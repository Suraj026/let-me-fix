"""
Agent 2: Context Collector — finds relevant files using grep, tree-sitter, and ChromaDB.
"""
import os
import re
from src.graph.state import GraphState
from src.models.manifest import ScoredFile, FileInfo
from src.models.events import TraceEvent
from src.tools.code_search import grep_files
from src.tools.tree_sitter_tools import (
    get_function_code,
    get_import_graph,
    extract_call_graph,
)
from src.tools.chroma_store import ChromaStore
from src.tools.notebook_converter import convert_notebook

def run_context_collector(state: GraphState) -> dict:
    """Search project files for code relevant to the bug.
    1. Read file contents (convert notebooks to Python)
    2. Generate search terms from error signature
    3. Run grep and tree-sitter analysis
    4. Index into ChromaDB for semantic search
    5. Score and rank relevant files
    """

    updates = {}
    trace_events = list(state.trace_events) # copy to avoid mutating acroaa calls
    manifest = state.manifest or []
    project_path = state.project_path

    if not manifest:
        trace_events.append(
            TraceEvent(
                agent="context",
                event_type="error",
                content="No manifest found — run intake first."
            )
        )
        updates["trace_events"] = trace_events
        updates["status"] = "failed"
        updates["error"] = "Context collector requires a file manifest."
        return updates
    
    # 1. Read file contents, converting notebooks to Python
    trace_events.append(
        TraceEvent(
            agent="context",
            event_type="tool_call",
            content=f"Reading {len(manifest)} files from project..."
        )
    )
    file_contents: dict[str, str] = {}
    file_functions: dict[str, list[str]] = {}
    import_graphs: dict[str, dict[str, list[str]]] = {}
    call_graphs: dict[str, dict[str, list[str]]] = {}
    notebook_count = 0

    for file_info in manifest:
        filepath = os.path.join(project_path, file_info.path)
        content = ""
        if file_info.is_notebook:
            nb_content = convert_notebook(filepath)
            if nb_content:
                content = nb_content
                notebook_count += 1
        else:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

        if content:
            file_contents[file_info.path] = content

    file_contents.update(state.file_contents or {})
    updates["file_contents"] = file_contents

    trace_events.append(
        TraceEvent(
            agent="context",
            event_type="milestone",
            content=f"Read {len(file_contents)} files ({notebook_count} notebooks converted)"
        )
    )

    # 2. Build search queries from error signature
    error_sig = state.error_signature
    search_terms = set()
    if error_sig:
        search_terms.add(error_sig.type)
        if error_sig.message:
            for word in re.findall(r"[a-zA-Z_]\w+", error_sig.message):
                if len(word) > 2:
                    search_terms.add(word)
        if error_sig.function:
            search_terms.add(error_sig.function)
        if error_sig.file:
            filename = os.path.basename(error_sig.file).replace(".py", "")
            search_terms.add(filename)

    trace_events.append(
        TraceEvent(
            agent="context",
            event_type="thinking",
            content=f"Search terms derived from error: {', '.join(sorted(search_terms)[:6])}"
        )
    )

     # 3. Run grep for each search term
    grep_results = {}  # file_path -> list of match dicts
    for term in search_terms:
        try:
            matches = grep_files(term, project_path)
            for match in matches:
                fpath = match["file"]
                if fpath not in grep_results:
                    grep_results[fpath] = []
                grep_results[fpath].append(match)
        except Exception:
            continue

     # 4. Run tree-sitter analysis on Python files for ChromaDB enrichment
    for fpath in file_contents:
        full_path = os.path.join(project_path, fpath)
        if not fpath.endswith(".py"):
            continue
        try:
            ig = get_import_graph(full_path)
            if ig:
                import_graphs[fpath] = ig
            cg = extract_call_graph(full_path)
            if cg:
                call_graphs[fpath] = cg
                file_functions[fpath] = list(cg.keys())
        except Exception:
            continue

     # 5. Index into ChromaDB
    trace_events.append(
        TraceEvent(
            agent="context",
            event_type="tool_call",
            content="Indexing files into ChromaDB for semantic search..."
        )
    )

    manifest_paths = {f.path for f in manifest}
    chroma = ChromaStore()

    # Build reverse import map
    reverse_imports: dict[str, list[str]] = {}
    for fpath, imports in import_graphs.items():
        for imp in imports:
            if imp not in reverse_imports:
                reverse_imports[imp] = []
            reverse_imports[imp].append(fpath)

    try:
        chroma.index_files(
            files=manifest,
            file_contents=file_contents,
            import_graphs=import_graphs,
            file_functions=file_functions,
            reverse_imports=reverse_imports,
        )
    except Exception as e:
        trace_events.append(
            TraceEvent(
                agent="context",
                event_type="error",
                content=f"ChromaDB indexing failed: {str(e)[:200]}"
            )
        )

    # 6. Query ChromaDB
    query_text = ""
    if error_sig:
        query_text = f"{error_sig.type}: {error_sig.message}"
        if error_sig.function:
            query_text += f" in {error_sig.function}"

    chroma_results = []
    if query_text:
        try:
            chroma_results = chroma.query(query_text, n_results=10)
        except Exception:
            pass

    # 7. Score and rank files
    scored: dict[str, ScoredFile] = {}

    # grep relevance: base score + 0.1 per match, capped at 1.0
    for fpath, matches in grep_results.items():
        score = min(1.0, 0.7 + (len(matches) * 0.1))
        match_reason = f"Matched {len(matches)} search term(s): {matches[0]['line'][:80]}"
        fi = _find_file_info(manifest, fpath)
        scored[fpath] = ScoredFile(
            file_info=fi or FileInfo(path=fpath, size=0, language="python"),
            relevance_score=round(score, 2),
            match_reason=match_reason,
        )

    # Chroma relevance: convert distance to similarity, merge with grep score if present
    for r in chroma_results:
        fpath = r["path"]
        chroma_score = max(0.0, 1.0 - r["score"])  # Convert distance to similarity
        if fpath in scored:
            # Merge: take the higher score
            existing = scored[fpath]
            combined = max(existing.relevance_score, round(chroma_score, 2))
            scored[fpath] = ScoredFile(
                file_info=existing.file_info,
                relevance_score=combined,
                match_reason=existing.match_reason,
            )
        elif chroma_score > 0.3:
            fi = _find_file_info(manifest, fpath)
            scored[fpath] = ScoredFile(
                file_info=fi or FileInfo(path=fpath, size=0, language="python"),
                relevance_score=round(chroma_score, 2),
                match_reason=f"Semantic match to error: {query_text[:60]}",
            )

    # Sort by score descending
    relevant_files = sorted(scored.values(), key=lambda x: x.relevance_score, reverse=True)

    # Store chroma collection id for potential reuse
    updates["relevant_files"] = relevant_files
    updates["chroma_collection_id"] = chroma.collection.name

    trace_events.append(
        TraceEvent(
            agent="context",
            event_type="milestone",
            content=f"Found {len(relevant_files)} relevant files for investigation"
        )
    )
    updates["trace_events"] = trace_events
    updates["status"] = "running"
    return updates


def _find_file_info(manifest: list[FileInfo], path: str) -> FileInfo | None:
    """Find FileInfo in manifest by path."""
    for fi in manifest:
        if fi.path == path:
            return fi
    return None
    

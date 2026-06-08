"""
ChromaDB wrapper for file embedding and semantic search with import-aware metadata.
"""

import chromadb
from chromadb.config import Settings
from src.models.manifest import FileInfo
from typing import Optional

class ChromaStore:
    """Wraps ChromaDB for file embedding and semantic search.
    Stores file content + metadata (imports, functions, callers) so Agent 2
    can find files related to a bug by semantic meaning not just keywords.
    """

    def __init__(self, persist_directory: Optional[str] = None):
        if persist_directory:
            self.client = chromadb.PersistentClient(
                path = persist_directory,
                settings = Settings(anonymized_telemetry = False)
            )
        else:
            self.client = chromadb.EphemeralClient(
                settings = Settings(anonymized_telemetry = False)
            )
        self.collection = self.client.get_or_create_collection(
            name = "project_files",
            configuration = {
                "hnsw": {"space": "cosine"}
            }
        )
    
    def index_files(self, 
                    files : list[FileInfo], 
                    file_contents : dict[str, str], 
                    import_graphs : Optional[dict[str, dict[str, list[str]]]] = None,
                    file_functions : Optional[dict[str, list[str]]] = None,
                    reverse_imports : Optional[dict[str, list[str]]] = None
                ) -> None:
        """Embed file contents with rich metadata for semantic search.
        
        Args:
            files: FileInfo list from manifest builder
            file_contents: Raw file content keyed by path
            import_graphs: Output of get_import_graph() keyed by path
            file_functions: Function names defined in each file, keyed by path
            reverse_imports: Files that import each file, keyed by path
        """
        ids, contents, metadatas = [], [], []
        for file in files:
            content = file_contents.get(file.path, "")
            if not content:
                continue
            ids.append(file.path)
            contents.append(content)
            metadata = {
                "path": file.path,
                "language": file.language,
                "size": file.size,
                "imports" : "",
                "functions": "",
                "imported_by": ""
            }
            # Add import graph info if available
            if import_graphs and file.path in import_graphs:
                imports = import_graphs[file.path]
                metadata["imports"] = ", ".join(sorted(imports.keys()))
            # Add function definitions if available
            if file_functions and file.path in file_functions:
                metadata["functions"] = ", ".join(file_functions[file.path])
            # Add reverse import info if available
            if reverse_imports and file.path in reverse_imports:
                metadata["imported_by"] = ", ".join(reverse_imports[file.path])
            metadatas.append(metadata)

        if ids:
            self.collection.upsert(
                ids = ids,
                documents = contents,
                metadatas = metadatas
            )

    def query(self, query_text : str, n_results: int = 5) -> list[dict]:
        """Query ChromaDB for semantically similar files.
        
        Returns list of {path, score, metadata} sorted by relevance.
        Returns empty list if nothing indexed yet.
        """
        if self.collection.count() == 0:
            return []
        results = self.collection.query(
            query_texts = [query_text],
            n_results = min(n_results, self.collection.count())
        )

        output = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "path": doc_id,
                    "score": results["distances"][0][i] if results.get("distances") else 0.0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {}
                })
        return output
    
    def find_related(self, seed_paths : list[str], n_results: int = 5) -> list[dict]:
        """Given seed files (e.g. crash site), find semantically related files.
        Uses ChromaDB's $contains filter to find files sharing imports
        with the seed files, then ranks by semantic similarity.
        """
        if self.collection.count() == 0:
            return []
         # Collect imports from seed files to find related files
        seed_imports = set()
        for path in seed_paths:
            try:
                result = self.collection.get(ids=[path])
                metadatas = result.get("metadatas") or []
                if not metadatas:
                    continue
                imports_str = metadatas[0].get("imports", "")
                for mod in imports_str.split(", "):
                    if mod:
                        seed_imports.add(mod)
            except Exception:
                continue

        if not seed_imports:
            return []
        
        # For each related import, search with it as query
        all_results = {}
        scored_imports = sorted(seed_imports)[:3]   # Limit to top 3
        for imp in scored_imports:
            results = self.query(imp, n_results=n_results)
            for r in results:
                if r["path"] not in seed_paths:
                    all_results[r["path"]] = r

        # Sort by score and return
        return sorted(all_results.values(), key=lambda x: x["score"])

    def clear(self) -> None:
        """Delete and recreate the collection."""
        self.client.delete_collection("project_files")
        self.collection = self.client.get_or_create_collection(
            name = "project_files",
            configuration = {
                "hnsw": {"space": "cosine"}
            }
        )
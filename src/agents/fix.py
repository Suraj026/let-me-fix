"""Agent 5: Generates corrected file content from the confirmed hypothesis using the LLM.

The LLM outputs full corrected file content in ``### path\n```python\n...\n```\n``
blocks.  The fix agent parses these blocks, stores them directly in
``state.fixed_files`` (filepath → corrected content), and passes them to the
verification agent which overwrites the files in the sandbox/workspace.

No unified-diff generation is involved.
"""

import os
import re
from src.graph.state import GraphState
from src.models.events import TraceEvent
from src.llm.model import LLMClient


def _parse_llm_patch(text: str) -> dict[str, str]:
    """Parse LLM output into {filepath: new_content} map.

    Expected format per file:

        ### path/to/file.py
        ```python
        <new file content>
        ```
    """
    files: dict[str, str] = {}
    # Match: ### filename  then ```...``` block
    pattern = r'###\s+(.+?)\s*\n```(?:python)?\s*\n(.*?)```'
    for match in re.finditer(pattern, text, re.DOTALL):
        fpath = match.group(1).strip()
        content = match.group(2).strip()
        # avoid matching non-file markers
        if fpath and content:
            files[fpath] = content
    return files


def run_fix(state: GraphState) -> dict:
    """Run the fix agent — ask LLM for corrected file content, store in fixed_files."""
    updates: dict = {}
    trace_events = list(state.trace_events)
    hypotheses = state.confirmed_hypothesis
    prev_verification = state.verification
    retry_attempt = state.retry_count

    if not hypotheses:
        trace_events.append(
            TraceEvent(
                agent="fix",
                event_type="error",
                content="No confirmed hypothesis to generate fix from."
            )
        )
        updates["trace_events"] = trace_events
        updates["status"] = "failed"
        updates["error"] = "Fix generation requires hypotheses to generate from."
        return updates

    # Gather relevant file contents from investigation results
    file_contents: dict[str, str] = {}
    project_path = state.project_path
    for fpath in (state.confirmed_hypothesis.evidence_files or []):
        full_path = os.path.join(project_path, fpath)
        try:
            with open(full_path, 'r') as f:
                file_contents[fpath] = f.read()
        except (OSError, FileNotFoundError):
            trace_events.append(
                TraceEvent(
                    agent="fix",
                    event_type="error",
                    content=f"Could not read file: {fpath}"
                )
            )

    error_sig = state.error_signature
    prompt = f"""You are a Python bug-fixing agent. Given the error analysis below, output the CORRECTED content of each file that needs to be changed.

Error: {error_sig.type if error_sig else 'Unknown'}: {error_sig.message if error_sig else 'N/A'}
Root cause: {hypotheses.description}

Current file contents:
"""
    for fpath, content in file_contents.items():
        prompt += f"\n### {fpath}\n```python\n{content}```\n"

    # Add verification failure feedback on retries
    if retry_attempt > 0 and prev_verification and not prev_verification.get("success"):
        test_output = prev_verification.get("test_output", "")
        prompt += f"""
Previous fix attempt failed (attempt {retry_attempt} of {state.max_retries}).
Output from failed verification:
{test_output[:2000]}

Generate a DIFFERENT fix.
"""
    else:
        prompt += "\nThis is the first fix attempt.\n"

    prompt += """
For each file that needs changes, output:
### path/to/file.py
```python
<full corrected file content>
```

IMPORTANT:
- Only output files that need to be changed
- Output the COMPLETE corrected file, not just the changed lines
- Use ```python ... ``` code blocks with exactly one `###` header per file
- No explanation, no markdown, no commentary outside the blocks
"""
    trace_events.append(
        TraceEvent(
            agent="fix",
            event_type="thinking",
            content="Requesting fix from LLM..."
        )
    )
    llm = LLMClient()
    response = llm.generate(prompt)
    llm_text = response.text.strip()

    # Parse LLM output into file -> new content
    llm_files = _parse_llm_patch(llm_text)

    # Harden paths: if the LLM outputs a path that doesn't match our
    # file_contents keys (e.g. "tests/corpus/type_error/main.py" vs "main.py"),
    # try to resolve it by reading from disk.
    for fpath in list(llm_files.keys()):
        if fpath not in file_contents:
            try:
                alt_path = os.path.join(project_path, fpath)
                with open(alt_path, 'r') as f:
                    file_contents[fpath] = f.read()
                trace_events.append(
                    TraceEvent(
                        agent="fix",
                        event_type="thinking",
                        content=f"Read {fpath} from disk (path mismatch in file_contents)"
                    )
                )
            except (OSError, FileNotFoundError):
                pass  # Path is opaque to us — verification will handle it

    if not llm_files:
        trace_events.append(
            TraceEvent(
                agent="fix",
                event_type="error",
                content="LLM did not return valid file blocks (### path ``` blocks). Cannot generate fix."
            )
        )
        updates["trace_events"] = trace_events
        updates["status"] = "failed"
        updates["error"] = "LLM response missing file blocks."
        return updates

    updates["fixed_files"] = llm_files
    trace_events.append(
        TraceEvent(
            agent="fix",
            event_type="milestone",
            content=f"Generated corrected content for {len(llm_files)} file(s): {', '.join(llm_files.keys())} (model: {response.model or 'unknown'})"
        )
    )

    updates["trace_events"] = trace_events
    return updates
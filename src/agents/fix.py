"""Agent 5: Generates a fix patch from the confirmed hypothesis using the LLM."""

import os
import re
from src.graph.state import GraphState
from src.models.events import TraceEvent
from src.llm.model import LLMClient

def run_fix(state: GraphState) -> dict:
    """Run the fix agent."""
    updates = {}
    trace_events = list(state.trace_events)
    hypotheses = state.confirmed_hypothesis 

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
    file_contents = {}
    project_path = state.project_path
    for result in (state.investigation_results or []):
        for fpath in (state.confirmed_hypothesis.evidence_files or []):
            full_path = os.path.join(project_path, fpath)
            try:
                with open(full_path, 'r') as f:
                    file_contents[fpath] = f.read()
            except (OSError, FileNotFoundError):
                continue

    # Build LLM prompt
    error_sig = state.error_signature
    prompt = f"""You are a Python bug-fixing agent. Given the error analysis below, produce a unified diff patch.

        Error: {error_sig.type if error_sig else 'Unknown'}: {error_sig.message if error_sig else 'N/A'}
        Root cause: {hypotheses.description}

        Relevant files:
    """
    for fpath, content in file_contents.items():
        prompt += f"\n--- {fpath} ---\n{content}\n"

    prompt += """
        Output ONLY a unified diff patch in this format:
        --- a/path/to/file.py
        +++ b/path/to/file.py
        @@ -start,count +start,count @@
        <code changes>

        No explanation, no commentary.
    """
    trace_events.append(
        TraceEvent(
            agent="fix",
            event_type="thinking",
            content="Requesting fix patch from LLM..."
        )
    )
    llm = LLMClient()
    response = llm.generate(prompt)
    
    # Extract diff block from response
    patch = response.text.strip()
    # if LLM wrapped it in markdown code block, strip that
    if "```" in patch:
        blocks = re.findall(r"```(?:diff)?\s*\n(.+?)```", patch, re.DOTALL)
        if blocks:
            patch = blocks[0].strip()

    trace_events.append(TraceEvent(
        agent="fix", event_type="milestone",
        content=f"Patch generated ({len(patch.splitlines())} lines, model: {response.model or 'unknown'})"
    ))

    updates["patch"] = patch
    updates["trace_events"] = trace_events
    return updates
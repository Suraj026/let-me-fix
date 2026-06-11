"""Agent 4: Picks the top hypothesis and gathers supporting evidence from files."""

import os
import re
from src.graph.state import GraphState
from src.models.hypothesis import InvestigationResult
from src.models.events import TraceEvent

def run_investigation(state : GraphState) -> dict:
    """Run the investigation agent."""
    updates = {}
    trace_events = list(state.trace_events)
    hypotheses = state.hypotheses or []

    if not hypotheses:
        trace_events.append(
            TraceEvent(
                agent="investigation",
                event_type="error",
                content="No hypotheses to investigate."
            )
        )
        updates["trace_events"] = trace_events
        updates["status"] = "failed"
        updates["error"] = "Investigation requires hypotheses to investigate."
        return updates
    
    # Pick highest confidence hypothesis
    top = max(hypotheses, key = lambda h: h.confidence)
    trace_events.append(
        TraceEvent(
            agent="investigation",
            event_type="thinking",
            content=f"Selected hypothesis: {top.description} with confidence {top.confidence:.2f}"
        )
    )

    # Read evidence files
    evidence_parts = []
    project_path = state.project_path
    for fpath in top.evidence_files:
        full_path = os.path.join(project_path, fpath)
        try:
            with open(full_path, 'r') as f:
                content = f.read()
            # extract relevant lines near error terms
            evidence_parts.append(f"---{fpath}---\n{content}")
        
        except (OSError, FileNotFoundError):
            trace_events.append(
                TraceEvent(
                    agent="investigation",
                    event_type="error",
                    content=f"Could not read evidence file: {fpath}"
                )
            )

    result = InvestigationResult(
        hypothesis_id=top.id,
        confirmed=True,
        evidence="\n".join(evidence_parts),
        tool_output=[{"file": f} for f in top.evidence_files]
    )
    trace_events.append(
        TraceEvent(
            agent="investigation",
            event_type="milestone",
            content=f"Investigation completed - evidence from {len(top.evidence_files)} files gathered."
        )
    )
    updates["investigation_results"] = [result]
    updates["confirmed_hypothesis"] = top
    updates["trace_events"] = trace_events
    return updates
    
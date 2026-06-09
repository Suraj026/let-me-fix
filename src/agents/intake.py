"""Agent 1: Bug Intake — parses trace and builds file manifest."""
import uuid
from src.graph.state import GraphState
from src.tools.trace_parser import parse_trace
from src.tools.manifest import build_manifest
from src.models.events import TraceEvent

def run_intake(state: GraphState) -> dict:
    """
    Parse the bug trace and build the project file manifest.
    LangGraph node function. Returns partial state update dict.
    """
    updates = {}

    # Generate a unique session ID if not already set
    if not state.session_id:
        id = uuid.uuid4().hex[:8]
        updates["session_id"] = id

    # 1. Parse the bug trace to extract error signature
    state.trace_events.append(
        TraceEvent(
            agent = "intake",
            event_type = "tool_call",
            content = "Parsing bug trace..."
        )
    )
    parsed = parse_trace(state.bug_trace)
    if parsed is None:
        state.trace_events.append(
            TraceEvent(
                agent = "intake",
                event_type = "error",
                content = f"Failed to parse trace: {state.bug_trace[:100]}..."
            )
        )
        updates["status"] = "failed"
        updates["error"] =  "Could not parse bug trace — unrecognized format."
        updates["trace_events"] = state.trace_events
        return updates
    
    updates["error_signature"] = parsed.error 
    state.trace_events.append(
        TraceEvent(
            agent = "intake",
            event_type = "milestone",
            content = f"Parsed {parsed.error.type}: {parsed.error.message}"
        )
    )

    # 2. Build the project file manifest
    state.trace_events.append(
        TraceEvent(
            agent="intake",
            event_type="tool_call",
            content=f"Scanning project: {state.project_path}"
        )
    )

    manifest = build_manifest(state.project_path)
    updates["manifest"] = manifest
    
    state.trace_events.append(
        TraceEvent(
            agent="intake",
            event_type="milestone",
            content=f"Found {len(manifest)} files in project"
        )
    )

    # 3. Mark complete
    state.trace_events.append(
        TraceEvent(
            agent="intake",
            event_type="thinking",
            content=f"Intake complete. Error: {parsed.error.type} in {parsed.error.file or 'unknown'}"
        )
    )
    updates["trace_events"] = state.trace_events
    updates["status"] = "running"
    return updates
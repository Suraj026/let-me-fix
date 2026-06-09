from src.graph.state import GraphState
from src.models.trace import ErrorSignature
from src.models.events import TraceEvent


def test_initial_state():
    state = GraphState()
    assert state.session_id == ""
    assert state.status == "running"
    assert state.bug_trace == ""
    assert state.error_signature is None
    assert state.manifest == []
    assert state.error is None


def test_state_with_signature():
    sig = ErrorSignature(type="TypeError", message="int + str")
    state = GraphState(error_signature=sig)
    assert state.error_signature is not None
    assert state.error_signature.type == "TypeError"


def test_state_custom_session():
    state = GraphState(session_id="debug-001", bug_trace="Traceback...", project_path="/app")
    assert state.session_id == "debug-001"
    assert state.bug_trace == "Traceback..."
    assert state.project_path == "/app"
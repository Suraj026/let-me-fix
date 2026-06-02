from src.models.trace import ErrorSignature, ParsedTrace
from src.models.manifest import FileInfo
from src.models.hypothesis import Hypothesis
from src.models.events import TraceEvent

def test_error_signature():
    sig = ErrorSignature(type="TypeError", message="unsupported operand type(s) for +: 'int' and 'str'")
    assert sig.type == "TypeError"
    assert sig.message == "unsupported operand type(s) for +: 'int' and 'str'"
    assert sig.file is None

def test_trace_event_default_timestamp():
    event = TraceEvent(agent="intake", event_type="milestone", content="done")
    assert event.timestamp is not None

def test_hypothesis_defaults():
    h = Hypothesis(
        id="h1", description="test", confidence=0.8,
        evidence_files=["a.py"], verification_steps=["run pytest"]
    )
    assert h.confirmed is None
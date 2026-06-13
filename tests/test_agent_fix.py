"""Tests for Agent 5: Fix Generator."""

import pytest
from unittest.mock import patch, MagicMock
from src.graph.state import GraphState
from src.agents.fix import run_fix, _parse_llm_patch
from src.llm.model import LLMResponse
from src.models.trace import ErrorSignature
from src.models.hypothesis import Hypothesis

@pytest.fixture
def state_with_hypothesis():
    h = Hypothesis(
        id = "h1",
        description="TypeError in calculate() - adds int + str",
        evidence_files=["main.py"],
        confidence=0.9,
        verification_steps=["Check line 17"]
    )
    return GraphState(
        session_id="test-fix",
        status="running",
        project_path="tests/corpus/type_error",
        error_signature=ErrorSignature(
            type="TypeError",
            message="unsupported operand type(s) for +: 'int' and 'str'",
        ),
        confirmed_hypothesis=h,
        investigation_results=[],
        trace_events=[]
    )


def test_parse_llm_patch():
    """_parse_llm_patch extracts file -> content map from ### blocks."""
    text = """### main.py
```python
def add(a, b):
    return a + b
```
### utils.py
```python
def helper():
    pass
```"""
    result = _parse_llm_patch(text)
    assert "main.py" in result
    assert "def add(a, b):" in result["main.py"]
    assert "utils.py" in result
    assert "def helper():" in result["utils.py"]


def test_fix_no_hypothesis():
    """Fails when no confirmed hypothesis."""
    state = GraphState(
        confirmed_hypothesis=None,
        trace_events=[],
    )
    result = run_fix(state)
    assert result["status"] == "failed"
    assert result["error"] is not None


@patch("src.agents.fix.LLMClient")
def test_fix_generates_fixed_files(mock_llm_cls, state_with_hypothesis):
    """Returns fixed_files dict when LLM responds with file blocks."""
    mock_instance = MagicMock()
    mock_instance.generate.return_value = LLMResponse(
        text="### main.py\n```python\ndef process_data(data):\n    if isinstance(data, str):\n        data = len(data)\n    return data * data\n\nif __name__ == '__main__':\n    result = process_data(5)\n    print(result)\n```",
        model="test-model",
    )
    mock_llm_cls.return_value = mock_instance

    result = run_fix(state_with_hypothesis)

    assert "fixed_files" in result
    assert "main.py" in result["fixed_files"]
    assert "len(data)" in result["fixed_files"]["main.py"]


@patch("src.agents.fix.LLMClient")
def test_fix_emits_milestone(mock_llm_cls, state_with_hypothesis):
    """Emits milestone trace event with fix info."""
    mock_instance = MagicMock()
    mock_instance.generate.return_value = LLMResponse(
        text="### main.py\n```python\ndef process_data(data):\n    return int(data) * int(data)\n```",
        model="test-model",
    )
    mock_llm_cls.return_value = mock_instance

    result = run_fix(state_with_hypothesis)

    events = result["trace_events"]
    assert any(e.event_type == "milestone" for e in events)
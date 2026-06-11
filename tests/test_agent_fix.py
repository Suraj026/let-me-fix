"""Tests for Agent 5: Fix Generator."""

import pytest
from unittest.mock import patch, MagicMock
from src.graph.state import GraphState
from src.agents.fix import run_fix
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
def test_fix_generates_patch(mock_llm_cls, state_with_hypothesis):
    """Returns a patch when LLM responds."""
    mock_instance = MagicMock()
    mock_instance.generate.return_value = LLMResponse(
        text="--- a/main.py\n+++ b/main.py\n@@ -1,3 +1,3 @@\n-def calculate(a, b):\n+def calculate(a, b):\n+    return int(a) + int(b)",
        model="test-model",
    )
    mock_llm_cls.return_value = mock_instance

    result = run_fix(state_with_hypothesis)

    assert "patch" in result
    assert result["patch"] is not None
    assert len(result["patch"]) > 0
    assert "--- a/" in result["patch"]

@patch("src.agents.fix.LLMClient")
def test_fix_emits_milestone(mock_llm_cls, state_with_hypothesis):
    """Emits milestone trace event with patch info."""
    mock_instance = MagicMock()
    mock_instance.generate.return_value = LLMResponse(
        text="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-1\n+2",
        model="test-model",
    )
    mock_llm_cls.return_value = mock_instance

    result = run_fix(state_with_hypothesis)

    events = result["trace_events"]
    assert any(e.event_type == "milestone" for e in events)
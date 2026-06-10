"""Tests for Agent 3: Hypothesis Generator."""

import pytest
from unittest.mock import patch, MagicMock
from src.graph.state import GraphState
from src.agents.hypothesis import run_hypothesis
from src.llm.model import LLMResponse
from src.models.trace import ErrorSignature
from src.models.manifest import FileInfo, ScoredFile
from src.models.hypothesis import Hypothesis


@pytest.fixture
def state_with_context():
    return GraphState(
        session_id="test-hyp",
        status="running",
        bug_trace="""Traceback (most recent call last):
                    File "main.py", line 19, in <module>
                        result = calculate(1, "hello")
                    File "main.py", line 17, in calculate
                        return a + b
                    TypeError: unsupported operand type(s) for +: 'int' and 'str'
                """,
        project_path="tests/corpus/type_error",
        manifest=[FileInfo(path="main.py", size=100, language="python")],
        error_signature=ErrorSignature(
            type="TypeError",
            message="unsupported operand type(s) for +: 'int' and 'str'",
            file="main.py",
            line=17,
            function="calculate",
        ),
        relevant_files=[
            ScoredFile(
                file_info=FileInfo(path="main.py", size=100, language="python"),
                relevance_score=0.95,
                match_reason="Contains the error"
            )
        ],
        chroma_collection_id="test-chroma",
        trace_events=[],
    )


def test_hypothesis_requires_context():
    """Should fail if no error signature or relevant files."""
    state = GraphState(
        manifest=[FileInfo(path="main.py", size=100, language="python")],
        project_path="tests/corpus/type_error",
        trace_events=[],
    )
    updates = run_hypothesis(state)
    assert updates["status"] == "failed"
    assert updates["error"] is not None


@patch("src.agents.hypothesis.LLMClient")
def test_hypothesis_generates_from_context(mock_llm_cls, state_with_context):
    """Should produce hypotheses when LLM returns valid JSON."""
    mock_instance = MagicMock()
    mock_instance.generate.return_value = LLMResponse(
        text='{"hypotheses": [{"description": "The function calculate(a, b) adds a and b directly. When b is a string Python raises TypeError.", "confidence": 0.9, "evidence_files": ["main.py"], "verification_steps": ["Inspect line 17 in main.py", "Check the type of b passed to calculate"]}]}',
        model="test-model",
    )
    mock_llm_cls.return_value = mock_instance

    updates = run_hypothesis(state_with_context)

    assert updates["status"] == "running"
    assert len(updates["hypotheses"]) > 0
    for h in updates["hypotheses"]:
        assert isinstance(h, Hypothesis)
        assert h.description
        assert 0.0 <= h.confidence <= 1.0
        assert len(h.evidence_files) > 0
        assert len(h.verification_steps) > 0


@patch("src.agents.hypothesis.LLMClient")
def test_hypothesis_handles_llm_failure(mock_llm_cls, state_with_context):
    """Should fall back to a default hypothesis when LLM fails."""
    mock_instance = MagicMock()
    mock_instance.generate.side_effect = Exception("API error")
    mock_llm_cls.return_value = mock_instance

    updates = run_hypothesis(state_with_context)

    # Fallback: still produce at least one hypothesis
    assert len(updates["hypotheses"]) >= 1
    assert updates["status"] == "running"
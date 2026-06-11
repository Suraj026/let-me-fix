"""Tests for the investigation agent."""
import pytest
from src.graph.state import GraphState
from src.models.hypothesis import Hypothesis, InvestigationResult
from src.agents.investigation import run_investigation

class TestInvestigation:
    """Tests for the investigation agent."""

    def test_confirms_top_hypothesis(self):
        """Picks the top hypothesis and confirms it."""
        h1 = Hypothesis(
            id = "h1",
            description="Low confidence hypothesis",
            evidence_files=[],
            confidence=0.1,
            verification_steps=[]
        )
        h2 = Hypothesis(
            id = "h2",
            description="High confidence hypothesis",
            evidence_files=[],
            confidence=0.9,
            verification_steps=[]
        )
        state = GraphState(
            hypotheses=[h1, h2],
            project_path="/tmp"
        )
        result = run_investigation(state)

        assert result["confirmed_hypothesis"].id == "h2"
        assert len(result["investigation_results"]) == 1
        assert result["investigation_results"][0].hypothesis_id == "h2"

    def test_empty_hypotheses_fails(self):
        """Returns status = failed when no hypotheses are provided."""
        state = GraphState(
            hypotheses=[],
            project_path="/tmp"
        )
        result = run_investigation(state)

        assert result["status"] == "failed"
        assert "hypotheses" in result["error"].lower()

    def test_reads_evidence_files(self, tmp_path):
        """Reads content from files listed in evidence files."""
        bugfile = tmp_path / "buggy.py"
        bugfile.write_text("x = 1 + 'Hello'  # TypeError\n")

        h = Hypothesis(
            id = "h1",
            description="Type error in buggy.py",
            evidence_files=["buggy.py"],
            confidence=0.8,
            verification_steps=[]
        )
        state = GraphState(
            hypotheses=[h],
            project_path=str(tmp_path)
        )
        result = run_investigation(state)
        res = result["investigation_results"][0]
        assert "buggy.py" in res.evidence
        assert "TypeError" in res.evidence

    def test_emits_trace_events(self):
        """Investigation emits thinking and milestone events."""
        h = Hypothesis(
            id="h1", 
            description="Root cause",
            evidence_files=[], 
            confidence=0.9,
            verification_steps=[]
        )
        state = GraphState(
            hypotheses=[h], 
            project_path="/tmp"
        )
        result = run_investigation(state)

        events = result["trace_events"]
        assert any(e.event_type == "thinking" for e in events)
        assert any(e.event_type == "milestone" for e in events)
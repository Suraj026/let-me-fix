"""Tests for LangGraph graph definition."""

from src.graph.graph import build_graph, run_pipeline, route_from_verification
from src.graph.state import GraphState
from src.models.hypothesis import Hypothesis


def test_build_returns_compiled_graph():
    graph = build_graph()
    assert graph is not None
    assert "intake" in graph.nodes
    assert "context_collector" in graph.nodes
    assert "hypothesis" in graph.nodes
    assert "investigation" in graph.nodes
    assert "fix" in graph.nodes
    assert "verification" in graph.nodes


def test_run_pipeline_no_trace():
    """Pipeline with empty trace should fail at intake gracefully."""
    result = run_pipeline(bug_trace="", project_path=".")
    assert isinstance(result, GraphState)
    assert result.status == "failed" or result.error is not None

def test_route_verification_success():
    """Routes to 'end' when verification passes."""
    state = GraphState(
        verification={"success": True},
        retry_count=0,
        max_retries=3,
    )
    assert route_from_verification(state) == "end"

def test_route_verification_retry():
    """Routes to 'fix' when verification fails and retries remain."""
    state = GraphState(
        verification={"success": False},
        retry_count=1,
        max_retries=3,
    )
    assert route_from_verification(state) == "fix"

def test_route_verification_exhausted():
    """Routes to 'end' when retries are exhausted."""
    state = GraphState(
        verification={"success": False},
        retry_count=3,
        max_retries=3,
    )
    assert route_from_verification(state) == "end"
"""Tests for LangGraph graph definition."""

from src.graph.graph import build_graph, run_pipeline
from src.graph.state import GraphState


def test_build_returns_compiled_graph():
    graph = build_graph()
    assert graph is not None
    # Should have 3 nodes
    assert "intake" in graph.nodes
    assert "context_collector" in graph.nodes
    assert "hypothesis" in graph.nodes


def test_run_pipeline_no_trace():
    """Pipeline with empty trace should fail at intake gracefully."""
    result = run_pipeline(bug_trace="", project_path=".")
    assert isinstance(result, GraphState)
    assert result.status == "failed" or result.error is not None
"""Integration tests — run the full pipeline end-to-end.
These tests require OPENROUTER_API_KEY to be set in the environment."""

import os
import pytest
from src.graph.state import GraphState
from src.graph.graph import run_pipeline

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason = "OPENROUTER_API_KEY not set in environment",
)

def test_full_pipeline_with_llm_call():
    """Run the full intake -> context -> hypothesis pipeline with a real trace.
    
    This test:
    - Parses a real trace file
    - Builds a file manifest
    - Searches for relevant files (grep, tree-sitter, ChromaDB)
    - Calls OpenRouter to generate hypotheses
    """
    trace_path = "tests/corpus/type_error/trace.txt"
    project_path = "tests/corpus/type_error"
    result = run_pipeline(
        bug_trace=open(trace_path).read(),
        project_path=project_path,
    )

    assert isinstance(result, GraphState)
    assert result.status == "running", f"Pipeline failed: {result.error}"

    # Agent 1 output
    assert result.error_signature is not None
    assert result.error_signature.type == "TypeError"
    assert len(result.manifest) > 0

    # Agent 2 output
    assert len(result.relevant_files) > 0
    assert result.chroma_collection_id is not None

    # Agent 3 output — real LLM-generated hypotheses
    assert len(result.hypotheses) > 0
    for h in result.hypotheses:
        assert h.description, "Hypothesis must have a description"
        assert 0.0 <= h.confidence <= 1.0, "Confidence must be between 0 and 1"
        assert len(h.evidence_files) > 0, "Must reference evidence files"
        assert len(h.verification_steps) > 0, "Must have verification steps"

    # Check trace events from all 3 agents
    agent_types = {e.agent for e in result.trace_events}
    assert "intake" in agent_types
    assert "context" in agent_types
    assert "hypothesis" in agent_types
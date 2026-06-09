"""Tests for Agent 1: Bug Intake."""

import pytest
from src.graph.state import GraphState
from src.agents.intake import run_intake

@pytest.fixture
def sample_trace() -> str:
    return (
        "Traceback (most recent call last):\n"
        '  File "/app/main.py", line 3, in <module>\n'
        "    result = 1 + 'a'\n"
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'\n"
    )

@pytest.fixture
def temp_project(tmp_path):
    """Create a small project for manifest scanning."""
    main_py = tmp_path / "main.py"
    main_py.write_text("x = 1\n")
    utils = tmp_path / "utils.py"
    utils.write_text("def helper(): pass\n")
    return str(tmp_path)

def test_intake_parses_trace(sample_trace, temp_project):
    state = GraphState(bug_trace=sample_trace, project_path=temp_project)
    updates = run_intake(state)

    assert updates["status"] == "running"
    assert updates["error_signature"] is not None
    assert updates["error_signature"].type == "TypeError"
    assert len(updates["manifest"]) > 0
    assert len(updates["trace_events"]) >= 3

def test_intake_fails_on_bad_trace(temp_project):
    state = GraphState(bug_trace="garbage input", project_path=temp_project)
    updates = run_intake(state)

    assert updates["status"] == "failed"
    assert updates["error"] is not None
    assert "Could not parse" in updates["error"]


def test_intake_sets_session_id(sample_trace, temp_project):
    state = GraphState(bug_trace=sample_trace, project_path=temp_project)
    updates = run_intake(state)

    assert updates["session_id"] != ""
    assert len(updates["session_id"]) == 8

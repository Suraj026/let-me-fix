"""Tests for Agent 6: Verification."""

import os
import pytest
from src.graph.state import GraphState
from src.agents.verification import run_verification


def test_verification_no_fix():
    """Fails when fixed_files is empty."""
    state = GraphState(
        project_path="/tmp", trace_events=[],
        fixed_files={},
    )
    result = run_verification(state)
    assert result["status"] == "failed"


def test_verification_writes_files_direct(tmp_path):
    """Writes corrected files to a temp dir (never project path) and runs verification."""
    content = "x = 42\nprint(x)\n"
    state = GraphState(
        fixed_files={"main.py": content},
        project_path=str(tmp_path),
        retry_count=0,
        trace_events=[],
        use_sandbox=False,
        custom_command="python3 -c \"exec(open('main.py').read())\"",
    )
    result = run_verification(state)

    # Original project files should NOT have been touched
    assert not (tmp_path / "main.py").exists()

    assert "patch_applied" in result
    assert result["patch_applied"] is True
    assert "verification" in result
    assert result["verification"]["success"] is True


def test_verification_writes_fails_on_bad_path(tmp_path):
    """Returns failure when file can't be written (bad path)."""
    state = GraphState(
        fixed_files={"../malicious.py": "evil code"},
        project_path=str(tmp_path),
        retry_count=0,
        trace_events=[],
        use_sandbox=False,
    )
    result = run_verification(state)

    assert result["patch_applied"] is False
    assert result["verification"]["success"] is False


def test_verification_emits_trace_events(tmp_path):
    """Emits tool_call and milestone events."""
    content = "x = 1\n"
    state = GraphState(
        fixed_files={"main.py": content},
        project_path=str(tmp_path),
        retry_count=0,
        trace_events=[],
        use_sandbox=False,
    )
    result = run_verification(state)

    events = result["trace_events"]
    assert any(e.event_type == "tool_call" for e in events)
    assert any(e.event_type == "milestone" for e in events)
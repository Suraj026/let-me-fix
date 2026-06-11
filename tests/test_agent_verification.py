"""Tests for Agent 6: Verification."""

import os
import subprocess
import pytest
from src.graph.state import GraphState
from src.agents.verification import run_verification


def _init_git_repo(path):
    """Initialize a git repo and create a tracked file."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    return path


def test_verification_no_patch():
    """Fails when patch is None."""
    state = GraphState(patch=None, project_path="/tmp", trace_events=[])
    result = run_verification(state)
    assert result["status"] == "failed"


def test_verification_empty_patch():
    """Fails when patch is empty string."""
    state = GraphState(patch="", project_path="/tmp", trace_events=[])
    result = run_verification(state)
    assert result["status"] == "failed"


def test_verification_patch_apply(tmp_path):
    """Applies a valid patch and returns verification dict."""
    repo = _init_git_repo(str(tmp_path))
    (tmp_path / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    patch = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"

    state = GraphState(
        patch=patch, project_path=str(tmp_path),
        retry_count=0, trace_events=[]
    )
    result = run_verification(state)

    assert result["patch_applied"] is True
    assert "verification" in result
    assert "success" in result["verification"]
    assert "test_output" in result["verification"]
    assert "exit_code" in result["verification"]


def test_verification_patch_fails(tmp_path):
    """Returns patch_applied=False for invalid patch."""
    repo = _init_git_repo(str(tmp_path))
    (tmp_path / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    # Patch references a file that doesn't exist
    patch = "--- a/nonexistent.py\n+++ b/nonexistent.py\n@@ -1 +1 @@\n-x\n+y\n"

    state = GraphState(
        patch=patch, project_path=str(tmp_path),
        retry_count=0, trace_events=[]
    )
    result = run_verification(state)

    assert result["patch_applied"] is False
    assert result["retry_count"] == 1
    assert result["verification"]["success"] is False


def test_verification_emits_trace_events(tmp_path):
    """Emits tool_call and milestone events."""
    repo = _init_git_repo(str(tmp_path))
    (tmp_path / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    patch = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"

    state = GraphState(
        patch=patch, project_path=str(tmp_path),
        retry_count=0, trace_events=[]
    )
    result = run_verification(state)

    events = result["trace_events"]
    assert any(e.event_type == "tool_call" for e in events)
    assert any(e.event_type == "milestone" for e in events)
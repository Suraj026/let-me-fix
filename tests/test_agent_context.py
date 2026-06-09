"""Tests for Agent 2: Context Collector."""

import pytest
from src.graph.state import GraphState
from src.agents.context import run_context_collector
from src.models.trace import ErrorSignature


@pytest.fixture
def temp_project(tmp_path):
    """Create a small project with multiple files."""
    main = tmp_path / "main.py"
    main.write_text("""
import utils

def calculate(a, b):
    return a + b

result = calculate(1, "hello")
""")
    utils = tmp_path / "utils.py"
    utils.write_text("""
def helper():
    return 42

def process(data):
    return data.strip()
""")
    return str(tmp_path)


def test_context_collector_returns_files(temp_project):
    manifest = _build_manifest_for_test(temp_project)
    error_sig = ErrorSignature(
        type="TypeError",
        message="unsupported operand type(s) for +: 'int' and 'str'",
    )
    state = GraphState(
        manifest=manifest,
        error_signature=error_sig,
        project_path=temp_project,
        trace_events=[],
    )
    updates = run_context_collector(state)

    assert updates["status"] == "running"
    assert len(updates["relevant_files"]) > 0
    assert updates["file_contents"] is not None
    assert "main.py" in updates["file_contents"]


def test_context_collector_fails_without_manifest(temp_project):
    state = GraphState(
        manifest=[],
        project_path=temp_project,
        trace_events=[],
    )
    updates = run_context_collector(state)

    assert updates["status"] == "failed"
    assert updates["error"] is not None


def _build_manifest_for_test(project_path):
    """Helper to build a quick manifest without importing manifest builder."""
    from src.models.manifest import FileInfo
    import os
    files = []
    for root, dirs, names in os.walk(project_path):
        for name in names:
            if name.endswith(".py"):
                files.append(FileInfo(
                    path=os.path.relpath(os.path.join(root, name), project_path),
                    size=os.path.getsize(os.path.join(root, name)),
                    language="python",
                ))
    return files
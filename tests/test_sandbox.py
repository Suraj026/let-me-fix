"""Tests for DockerSandbox tool."""

import subprocess
import os
import tempfile
import pytest
from src.tools.sandbox import DockerSandbox


DOCKER_AVAILABLE = subprocess.run(
    ["docker", "info"], capture_output=True
).returncode == 0

pytestmark = pytest.mark.skipif(
    not DOCKER_AVAILABLE, 
    reason="Docker not available"
)

@pytest.fixture
def temp_git_project():
    """Create a temp git repo with a Python file and one failing test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # git init
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)

        # Create a Python file
        os.makedirs(os.path.join(tmpdir, "src"), exist_ok=True)
        with open(os.path.join(tmpdir, "src", "calc.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b  # bug: should be a + b but works fine here\n")
        
        # Write a passing test
        os.makedirs(os.path.join(tmpdir, "tests"), exist_ok=True)
        with open(os.path.join(tmpdir, "tests", "test_calc.py"), "w") as f:
            f.write("from src.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
        
        # git commit
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True)

        yield tmpdir

def test_sandbox_starts_container():
    """Context manager starts a container and cleans up on exit."""
    container_name = None
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        with DockerSandbox(tmpdir) as sandbox:
            container_name = sandbox._container_name

            # verify container is running
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True, 
                text=True
            )
            assert container_name in result.stdout

def test_sandbox_exec_run(temp_git_project):
    """exec_run runs a command and returns output."""
    with DockerSandbox(temp_git_project) as sandbox:
        result = sandbox.exec_run(["echo", "hello-world"])
        assert result["exit_code"] == 0
        assert "hello-world" in result["output"]

def test_sandbox_exec_run_timeout(temp_git_project):
    """exec_run with short timeout returns error gracefully."""
    with DockerSandbox(temp_git_project) as sandbox:
        result = sandbox.exec_run(["sleep", "10"], timeout=1)
        assert result["exit_code"] == -1
        assert "timed out" in result["output"].lower()

def test_sandbox_apply_patch(temp_git_project):
    """apply_patch applies a valid unified-diff to the container."""
    # Make a change and create a diff
    with open(os.path.join(temp_git_project, "src", "calc.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b  # fixed comment\n")
    
    diff = subprocess.run(
        ["git", "diff"], cwd=temp_git_project,
        capture_output=True, 
        text=True
        ).stdout

    # Revert the change on host
    subprocess.run(
        ["git", "checkout", "--", "."], 
        cwd=temp_git_project, 
        capture_output=True
    )

    with DockerSandbox(temp_git_project) as sandbox:
        result = sandbox.apply_patch(diff)
        assert result["success"] is True, f"Patch failed: {result['output']}"
        assert result["exit_code"] == 0

def test_sandbox_run_tests(temp_git_project):
    """run_tests runs pytest inside container and returns result."""
    with DockerSandbox(temp_git_project) as sandbox:
        result = sandbox.run_tests(timeout=30)
        assert result["success"] is True, f"Tests failed: {result['test_output']}"
        assert result["exit_code"] == 0

def test_sandbox_cleanup_on_error(temp_git_project):
    """Container is removed even if an exception occurs inside the block."""
    container_name = None
    try:
        with DockerSandbox(temp_git_project) as sandbox:
            container_name = sandbox._container_name
            raise ValueError("Something went wrong")
    except ValueError:
        pass

    # Container should be gone
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    assert container_name not in result.stdout



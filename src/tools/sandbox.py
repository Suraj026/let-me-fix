"""Docker-based sandbox for isolated patch apply and test execution."""

import subprocess
import tempfile
import os
import time
import random
import string
from pathlib import Path

class DockerSandbox:
    """
    Disposable Docker container for safely applying patches and running tests.
    """

    def __init__(self, project_path: str, timeout: int = 60, image: str =  "let-me-fix-sandbox"):
        self.project_path = project_path
        self.timeout = timeout
        self.image = image
        suffix = "".join(random.choices(string.ascii_lowercase, k=8))
        self._container_name = f"let-me-fix-sandbox-{suffix}"
        self._container_id = None

    def __enter__(self):
        # 1. Verify Docker is available
        result = subprocess.run(
            ["docker", "info"], 
            capture_output=True, 
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Docker is not available. Install Docker or use --no-sandbox. "
                f"Error: {result.stderr.strip()}"
            )
        # 2. Check if image exists, build if not
        result = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True, 
            text=True
        )
        if result.returncode != 0:
            # Build from project root (where Dockerfile lives)
            project_root = self._find_project_root()
            build = subprocess.run(
                ["docker", "build", "-t", self.image, "."],
                capture_output=True, 
                text=True,
                cwd=project_root
            )
            if build.returncode != 0:
                raise RuntimeError(f"Failed to build Docker image: {build.stderr.strip()}")
    
        # 3. Start container with project bind-mounted
        start = subprocess.run(
            ["docker", "run", "-d", "--name", self._container_name, "-v", f"{self.project_path}:/workspace",
            "--user", f"{os.getuid()}:{os.getgid()}", self.image, "sleep", "infinity"], 
            capture_output=True, 
            text=True
        )
        if start.returncode != 0:
            raise RuntimeError(f"Failed to start container: {start.stderr.strip()}")
        
        self._container_id = start.stdout.strip()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._container_id:
            subprocess.run(
                ["docker", "rm", "-f", self._container_id],
                capture_output=True
            )
            self._container_id = None
        return False  # Don't suppress exceptions
    
    def exec_run(self, cmd: list[str], timeout: int = 60) -> dict:
        """Run a command inside the container. Returns {exit_code, output}."""
        docker_cmd = ["docker", "exec", self._container_id] + cmd 
        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "exit_code" : result.returncode,
                "output" : (result.stdout + result.stderr).strip()
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code" : -1,
                "output" : f"Command timed out after {timeout} seconds"
            }
        
    def apply_patch(self, patch_content: str) -> dict:
        """Write patch to temp file, copy into container, git-apply.
        Returns {success, output, exit_code}."""
        
        # Write patch to host temp file
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as f:
            f.write(patch_content)
            patch_path = f.name
        try:
            # Cop yinto container
            cp = subprocess.run(
                ["docker", "cp", patch_path, f"{self._container_id}:/workspace/patch.diff"],
                capture_output=True,
                text=True
            )
            if cp.returncode != 0:
                return {
                    "success": False,
                    "output": f"Failed to copy patch into container: {cp.stderr.strip()}",
                    "exit_code": cp.returncode
                }
            # Dry run check first
            check = subprocess.run(
                ["docker", "exec", self._container_id, "git", "apply", "--check", "/workspace/patch.diff"],
                capture_output=True,
                text=True
            )
            if check.returncode != 0:
                return {
                    "success": False,
                    "output": f"Patch dry run failed: {check.stderr.strip()}",
                    "exit_code": check.returncode
                }
            
            # Apply patch
            apply = subprocess.run(
                ["docker", "exec", self._container_id, "git", "apply", "/workspace/patch.diff"],
                capture_output=True,
                text=True
            )
            return {
                "success": apply.returncode == 0,
                "output": (apply.stdout + apply.stderr).strip(),
                "exit_code": apply.returncode
            }
        finally:
            os.unlink(patch_path)  # Clean up temp file

    def run_tests(self, timeout: int = 60) -> dict:
        """Run pytest inside container. Returns {success, test_output, exit_code}."""
        result = self.exec_run(
            ["python", "-m", "pytest", "-x", "--tb=short"],
            timeout=timeout
        )
        return {
            "success": result["exit_code"] == 0,
            "test_output": result["output"],
            "exit_code": result["exit_code"]
        }
        
    def _find_project_root(self) -> str:
        """Walk up from project_path to find Dockerfile."""
        current = Path(self.project_path).resolve()
        for parent in [current] + list(current.parents):
            if (parent / "Dockerfile").exists():
                return str(parent)
        return str(current)  # fallback
         
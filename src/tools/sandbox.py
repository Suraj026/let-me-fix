"""Docker-based sandbox for isolated fix verification and test execution."""

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
        self.project_path = os.path.abspath(project_path)
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
        
        # 3. Start container with project mounted READ-ONLY
        #    Read-only mount prevents accidental writes to the host filesystem.
        #    write_files() copies the project to a writable temp dir inside the container.
        start = subprocess.run(
            ["docker", "run", "-d", "--name", self._container_name,
             "-v", f"{self.project_path}:/workspace:ro",
             "--user", f"{os.getuid()}:{os.getgid()}",
             self.image, "sleep", "infinity"], 
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
    
    def exec_run(self, cmd: list[str], timeout: int = 60, workdir: str = "/workspace") -> dict:
        """Run a command inside the container. Returns {exit_code, output}.
        The workdir defaults to /workspace (where the project is bind-mounted).
        """
        docker_cmd = ["docker", "exec", "--workdir", workdir, self._container_id] + cmd 
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
        
    def write_files(self, files: dict[str, str]) -> dict:
        """Write multiple files into a writable workspace inside the container.

        The project is mounted read-only at /workspace.  This method:
        1. Creates a writable temp dir inside the container
        2. Copies the entire project into it (so all files are available)
        3. Overwrites only the files in ``files`` with the corrected content
        4. Sets ``self._writable_workspace`` so subsequent commands run from there
        
        Each key is a relative filepath (e.g. ``main.py`` or
        ``tests/corpus/type_error/main.py``), and the value is the
        full corrected file content.
        
        Returns {success, writable_workspace, written, errors}
        """
        import tempfile
        errors: dict[str, str] = {}
        success_count = 0

        # 1. Create writable temp dir inside container
        suffix = "".join(random.choices(string.ascii_lowercase, k=8))
        writable_dir = f"/tmp/lmf-workspace-{suffix}"
        mkdir = subprocess.run(
            ["docker", "exec", self._container_id, "mkdir", "-p", writable_dir],
            capture_output=True, text=True,
        )
        if mkdir.returncode != 0:
            return {
                "success": False,
                "written": 0,
                "errors": {"__workspace__": mkdir.stderr.strip()},
            }

        # 2. Copy project files from read-only mount into writable dir
        cp_ret = subprocess.run(
            ["docker", "exec", self._container_id, "cp", "-a", "/workspace/.", f"{writable_dir}/"],
            capture_output=True, text=True,
        )
        if cp_ret.returncode != 0:
            return {
                "success": False,
                "written": 0,
                "errors": {"__workspace__": cp_ret.stderr.strip()},
            }

        # 3. Write fixed files into the writable workspace
        for fpath, content in files.items():
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                f.write(content)
                host_path = f.name
            try:
                container_path = f"{writable_dir}/{fpath.lstrip('/')}"
                parent = os.path.dirname(container_path)
                if parent and parent != writable_dir:
                    subprocess.run(
                        ["docker", "exec", self._container_id, "mkdir", "-p", parent],
                        capture_output=True, text=True,
                    )
                cp = subprocess.run(
                    ["docker", "cp", host_path, f"{self._container_id}:{container_path}"],
                    capture_output=True, text=True,
                )
                if cp.returncode != 0:
                    errors[fpath] = cp.stderr.strip()
                else:
                    success_count += 1
            finally:
                os.unlink(host_path)

        self._writable_workspace = writable_dir
        return {
            "success": len(errors) == 0,
            "writable_workspace": writable_dir,
            "written": success_count,
            "errors": errors,
        }

        
    def _find_project_root(self) -> str:
        """Walk up from project_path to find Dockerfile."""
        current = Path(self.project_path).resolve()
        for parent in [current] + list(current.parents):
            if (parent / "Dockerfile").exists():
                return str(parent)
        return str(current)  # fallback
         
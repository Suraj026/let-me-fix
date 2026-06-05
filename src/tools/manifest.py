"""
Utilities for parsing Python tracebacks and extracting file info.
"""

import os
from src.models.manifest import FileInfo

PYTHON_EXTENSIONS = {".py", ".pyw", ".pyx"}
NOTEBOOK_EXTENSIONS = ".ipynb"
SKIP_DIRS = {".venv", ".env", "__pycache__", "site-packages", "dist-packages", ".git", "node_modules"}

def detect_language(filename : str) -> str:
    """
    Detects the programming language of a file based on its extension.
    Currently supports Python files (.py, .pyw, .pyx) and Jupyter notebooks (.ipynb). 
    Returns "python" for Python files, "notebook" for Jupyter notebooks, and "unknown" for others.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in PYTHON_EXTENSIONS or ext == NOTEBOOK_EXTENSIONS:
        return "python"
    else:
        return "unknown"
    
def build_manifest(project_path : str) -> list[FileInfo]:
    """
    Recursively scans the project directory for Python files and builds a manifest of FileInfo objects.
    Skips common directories like virtual environments, __pycache__, .git, and node_modules.
    """
    manifest = []
    for root, dirs, files in os.walk(project_path):
        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.startswith("."):
                continue  # Skip hidden files
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, project_path)
            ext = os.path.splitext(f)[1].lower()

            manifest.append(
                FileInfo(
                    path = rel_path,
                    size = os.path.getsize(full_path),
                    is_notebook = (ext == NOTEBOOK_EXTENSIONS),
                    language = detect_language(f)
                )
            )
    
    manifest.sort(key = lambda x : x.path) # Sort manifest by path for consistency
    return manifest
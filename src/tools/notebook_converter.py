"""
This module provides a function to convert Jupyter notebooks (.ipynb) into Python code strings.
"""

import json
import os

def convert_notebook(notebook_path: str) -> str | None:
    """Convert .ipynb to Python code string. Returns None if conversion fails."""
    try:
        from nbconvert import PythonExporter
        exporter = PythonExporter()
        with open(notebook_path) as f:
            body, _ = exporter.from_notebook_node(
                json.load(f)
            ) if False else (None, None)
        # nbconvert expects a file path, not raw JSON
    except ImportError:
        return None
    # using nbformat + nbconvert properly
    import nbformat
    from nbconvert import PythonExporter
    with open(notebook_path) as f:
        nb = nbformat.read(f, as_version=4)
    exporter = PythonExporter()
    body, _ = exporter.from_notebook_node(nb)
    return body
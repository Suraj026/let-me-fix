"""
Tests for the manifest building functionality. 
"""

import pytest
from src.tools.manifest import detect_language, build_manifest

def test_build_manifest_type_error_corpus():
    files = build_manifest("tests/corpus/type_error")
    paths = [f.path for f in files]
    assert "main.py" in paths
    assert "test_main.py" in paths
    assert "trace.txt" in paths

def test_detect_language():
    assert detect_language("main.py") == "python"

def test_detect_language_notebook():
    # notebooks should be detected as python
    lang = detect_language("notebook.ipynb")
    assert lang == "python"

def test_manifest_skips_hidden():
    files = build_manifest("tests/corpus/type_error")
    hidden = [f for f in files if f.path.startswith(".")]
    assert len(hidden) == 0

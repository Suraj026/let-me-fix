import pytest
from src.tools.code_search import grep_files, find_function_references

def test_grep_finds_matches():
    results = grep_files("process_data", "tests/corpus/type_error")
    assert len(results) > 0
    assert any("process_data" in r["line"] for r in results)

def test_grep_no_match():
    results = grep_files("XYZZY_NONEXISTENT", "tests/corpus/type_error")
    assert len(results) == 0

def test_find_references():
    refs = find_function_references("process_data", "tests/corpus/type_error")
    assert len(refs) >= 1
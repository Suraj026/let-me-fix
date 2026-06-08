import pytest
from src.tools.tree_sitter_tools import (
    get_function_code, 
    get_function_signature, 
    extract_call_graph, 
    get_import_graph
)

def test_get_function_code():
    code = get_function_code("tests/corpus/type_error/main.py", "process_data")
    assert code is not None
    assert "def process_data" in code
    assert "return data * data" in code

def test_get_function_signature():
    signature = get_function_signature("tests/corpus/type_error/main.py", "process_data")
    assert signature is not None
    assert "process_data" in signature
    assert "data" in signature # parameter name should be in signature

def test_function_not_found():
    code = get_function_code("tests/corpus/type_error/main.py", "non_existent_function")
    assert code is None

def test_get_import_graph():
    imports = get_import_graph("tests/corpus/import_error/main.py")
    assert "utils" in imports
    assert "function" in imports["utils"]


def test_get_import_graph_no_imports():
    imports = get_import_graph("tests/corpus/import_error/utils.py")
    assert imports == {}

def test_extract_call_graph():
    call_graph = extract_call_graph("tests/corpus/type_error/main.py")
    assert call_graph is not None
    assert "process_data" in call_graph
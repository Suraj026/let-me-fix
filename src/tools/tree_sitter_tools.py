"""
This module provides tools for working with tree-sitter, a parser generator tool 
and an incremental parsing library. It allows you to build and use tree-sitter parsers 
for various programming languages (for now Python only)."""

import os
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor

# Build Python language object
PY_LANGUAGE = Language(tspython.language())

def _get_parser() -> Parser:
    """
    Create and return a tree-sitter parser.
    """
    parser = Parser(PY_LANGUAGE)
    return parser

def _read_file(path: str) -> str | None:
    """
    Read the contents of a file and return it as a string.
    Returns None if the file cannot be read.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def get_function_code(file_path: str, function_name: str) -> str | None:
    """
    Extract the code of a function from a Python file using tree-sitter.
    Returns the function code as a string, or None if not found.
    """
    source_code = _read_file(file_path)
    if source_code is None:
        return None

    parser = _get_parser()
    tree = parser.parse(bytes(source_code, "utf-8"))
    query = Query(PY_LANGUAGE, f"""
        (function_definition
            name: (identifier) @name
            (#eq? @name "{function_name}")
            body: (block) @body
        )
    """)
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    for _pattern_idx, captures_dict in matches:
        body_nodes = captures_dict.get("body", [])
        for body_node in body_nodes:
            func_node = body_node.parent  # function_definition
            if func_node and func_node.type == "function_definition":
                return source_code[func_node.start_byte:func_node.end_byte]

    return None  # Function not found


def get_function_signature(file_path: str, function_name: str) -> str | None:
    """
    Extract the signature of a function from a Python file using tree-sitter.
    Returns the function signature as a string, or None if not found.
    """
    source_code = _read_file(file_path)
    if source_code is None:
        return None

    parser = _get_parser()
    tree = parser.parse(bytes(source_code, "utf-8"))
    query = Query(PY_LANGUAGE, f"""
        (function_definition
            name: (identifier) @name
            (#eq? @name "{function_name}")
            parameters: (parameters) @params
        )
    """)
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    for _pattern_idx, captures_dict in matches:
        name_nodes = captures_dict.get("name", [])
        for node in name_nodes:
            func_node = node.parent  # function_definition
            if func_node and func_node.type == "function_definition":
                return source_code[func_node.start_byte:func_node.end_byte].split("\n")[0]

    return None  # Function not found


def extract_call_graph(file_path: str) -> dict[str, list[str]] | None:
    """
    Extract a call graph from a Python file using tree-sitter.
    Returns a dictionary mapping function names to lists of called functions.
    """
    source_code = _read_file(file_path)
    if source_code is None:
        return None

    parser = _get_parser()
    tree = parser.parse(bytes(source_code, "utf-8"))
    calls = {}

    # Find all function definitions
    query = Query(PY_LANGUAGE, """
        (function_definition
            name: (identifier) @name
        )
    """)
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    for _pattern_idx, captures_dict in matches:
        name_nodes = captures_dict.get("name", [])
        for node in name_nodes:
            func_name = source_code[node.start_byte:node.end_byte]
            calls[func_name] = []

            # Find all function calls within this function definition
            func_def = node.parent
            call_query = Query(PY_LANGUAGE, """
                (call
                    function: (identifier) @called_func
                )
            """)
            call_cursor = QueryCursor(call_query)
            call_matches = call_cursor.matches(func_def)

            for _call_pattern_idx, call_captures_dict in call_matches:
                called_nodes = call_captures_dict.get("called_func", [])
                for call_node in called_nodes:
                    called = source_code[call_node.start_byte:call_node.end_byte]
                    if called != func_name:  # avoid self-calls
                        calls[func_name].append(called)

    return calls
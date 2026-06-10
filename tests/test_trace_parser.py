from src.tools.trace_parser import parse_trace
from src.models.trace import ErrorSignature, ParsedTrace


def _read_corpus(name: str) -> str:
    path = f"tests/corpus/{name}/trace.txt"
    with open(path) as f:
        return f.read()


def test_parse_type_error():
    text = _read_corpus("type_error")
    result = parse_trace(text)

    assert result.error.type == "TypeError"
    assert "can't multiply" in result.error.message
    assert result.error.file.endswith("main.py")
    assert result.error.line == 2
    assert result.error.function == "process_data"
    assert len(result.traceback_lines) > 0
    assert result.raw_text == text


def test_parse_import_error():
    text = _read_corpus("import_error")
    result = parse_trace(text)

    assert result.error.type == "ImportError"
    assert "cannot import name" in result.error.message
    assert result.error.file.endswith("main.py")
    assert result.error.line == 1
    assert result.error.function == "<module>"
    assert len(result.traceback_lines) > 0
    assert result.raw_text == text
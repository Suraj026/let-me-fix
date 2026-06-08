import pytest
import tempfile
import shutil
from src.tools.chroma_store import ChromaStore
from src.models.manifest import FileInfo


@pytest.fixture
def store():
    tmpdir = tempfile.mkdtemp()
    s = ChromaStore(persist_directory=tmpdir)
    yield s
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_embed_and_query(store):
    files = [
        FileInfo(path="main.py", size=100, language="python"),
        FileInfo(path="utils.py", size=200, language="python"),
    ]
    file_contents = {
        "main.py": "def process_data(data):\n    return data * data",
        "utils.py": "def helper():\n    return 42",
    }
    store.index_files(files, file_contents)
    results = store.query("process_data function", n_results=2)
    assert len(results) > 0
    assert any("main.py" in r["path"] for r in results)


def test_query_empty_store(store):
    results = store.query("anything", n_results=5)
    assert len(results) == 0


def test_index_with_imports(store):
    files = [
        FileInfo(path="main.py", size=100, language="python"),
        FileInfo(path="utils.py", size=200, language="python"),
    ]
    file_contents = {
        "main.py": "from utils import helper\ndef run():\n    return helper()",
        "utils.py": "def helper():\n    return 42",
    }
    import_graphs = {
        "main.py": {"utils": ["helper"]},
        "utils.py": {},
    }
    store.index_files(files, file_contents, import_graphs=import_graphs)
    results = store.query("helper function", n_results=5)
    assert len(results) >= 1
    # Metadata should contain the import info
    main_meta = [r["metadata"] for r in results if r["path"] == "main.py"]
    if main_meta:
        assert "imports" in main_meta[0]


def test_find_related(store):
    files = [
        FileInfo(path="main.py", size=100, language="python"),
        FileInfo(path="utils.py", size=150, language="python"),
        FileInfo(path="unrelated.py", size=50, language="python"),
    ]
    file_contents = {
        "main.py": "from utils import helper\ndef run():\n    return helper()",
        "utils.py": "def helper():\n    return 42",
        "unrelated.py": "x = 1",
    }
    import_graphs = {
        "main.py": {"utils": ["helper"]},
        "utils.py": {},
        "unrelated.py": {},
    }
    store.index_files(files, file_contents, import_graphs=import_graphs)
    # Find files related to main.py
    related = store.find_related(["main.py"], n_results=3)
    assert any("utils.py" in r["path"] for r in related)
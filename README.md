# let-me-fix

**Autonomous debugging agent** — give it a Python traceback and a project, and it analyzes the error, gathers context, generates root cause hypotheses, produces a fix, and verifies it against your tests.

Built with a LangGraph pipeline of 6 specialized agents. Currently through Phase 2 (investigation → fix → verification) — Phase 3 will add Docker sandbox isolation.

## Quick Start

```bash
# Install
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Set your API key
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env

# Analyze a bug
let-me-fix analyze tests/corpus/type_error/trace.txt tests/corpus/type_error
```

## Architecture

Six agents connected in a LangGraph pipeline with conditional retry:

```
bug trace + project
      │
      ▼
┌────────────────────┐
│  1. Intake         │  Parse trace → extract error signature
│                    │  Scan project → build file manifest
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  2. Context        │  Read file contents (notebooks converted)
│                    │  Grep for error-related terms
│                    │  Tree-sitter analysis (imports, calls)
│                    │  ChromaDB semantic search
│                    │  Score files by relevance
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  3. Hypothesis     │  LLM analyzes error + context
│                    │  Produces 1-3 root cause hypotheses
│                    │  Each with confidence score & evidence
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  4. Investigation  │  Picks top hypothesis
│                    │  Gathers evidence from files
│                    │  Confirms or refutes root cause
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  5. Fix            │  LLM generates unified-diff patch
│                    │  Based on confirmed hypothesis
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  6. Verification   │  Applies patch via git-apply
│                    │  Runs project tests
│                    │  Retries fix up to 3x if tests fail
└─────────┬──────────┘
          │
     ┌────┴────┐
     │         │
   pass      fail
     │      ┌──┴──┐
     ▼      │     │
    end   retry  end
          (<3x)  (≥3x)
```

### Agent Details

**Agent 1 — Intake:**
- Parses Python tracebacks (extracts error type, message, file, line, function)
- Scans the project directory to build a manifest of files (detects Python, notebooks, etc.)

**Agent 2 — Context Collector:**
- Reads all project files (converts `.ipynb` notebooks to Python)
- Runs grep searches for terms extracted from the error message
- Uses tree-sitter for import graph and call graph analysis
- Indexes everything into ChromaDB for semantic similarity search
- Scores and ranks files by relevance to the error

**Agent 3 — Hypothesis Generator:**
- Sends the error signature + relevant file contents to an LLM (via OpenRouter)
- LLM returns structured JSON with 1-3 hypotheses
- Each hypothesis includes: description, confidence score, evidence files, verification steps
- Falls back to a heuristic hypothesis if the LLM is unavailable

**Agent 4 — Investigation:**
- Picks the highest-confidence hypothesis from Agent 3
- Reads evidence files referenced in the hypothesis
- Runs grep on hypothesis terms for additional supporting evidence
- Produces a confirmed hypothesis ready for fixing

**Agent 5 — Fix Generator:**
- Sends confirmed hypothesis + relevant file contents to an LLM
- LLM returns a unified-diff patch targeting the root cause
- Validates patch is non-empty and references real file paths

**Agent 6 — Verification:**
- Applies the patch using `git apply` (dry-run check first)
- Runs `pytest` to verify the fix doesn't break anything
- Supports retry loop: up to 3 attempts, regenerating fix each time
- Returns a verification report with pass/fail, test output, and exit code

### LLM Integration

Uses [OpenRouter](https://openrouter.ai/) with the `openrouter/free` endpoint (routes to the best available free model). Configurable model — set `MODEL` in `src/llm/model.py`.

- 120s timeout for long-running models
- Returns model name in metadata (shown in CLI summary)
- No local model required

## CLI Usage

```bash
# Analyze a trace file against a project
let-me-fix analyze trace.txt /path/to/project

# Get help
let-me-fix analyze --help

# Show version
let-me-fix version
```

Live streaming output shows each agent's progress in real time:
```
── 🔍 Intake ──
  [tool_call] Parsing bug trace...
  [milestone] Parsed TypeError: can't multiply sequence by non-int of type 'str'
  [tool_call] Scanning project: tests/corpus/type_error
  [milestone] Found 2 files in project

── 📁 Context ──
  [tool_call] Reading 2 files from project...
  [milestone] Read 2 files (0 notebooks converted)
  [thinking] Search terms derived from error: TypeError, can't, multiply...

── 💡 Hypothesis ──
  [thinking] Analyzing 2 relevant files for root cause hypotheses...
  [milestone] Generated 2 root cause hypotheses using openrouter/free

── 🔎 Investigation ──
  [milestone] Top hypothesis confirmed
  [tool_call] Evidence gathered from 2 files

── 🛠 Fix ──
  [milestone] Patch generated (12 lines)
  ── Patch Preview ──
  --- a/main.py
  +++ b/main.py
  @@ -5,7 +5,7 @@

── ✅ Verification ──
  [tool_call] Applying patch... ✓
  [tool_call] Running tests... ✓
  [milestone] All tests passed

══ Summary ══
Session: a1b2c3d4
Status: completed

Error: TypeError: can't multiply sequence by non-int of type 'str'

LLM Model: openrouter/free

Hypotheses (2):
  [85%] TypeError occurs in process_data at line...
    → Inspect the input passed to process_data()
    → Check the type of 'data' parameter

Investigation: 2 hypotheses evaluated, top: TypeError in process_data()
Fix: ✓ Applied
Verification: ✓ Passed
```

## Project Structure

```
src/
  agents/
    intake.py          # Agent 1: trace parsing + manifest building
    context.py         # Agent 2: file reading, grep, ChromaDB, scoring
    hypothesis.py      # Agent 3: LLM root cause hypothesis generation
    investigation.py   # Agent 4: picks top hypothesis, gathers evidence
    fix.py             # Agent 5: LLM generates unified-diff patch
    verification.py    # Agent 6: applies patch, runs tests, retry loop
  graph/
    state.py           # GraphState — Pydantic model for pipeline state
    graph.py           # LangGraph graph definition + streaming
  llm/
    model.py           # LLMClient — OpenRouter via httpx
  models/
    trace.py           # ErrorSignature, ParsedTrace
    manifest.py        # FileInfo, ScoredFile
    hypothesis.py      # Hypothesis, InvestigationResult
    events.py          # TraceEvent
  tools/
    trace_parser.py    # Regex-based Python traceback parser
    manifest.py        # Project file scanner
    notebook_converter.py  # Jupyter notebook → Python converter
    code_search.py     # grep-based file search
    tree_sitter_tools.py   # AST analysis (imports, calls, functions)
    chroma_store.py    # ChromaDB vector store wrapper
  cli.py               # Typer CLI with streaming output
  config.py            # API key loading (env var → config file)
tests/
  test_agent_intake.py           # Agent 1 tests
  test_agent_context.py          # Agent 2 tests
  test_agent_hypothesis.py       # Agent 3 tests
  test_agent_investigation.py    # Agent 4 tests
  test_agent_fix.py              # Agent 5 tests
  test_agent_verification.py     # Agent 6 tests
  test_graph.py                  # Pipeline integration (6-node topology + retry)
  test_integration.py            # End-to-end with real LLM (skipped by default)
  test_trace_parser.py           # Trace parser tests
  test_manifest.py               # Manifest builder tests
  test_code_search.py            # Grep tool tests
  test_tree_sitter_tools.py      # AST analysis tests
  test_chroma_store.py           # ChromaDB tests
  test_model.py                  # LLM client tests
  test_models.py                 # Pydantic model tests
  test_state.py                  # GraphState tests
  corpus/                        # Test fixtures (trace files + projects)
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | — (required) |

Key can be set via environment variable or a config file at `~/.let-me-fix/config` with the format `OPENROUTER_API_KEY=sk-or-v1-...`.

A `.env` file in the project root is also loaded automatically.

## Development

```bash
# Run all tests
venv/bin/python -m pytest

# Run with verbose output
venv/bin/python -m pytest -v

# Run a specific test file
venv/bin/python -m pytest tests/test_agent_intake.py -v

# Run the real LLM integration test (requires API key)
venv/bin/python -m pytest tests/test_integration.py -v
```

## Roadmap

- **Phase 1** — Agent pipeline — intake → context → hypothesis
- **Phase 2** — Investigation + fix generation + test verification (with retry)
- **Phase 3** — Docker sandbox for safe code execution (isolated patch test environment)
- **Phase 4** — Rich terminal UI (Textual)

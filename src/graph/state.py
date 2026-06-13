"""Pydantic model that holds all state as it passes through the graph nodes."""

from pydantic import BaseModel
from typing import Optional, Literal
from src.models.trace import ErrorSignature
from src.models.manifest import FileInfo, ScoredFile
from src.models.hypothesis import Hypothesis, InvestigationResult
from src.models.events import TraceEvent


class GraphState(BaseModel):
    """State that is passed through the graph nodes."""

    # Identifiers
    session_id: str = ""
    status: Literal["running", "completed", "failed"] = "running"

    # Input
    bug_trace: str = ""
    project_path: str = ""

    # Agent 1 output (Bug Intake)
    manifest: list[FileInfo] = []
    error_signature: Optional[ErrorSignature] = None

    # Agent 2 output (Context Collector)
    relevant_files: list[ScoredFile] = []
    chroma_collection_id: Optional[str] = None
    file_contents: dict[str, str] = {}

    # Agent 3 output (Hypothesis)
    hypotheses: list[Hypothesis] = []

    # Phase 4-5 (Investigation + Fix generation)
    investigation_results: list[InvestigationResult] = []
    confirmed_hypothesis: Optional[Hypothesis] = None
    fixed_files: dict[str, str] = {}  # filepath → corrected content (LLM output)

    # Phase 6 (Verification)
    patch_applied: bool = False
    verification: Optional[dict] = None
    retry_count: int = 0
    max_retries: int = 3
    report: Optional[str] = None
    use_sandbox: bool = True
    custom_command: Optional[str] = None
    custom_command_dir: Optional[str] = None
    
    # Streaming and error handling
    trace_events: list[TraceEvent] = []
    error: Optional[str] = None
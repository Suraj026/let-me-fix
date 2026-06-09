"""
Agent 3: Hypothesis Generator — analyzes bug context and produces root cause hypotheses.
"""
import re
from src.graph.state import GraphState
from src.models.hypothesis import Hypothesis
from src.models.events import TraceEvent
from src.llm.model import LLMClient

HYPOTHESIS_PROMPT = """You are a debugging expert. Given the following error and code context, 
identify 1-3 possible root causes for the bug.

For each hypothesis provide:
1. A clear description of what might be wrong
2. A confidence score (0.0 to 1.0)
3. The relevant files involved
4. Specific steps to verify or disprove this theory

Error: {error_type}: {error_message}
Error location: {error_file}:{error_line} in {error_function}

Relevant files:
{file_context}

Bug trace:
{trace}
"""

def _parse_hypotheses(llm_text : str, relevant_files: list) -> list[Hypothesis]:
    """Extract Hypothesis objects from LLM response using regex patterns."""
    
    hypotheses = []
    # Split on hypothesis boundaries
    parts = re.split(r"\n(?=Hypothesis \d+|^\d+\.\s)", llm_text.strip())
    for part in parts:
        if not part.strip():
            continue

        # Extract confidence
        conf_match = re.search(r"(?:Confidence|confidence)[:\s]*([0-9.]+)", part)
        confidence = float(conf_match.group(1)) if conf_match else 0.5
        confidence = max(0.0, min(1.0, confidence))

        # Extract evidence files
        evidence_files = set()
        for sf in relevant_files:
            if sf.file_info.path in part:
                evidence_files.add(sf.file_info.path)
        ev_match = re.search(r"(?:Evidence|evidence|File|file)[:\s]*([^\n]+)", part)
        if ev_match and not evidence_files:
            path = ev_match.group(1).strip()
            if path.endswith(".py"):
                evidence_files.add(path)

        # If no file references, use the top relevant file
        if not evidence_files and relevant_files:
            evidence_files.add(relevant_files[0].file_info.path)

        # Extract verification steps
        steps = []
        for line in part.split("\n"):
            line = line.strip()
            if re.search(r"(verify|check|run|test|assert|try)\b", line, re.IGNORECASE):
                steps.append(line.rstrip(". "))
        if not steps:
            steps.append("Inspect the relevant files for the root cause")

        description = part.strip()[:500]
        hypotheses.append(Hypothesis(
            id=f"h{len(hypotheses) + 1}",
            description=description,
            confidence=round(confidence, 2),
            evidence_files=sorted(list(evidence_files)),
            verification_steps=steps[:5],
        ))

    return hypotheses

def _build_fallback_hypothesis(error_sig, relevant_files) -> Hypothesis:
    """Create a sensible default hypothesis when LLM is unavailable."""
    file_paths = [sf.file_info.path for sf in relevant_files[:3]]
    location = ""
    if error_sig.file:
        location += f" in {error_sig.file}"
    if error_sig.line:
        location += f" at line {error_sig.line}"
    if error_sig.function:
        location += f" in function {error_sig.function}"
    description = (
        f"The error {error_sig.type} ('{error_sig.message[:100]}') occurred{location}. "
    )
    return Hypothesis(
        id="h_fallback",
        description=description,
        confidence=0.5,
        evidence_files=file_paths,
        verification_steps=[
            f"Inspect {error_sig.file or 'relevant files'} at line {error_sig.line or '?'}",
            "Check the types of values passed to the function",
            "Run the failing test to reproduce the error",
        ],
    )

def run_hypothesis(state: GraphState) -> dict:
    """Agent 3: Analyze context and produce 1-3 hypotheses about the root cause."""
    trace_events = list(state.trace_events)
    error_sig = state.error_signature
    relevant_files = state.relevant_files

    if not error_sig or not relevant_files:
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="error",
                content="No error signature or relevant files — run intake and context first.",
            )
        )
        return {
            "status": "failed",
            "error": "Hypothesis requires error signature and relevant files.",
            "trace_events": trace_events,
        }
    trace_events.append(
        TraceEvent(
            agent="hypothesis",
            event_type="milestone",
            content=f"Analyzing {len(relevant_files)} relevant files for root cause hypotheses..."
        )
    )

    # Build the context file for LLM
    file_context_lines = []
    for sf in relevant_files:
        path = sf.file_info.path
        score = sf.relevance_score
        reason = sf.match_reason
        file_context_lines.append(f"- {path} (relevance: {score:.2f}) — {reason}")
    file_context = "\n".join(file_context_lines)

    # Build prompt
    prompt = HYPOTHESIS_PROMPT.format(
        error_type=error_sig.type,
        error_message=error_sig.message[:200],
        error_file=error_sig.file or "unknown",
        error_line=error_sig.line or "?",
        error_function=error_sig.function or "?",
        file_context=file_context,
        trace=state.bug_trace[:1000],
    )

    # Call LLM
    try:
        llm = LLMClient()
        response = llm.generate(
            prompt=prompt,
            system="You are a debugging expert that produces structured root cause analysis.",
            temperature=0.3,
            max_tokens=2048,
        )
        llm.close()
    except Exception as e:
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="error",
                content=f"LLM call failed: {str(e)[:200]}. Using fallback hypothesis.",
            )
        )
        response = None

    hypotheses = []
    if response:
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="tool_result",
                content=f"LLM generated analysis ({len(response)} chars)",
            )
        )
        hypotheses = _parse_hypotheses(response, relevant_files)

    # Fallback: if parsing produced nothing or LLM failed, create a default hypothesis
    if not hypotheses:
        hypotheses.append(_build_fallback_hypothesis(error_sig, relevant_files))
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="milestone",
                content="Using fallback hypothesis (LLM unavailable or no structured output)",
            )
        )

    trace_events.append(
        TraceEvent(
            agent="hypothesis",
            event_type="milestone",
            content=f"Generated {len(hypotheses)} root cause hypotheses",
            metadata={"count": len(hypotheses)},
        )
    )

    return {
        "hypotheses": hypotheses,
        "status": "running",
        "trace_events": trace_events,
    }

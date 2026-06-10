"""
Agent 3: Hypothesis Generator — analyzes bug context and produces root cause hypotheses.
"""
import json
import re
from src.graph.state import GraphState
from src.models.hypothesis import Hypothesis
from src.models.events import TraceEvent
from src.llm.model import LLMClient

HYPOTHESIS_PROMPT = """You are a debugging expert. Given the following error and code context, identify 1-3 possible root causes for the bug.

Respond with ONLY valid JSON. No other text. Use this exact structure:
{{
  "hypotheses": [
    {{
      "description": "Clear explanation of what might be wrong and why",
      "confidence": X.XX,  # number between 0.0 and 1.0
      "evidence_files": ["path/to/file.py"],
      "verification_steps": ["Check line 10 in file.py for X", "Run command Y to reproduce"]
    }}
  ]
}}

Rules:
- confidence must be between 0.0 and 1.0
- evidence_files must be file paths from the relevant files list
- verification_steps should be concrete, actionable steps
- Output ONLY the JSON object, no commentary

Error: {error_type}: {error_message}
Error location: {error_file}:{error_line} in {error_function}

Relevant files:
{file_context}

Bug trace:
{trace}
"""


def _parse_hypotheses_json(llm_text: str, relevant_files: list) -> list[Hypothesis] | None:
    """Try to parse LLM response as JSON. Returns None if parsing fails."""
    try:
        # Strip markdown fences if present
        cleaned = llm_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        raw_hypotheses = data.get("hypotheses", [])
        if not raw_hypotheses:
            return None

        hypotheses = []
        valid_paths = {sf.file_info.path for sf in relevant_files}

        for i, raw in enumerate(raw_hypotheses):
            desc = raw.get("description", "").strip()
            if not desc:
                continue

            confidence = float(raw.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, round(confidence, 2)))

            evidence = raw.get("evidence_files", [])
            # Filter to only valid paths from our manifest
            evidence = [p for p in evidence if p in valid_paths]
            if not evidence and relevant_files:
                evidence.append(relevant_files[0].file_info.path)

            steps = raw.get("verification_steps", [])
            steps = [s.strip().rstrip(". ") for s in steps if s.strip()]
            if not steps:
                steps.append("Inspect the relevant files for the root cause")

            hypotheses.append(Hypothesis(
                id=f"h{i + 1}",
                description=desc[:500],
                confidence=confidence,
                evidence_files=sorted(evidence),
                verification_steps=steps[:5],
            ))

        return hypotheses if hypotheses else None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _parse_hypotheses_regex(llm_text: str, relevant_files: list) -> list[Hypothesis]:
    """Fallback: extract Hypothesis objects using regex patterns."""
    hypotheses = []
    parts = re.split(r"\n(?=Hypothesis \d+|^\d+\.\s)", llm_text.strip())
    for part in parts:
        if not part.strip():
            continue

        conf_match = re.search(r"(?:Confidence|confidence)[:\s]*([0-9.]+)", part)
        confidence = float(conf_match.group(1)) if conf_match else 0.5
        confidence = max(0.0, min(1.0, confidence))

        evidence_files = set()
        for sf in relevant_files:
            if sf.file_info.path in part:
                evidence_files.add(sf.file_info.path)
        ev_match = re.search(r"(?:Evidence|evidence|File|file)[:\s]*([^\n]+)", part)
        if ev_match and not evidence_files:
            path = ev_match.group(1).strip()
            if path.endswith(".py"):
                evidence_files.add(path)
        if not evidence_files and relevant_files:
            evidence_files.add(relevant_files[0].file_info.path)

        steps = []
        for line in part.split("\n"):
            line = line.strip()
            if re.search(r"(verify|check|run|test|assert|try)\b", line, re.IGNORECASE):
                steps.append(line.rstrip(". "))
        if not steps:
            steps.append("Inspect the relevant files for the root cause")

        hypotheses.append(Hypothesis(
            id=f"h{len(hypotheses) + 1}",
            description=part.strip()[:500],
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
        f"The error {error_sig.type} ('{error_sig.message}') occurred{location}. "
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
            content=f"Analyzing {len(relevant_files)} relevant files for root cause hypotheses...",
        )
    )

    # Build file context for LLM
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
        error_message=error_sig.message,
        error_file=error_sig.file or "unknown",
        error_line=error_sig.line or "?",
        error_function=error_sig.function or "?",
        file_context=file_context,
        trace=state.bug_trace,
    )

    # Call LLM
    llm_model = "none"
    response = None
    try:
        llm = LLMClient()
        llm_resp = llm.generate(
            prompt=prompt,
            system="You are a debugging expert. Output ONLY valid JSON with no other text.",
            temperature=0.2,
            max_tokens=2048,
        )
        llm_model = llm_resp.model or "unknown"
        response = llm_resp.text
        llm.close()
    except Exception as e:
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="error",
                content=f"LLM call failed: {str(e)}. Using fallback hypothesis.",
            )
        )

    hypotheses = []
    if response:
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="tool_result",
                content=f"LLM ({llm_model}) generated analysis ({len(response)} chars)",
                metadata={"model": llm_model},
            )
        )
        # Try JSON parsing first, fall back to regex
        hypotheses = _parse_hypotheses_json(response, relevant_files)
        if not hypotheses:
            hypotheses = _parse_hypotheses_regex(response, relevant_files)

    # Fallback if nothing parsed or LLM failed
    if not hypotheses:
        hypotheses.append(_build_fallback_hypothesis(error_sig, relevant_files))
        trace_events.append(
            TraceEvent(
                agent="hypothesis",
                event_type="milestone",
                content=f"Using fallback hypothesis (model: {llm_model})",
                metadata={"model": llm_model},
            )
        )

    trace_events.append(
        TraceEvent(
            agent="hypothesis",
            event_type="milestone",
            content=f"Generated {len(hypotheses)} root cause hypotheses using {llm_model}",
            metadata={"count": len(hypotheses), "model": llm_model},
        )
    )

    return {
        "hypotheses": hypotheses,
        "status": "running",
        "trace_events": trace_events,
    }

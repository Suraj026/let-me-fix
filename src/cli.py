import os
import sys
import typer
from dotenv import load_dotenv
from src.graph.graph import stream_pipeline

app = typer.Typer()

# helpers

def _print_trace_event(event) -> None:
    """Print a single trace event to stderr so it appears live."""
    content = event.content if len(event.content) <= 400 else event.content[:400] + "..."
    msg = f"  [{event.event_type}] {content}"
    print(msg, file=sys.stderr)


def _print_error_signature(sig) -> None:
    if sig:
        typer.echo(f"\nError: {sig.type}: {sig.message}")


def _print_hypotheses(hypotheses) -> None:
    if hypotheses:
        typer.echo(f"\nHypotheses ({len(hypotheses)}):")
        for h in hypotheses:
            typer.echo(f"  [{h.confidence:.0%}] {h.description}")
            for step in h.verification_steps:
                typer.echo(f"    → {step}")


NODE_LABELS = {
    "intake": "🔍 Intake",
    "context_collector": "📁 Context",
    "hypothesis": "💡 Hypothesis",
}

# commands 

@app.command()
def analyze(
    trace: str = typer.Argument(..., help="Bug trace text or path to trace file"),
    project: str = typer.Argument(".", help="Path to the project to analyze"),
):
    """Analyze a bug trace and project to find root cause hypotheses."""
    load_dotenv(override=True)

    # Read trace from file if it's a file path
    if os.path.isfile(trace):
        with open(trace) as f:
            trace_text = f.read()
    else:
        trace_text = trace

    typer.echo(f"Analyzing bug in {project}...\n")

    result = None
    seen_events = 0  # track already-printed events to avoid duplicates

    for node_name, updates in stream_pipeline(trace_text, project):
        if node_name == "final":
            result = updates
            break

        label = NODE_LABELS.get(node_name, node_name)
        typer.echo(f"── {label} ──")

        # Print only new trace events from this node
        trace_events = updates.get("trace_events", [])
        for te in trace_events[seen_events:]:
            _print_trace_event(te)
        seen_events = len(trace_events)

        typer.echo("")  # blank line between nodes

    ## Final summary 
    if not result:
        typer.echo("Pipeline completed without returning final state.")
        raise typer.Exit(1)

    typer.echo("══ Summary ══")
    typer.echo(f"Session: {result.session_id}")
    typer.echo(f"Status: {result.status}")

    # Extract model info from hypothesis agent's trace events
    model_name = "unknown"
    for te in result.trace_events:
        if te.agent == "hypothesis" and te.metadata and "model" in te.metadata:
            model_name = te.metadata["model"]

    _print_error_signature(result.error_signature)

    typer.echo(f"\nLLM Model: {model_name}")

    _print_hypotheses(result.hypotheses)

    if result.error and not result.hypotheses:
        typer.echo(f"\nError: {result.error}")

@app.command()
def version():
    """Show version."""
    typer.echo("let-me-fix v0.1.0")


if __name__ == "__main__":
    app()
import os
import sys
import typer
from dotenv import load_dotenv
from src.graph.graph import stream_pipeline

app = typer.Typer()

# helpers

def _print_trace_event(event) -> None:
    """Print a single trace event to stderr so it appears live."""
    content = event.content 
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

def _print_fixed_files_preview(fixed_files: dict[str, str]) -> None:
    """Print the corrected file contents."""
    for fpath, content in fixed_files.items():
        lines = content.strip().splitlines()
        typer.echo(f"  Corrected {fpath} ({len(lines)} lines):")
        typer.echo("  ─" * 20)
        for line in content.splitlines():
            typer.echo(f"  {line}")
        typer.echo("  ─" * 20)

def _print_verification_result(verification) -> None:
    """Print verification result."""
    if not verification:
        return
    success = verification.get("success")
    exit_code = verification.get("exit_code")
    test_output = verification.get("test_output", "")

    if success:
        typer.echo("  ✅ All tests passed")
    else:
        typer.echo(f"  ❌ Tests failed (exit {exit_code})")
        # Show test output on failure
        if test_output:
            lines = test_output.splitlines()
            for line in lines:
                typer.echo(f"    {line}")

    # Print custom command output if present
    custom_output = verification.get("custom_output")
    if custom_output:
        typer.echo("")
        typer.echo("  Custom command output:")
        for line in custom_output.splitlines():
            typer.echo(f"    {line}")




NODE_LABELS = {
    "intake": "🔍 Intake",
    "context_collector": "📁 Context",
    "hypothesis": "💡 Hypothesis",
    "investigation": "🔎 Investigation",
    "fix": "🛠 Fix",
    "verification": "✅ Verification",
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

    typer.echo(f"Analyzing bug in {project}...")

    # Optional: custom sandbox command to run after fix is applied
    custom_command = typer.prompt(
        "Custom command to run in sandbox after fix (or Enter to skip)",
        default="",
        show_default=False,
    )
    custom_command_dir = ""
    if custom_command:
        custom_command_dir = typer.prompt(
            "Working directory inside project (relative, or Enter for root)",
            default="",
            show_default=False,
        )
    typer.echo("")

    result = None
    seen_events = 0  # track already-printed events to avoid duplicates

    for node_name, updates in stream_pipeline(
        trace_text, project,
        custom_command=custom_command or None,
        custom_command_dir=custom_command_dir or None,
    ):
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

        # Print fixed files preview when fix node runs
        if node_name == "fix" and updates.get("fixed_files"):
            _print_fixed_files_preview(updates["fixed_files"])

        # Print verification result when verification node runs
        if node_name == "verification" and updates.get("verification"):
            _print_verification_result(updates["verification"])

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

     # Investigation result
    if result.investigation_results:
        top_desc = result.confirmed_hypothesis.description if result.confirmed_hypothesis else "confirmed"
        typer.echo(f"\nInvestigation: {len(result.investigation_results)} evaluated, top: {top_desc}")
    elif result.confirmed_hypothesis:
        typer.echo(f"\nInvestigation: {result.confirmed_hypothesis.description}")

    # Fix result — show corrected code
    if result.fixed_files:
        for fpath, content in result.fixed_files.items():
            lines = content.strip().splitlines()
            typer.echo(f"\nFix: ✓ {fpath} corrected ({len(lines)} lines)")
            typer.echo("  " + "─" * 40)
            for line in content.splitlines():
                typer.echo(f"  {line}")
            typer.echo("  " + "─" * 40)

    # Verification result
    if result.verification:
        v = result.verification
        if v.get("success"):
            typer.echo("Verification: ✓ Passed")
        else:
            typer.echo(f"Verification: ✗ Failed (exit {v.get('exit_code')})")
            # Show last few lines of test output in summary
            output = v.get("test_output", "")
            if output:
                lines = output.strip().splitlines()
                tail = lines[-5:] if len(lines) > 5 else lines
                typer.echo("  Last test output:")
                for line in tail:
                    typer.echo(f"    {line}")

        # Show custom command output in summary
        custom_output = v.get("custom_output")
        if custom_output:
            typer.echo("")
            typer.echo("  Custom command output:")
            lines = custom_output.strip().splitlines()
            tail = lines[-10:] if len(lines) > 10 else lines
            for line in tail:
                typer.echo(f"    {line}")

    if result.error and not result.hypotheses:
        typer.echo(f"\nError: {result.error}")

    # Ask user if they want to apply the fix to their original project files
    if result.fixed_files and result.verification and result.verification.get("success"):
        typer.echo("")
        if typer.confirm("Apply these changes to the original project?", default=False):
            written = 0
            errors: list[str] = []
            project = result.project_path
            for fpath, content in result.fixed_files.items():
                target = os.path.join(project, fpath)
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, 'w') as f:
                        f.write(content)
                    written += 1
                except (OSError, FileNotFoundError) as e:
                    errors.append(f"{fpath}: {e}")
            typer.echo(f"  ✓ {written} file(s) written to project")
            for err in errors:
                typer.echo(f"  ✗ {err}")
        else:
            typer.echo("  Files not overwritten (sandbox-only changes)")

@app.command()
def version():
    """Show version."""
    typer.echo("let-me-fix v0.1.0")


if __name__ == "__main__":
    app()
"""Agent 6: Overwrites corrected files (from LLM) in sandbox and runs verification command."""

import os
import subprocess
from src.graph.state import GraphState
from src.models.events import TraceEvent
from src.tools.sandbox import DockerSandbox


def _run_custom_command(sandbox, state, trace_events, writable_workspace: str | None = None) -> tuple[bool, str, int, str | None]:
    """Run the user's custom command (or pytest as default) inside the sandbox.

    Returns ``(success, output, exit_code, custom_output)``.
    """
    # Determine the command to run
    command = state.custom_command or "python3 -m pytest -x --tb=short"
    custom_dir = state.custom_command_dir or "."

    # Resolve workdir — use writable workspace if available, otherwise /workspace
    base_dir = writable_workspace or "/workspace"
    workdir = base_dir
    if custom_dir != "." and custom_dir != "/workspace":
        candidate = f"{base_dir}/{custom_dir.lstrip('/')}"
        # Ensure the directory exists inside the container
        check = sandbox.exec_run(["test", "-d", candidate])
        if check["exit_code"] == 0:
            workdir = candidate
        else:
            # Fall back to base_dir and log a warning
            trace_events.append(
                TraceEvent(
                    agent="verification",
                    event_type="error",
                    content=f"Workdir '{candidate}' not found in sandbox, using {base_dir} instead"
                )
            )

    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="tool_call",
            content=f"Running command: {command} (workdir: {workdir})"
        )
    )

    cmd_result = sandbox.exec_run(
        ["sh", "-c", command],
        timeout=60,
        workdir=workdir
    )
    exit_code = cmd_result.get("exit_code", -1)
    output = cmd_result.get("output", "")
    success = exit_code == 0

    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="milestone",
            content=f"Command {'succeeded' if success else 'failed'} (exit {exit_code})"
        )
    )
    # Only return custom_output separately if the user explicitly provided a command
    custom_output = output if state.custom_command else None
    return success, output, exit_code, custom_output


def _run_custom_command_direct(state, trace_events, work_dir: str | None = None) -> tuple[bool, str, int, str | None]:
    """Run verification command directly on host (no sandbox).
    
    Args:
        work_dir: If set, use this as the base directory instead of state.project_path.
    """
    command = state.custom_command or "python3 -m pytest -x --tb=short"
    custom_dir = state.custom_command_dir or "."
    base = work_dir or state.project_path
    workdir = os.path.join(base, custom_dir) if custom_dir != "." else base

    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="tool_call",
            content=f"Running command: {command} (workdir: {workdir})"
        )
    )

    try:
        result = subprocess.run(
            ["sh", "-c", command],
            capture_output=True, text=True, timeout=60,
            cwd=workdir,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        trace_events.append(
            TraceEvent(agent="verification", event_type="error", content=f"Command failed: {str(e)}")
        )
        return False, str(e), -1, str(e) if state.custom_command else None

    exit_code = result.returncode
    output = (result.stdout + result.stderr).strip()
    success = exit_code == 0

    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="milestone",
            content=f"Command {'succeeded' if success else 'failed'} (exit {exit_code})"
        )
    )
    custom_output = output if state.custom_command else None
    return success, output, exit_code, custom_output


def _verify_fixed_files_sandbox(state, trace_events, retry_count) -> dict:
    """Write corrected files into a Docker sandbox and run the verification command."""
    try:
        with DockerSandbox(state.project_path) as sandbox:
            # Write corrected files into the container
            trace_events.append(
                TraceEvent(
                    agent="verification",
                    event_type="tool_call",
                    content=f"Writing {len(state.fixed_files)} corrected file(s) to sandbox..."
                )
            )
            write_result = sandbox.write_files(state.fixed_files)
            if not write_result["success"]:
                err_msg = "; ".join(f"{p}: {e}" for p, e in write_result["errors"].items())
                trace_events.append(
                    TraceEvent(
                        agent="verification",
                        event_type="error",
                        content=f"Failed to write files: {err_msg}"
                    )
                )
                return {
                    "patch_applied": False,
                    "verification": {
                        "success": False,
                        "test_output": f"File write errors: {err_msg}",
                        "exit_code": -1,
                    },
                    "retry_count": retry_count,
                    "trace_events": trace_events,
                }

            trace_events.append(
                TraceEvent(
                    agent="verification",
                    event_type="milestone",
                    content=f"Wrote {write_result['written']} file(s) to sandbox."
                )
            )

            # Run the verification command in the writable workspace
            writable_workspace = write_result.get("writable_workspace")
            success, output, exit_code, custom_output = _run_custom_command(
                sandbox, state, trace_events, writable_workspace=writable_workspace
            )

            verification_data = {
                "success": success,
                "test_output": output,
                "exit_code": exit_code,
            }
            if custom_output is not None:
                verification_data["custom_output"] = custom_output

            updates = {
                "patch_applied": success,
                "verification": verification_data,
                "retry_count": retry_count,
                "trace_events": trace_events,
            }
            if not success:
                updates["status"] = "running"
            return updates

    except Exception as e:
        trace_events.append(
            TraceEvent(
                agent="verification",
                event_type="error",
                content=f"Docker sandbox error: {str(e)}"
            )
        )
        return {
            "patch_applied": False,
            "verification": {
                "success": False,
                "test_output": str(e),
                "exit_code": -1,
            },
            "retry_count": retry_count,
            "trace_events": trace_events,
        }


def _verify_fixed_files_direct(state, trace_events, retry_count) -> dict:
    """Write corrected files to a temp directory and run verification command.
    
    Never touches the original project files — the CLI prompts the user before overwriting.
    """
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="let-me-fix-verify-")
    errors: list[str] = []
    written = 0
    for fpath, content in state.fixed_files.items():
        target = os.path.join(work_dir, fpath)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w') as f:
                f.write(content)
            written += 1
        except (OSError, FileNotFoundError) as e:
            errors.append(f"{fpath}: {e}")

    if errors:
        err_msg = "; ".join(errors)
        trace_events.append(
            TraceEvent(
                agent="verification",
                event_type="error",
                content=f"Failed to write files: {err_msg}"
            )
        )
        return {
            "patch_applied": False,
            "verification": {
                "success": False,
                "test_output": f"File write errors: {err_msg}",
                "exit_code": -1,
            },
            "retry_count": retry_count,
            "trace_events": trace_events,
        }

    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="milestone",
            content=f"Wrote {written} corrected file(s) to temp dir ({work_dir})."
        )
    )

    success, output, exit_code, custom_output = _run_custom_command_direct(state, trace_events, work_dir=work_dir)

    verification_data = {
        "success": success,
        "test_output": output,
        "exit_code": exit_code,
    }
    if custom_output is not None:
        verification_data["custom_output"] = custom_output

    updates = {
        "patch_applied": success,
        "verification": verification_data,
        "retry_count": retry_count,
        "trace_events": trace_events,
    }
    if not success:
        updates["status"] = "running"
    return updates


def run_verification(state: GraphState) -> dict:
    """Write corrected files and run verification command."""
    trace_events = list(state.trace_events)
    retry_count = state.retry_count + 1

    if not state.fixed_files:
        trace_events.append(
            TraceEvent(
                agent="verification",
                event_type="error",
                content="No fixed files provided to verify."
            )
        )
        return {
            "retry_count": retry_count,
            "verification": {"success": False, "test_output": "No fix to verify.", "exit_code": -1},
            "trace_events": trace_events,
            "status": "failed",
            "error": "No fix to verify.",
        }

    if getattr(state, "use_sandbox", True):
        return _verify_fixed_files_sandbox(state, trace_events, retry_count)
    else:
        return _verify_fixed_files_direct(state, trace_events, retry_count)
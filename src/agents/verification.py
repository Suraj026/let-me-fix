"""Agent 6: Applies the fix patch and runs project tests to verify."""

import os
import subprocess
import tempfile
from src.graph.state import GraphState
from src.models.events import TraceEvent

def run_verification(state: GraphState) -> dict:
    """Run the verification agent."""
    updates = {}
    trace_events = list(state.trace_events)
    patch = state.patch

    if not patch or not patch.strip():
        trace_events.append(
            TraceEvent(
                agent="verification",
                event_type="error",
                content="No patch provided to apply."
            )
        )
        updates["trace_events"] = trace_events
        updates["status"] = "failed"
        updates["error"] = "Verification requires a non-empty patch to apply."
        return updates
    
    # Write patch to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as f:
        f.write(patch)
        patch_path = f.name
    project_path = state.project_path
    retry_count = state.retry_count + 1 

    # try to apply patch
    trace_events.append(
        TraceEvent(
            agent="verification",
            event_type="tool_call",
            content=f"Applying patch..."
        )
    )

    try:
        # Dry run first
        dry_run = subprocess.run(
            ["git", "apply", "--check", patch_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_path
        )
        if dry_run.returncode != 0:
            trace_events.append(
                TraceEvent(
                    agent="verification",
                    event_type="error",
                    content=f"Patch check failed: {dry_run.stderr.strip()}"
                )
            )
            updates["patch_applied"] = False
            updates["verification"] = {
                "success": False,
                "test_output": dry_run.stderr.strip(),
                "exit_code": dry_run.returncode
            }
            updates["retry_count"] = retry_count
            updates["trace_events"] = trace_events
            return updates
        
        # Apply patch
        result = subprocess.run(
            ["git", "apply", patch_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_path
        )
        patch_applied = result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        trace_events.append(
            TraceEvent(
                agent="verification",
                event_type="error",
                content=f"Patch apply failed: {str(e)}"
            )
        )
        updates["patch_applied"] = False
        updates["verification"] = {
            "success": False,
            "test_output": str(e),
            "exit_code": -1
        }
        updates["retry_count"] = retry_count
        updates["trace_events"] = trace_events
        return updates
    
    finally:
        # clean up temp file
        try:
            os.unlink(patch_path)
        except OSError:
            pass

    if not patch_applied:
        trace_events.append(TraceEvent(
            agent="verification", event_type="error",
            content="git apply failed."
        ))
        updates["patch_applied"] = False
        updates["verification"] = {
            "success": False,
            "test_output": result.stderr,
            "exit_code": result.returncode,
        }
        updates["retry_count"] = retry_count
        updates["trace_events"] = trace_events
        return updates

    trace_events.append(
        TraceEvent(
            agent="verification", 
            event_type="milestone",
            content="Patch applied successfully."
        )
    )

    # Run tests
    trace_events.append(
        TraceEvent(
            agent="verification", event_type="tool_call",
            content="Running tests..."
        )
    )
    try:
        test_result = subprocess.run(
            ["python", "-m", "pytest"],
            capture_output=True, 
            text=True, 
            timeout=60,
            cwd=project_path,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        trace_events.append(TraceEvent(
            agent="verification", 
            event_type="error",
            content=f"Test run failed: {str(e)}"
            )
        )
        updates["patch_applied"] = True
        updates["verification"] = {
            "success": False,
            "test_output": str(e),
            "exit_code": -1,
        }
        updates["retry_count"] = retry_count
        updates["trace_events"] = trace_events
        return updates

    success = test_result.returncode == 0
    trace_events.append(
        TraceEvent(
            agent="verification", 
            event_type="milestone",
            content=f"Tests {'passed' if success else 'failed'} (exit {test_result.returncode})"
        )
    )

    updates["patch_applied"] = True
    updates["verification"] = {
        "success": success,
        "test_output": test_result.stdout + test_result.stderr,
        "exit_code": test_result.returncode,
    }
    updates["retry_count"] = retry_count
    updates["trace_events"] = trace_events

    if not success:
        updates["status"] = "running"  # let graph decide retry
    return updates
"""
Trace parser for handling and analyzing execution traces.
"""

import re
from src.models.trace import ErrorSignature, ParsedTrace

# Matches - File "path", line N, in func
FRAME_PATTERN = re.compile(r'  File "(.+?)", line (\d+)(?:, in (.+))?')

# Matches - ErrorType: message
ERROR_PATTERN = re.compile(r'^(\w+(?:\.\w+)*): (.+)$')


def parse_trace(raw_text: str) -> ParsedTrace | None:
    """
    Parses a raw Python traceback and returns structured info.

    Works by scanning lines from bottom to top:
    1. Last non-empty line -> error type and message
    2. Walk upwards -> find last frame (file, line, function)
    3. Collect all frame lines for traceback_lines

    Returns None if the trace can't be parsed (no error line found).
    """
    lines = raw_text.strip().split("\n")
    if not lines or not lines[0]:
        return None

    # Find error type and message from the last non-empty line 
    error_line = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            error_line = lines[i]
            break

    if not error_line:
        return None

    error_match = ERROR_PATTERN.match(error_line.strip())
    if not error_match:
        # Couldn't find "ErrorType: message" pattern
        return None

    error_type = error_match.group(1)
    error_message = error_match.group(2)

    # Walk backwards to find the last frame 
    file_path = None
    line_no = None
    func_name = None

    for j in range(len(lines) - 2, -1, -1):  # Start one line above the error
        frame_match = FRAME_PATTERN.match(lines[j])
        if frame_match:
            file_path = frame_match.group(1)
            line_no = int(frame_match.group(2))
            func_name = frame_match.group(3)  # Can be None
            break

    # Collect all traceback frame lines 
    traceback_lines = []
    for line in lines:
        if FRAME_PATTERN.match(line):
            traceback_lines.append(line)

    return ParsedTrace(
        error=ErrorSignature(
            type=error_type,
            message=error_message,
            file=file_path,
            line=line_no,
            function=func_name,
        ),
        traceback_lines=traceback_lines,
        raw_text=raw_text,
    )
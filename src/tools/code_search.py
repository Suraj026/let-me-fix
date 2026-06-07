"""
grep-like file search: find lines matching a regex across project files.
"""

import os
import re
from src.models.manifest import FileInfo

def grep_files(pattern : str, project_path : str, file_pattern : str = "*.py") -> list[dict]:
    """
    Search for lines matching the regex pattern across project files.
    Only searches files matching the file_pattern (default: *.py).
    Returns a list of dicts with file path, line number, and matched line.
    """
    results = []
    for root, dirs, files in os.walk(project_path):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            try :
                with open(path) as file:
                    for i, line in enumerate(file, start = 1):
                        if re.search(pattern, line):
                            results.append({
                                "file": os.path.relpath(path, project_path),
                                "line": line.strip(),
                                "line_number": i
                            })
            except (OSError, UnicodeDecodeError):
                continue  # Skip files that can't be read
    return results

def find_function_references(function_name : str, project_path : str) -> list[dict]:
    """
    Search for references to a function across project files.
    Returns a list of dicts with file path, line number, and matched line.
    """
    results = []
    for root, dirs, files in os.walk(project_path):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            try :
                with open(path) as file:
                    for i, line in enumerate(file, start = 1):
                        if function_name in line:
                            results.append({
                                "file": os.path.relpath(path, project_path),
                                "line": line.strip(),
                                "line_number": i
                            })
            except (OSError, UnicodeDecodeError):
                continue  # Skip files that can't be read
    return results

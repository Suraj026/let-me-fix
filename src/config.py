"""Configuration loading — env var first, then config file fallback."""

import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".let-me-fix"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config"

def get_openrouter_api_key(var: str) -> str:
    """Load api key from env var, fall back to config file.

    Config file format: KEY=value.
    """
    key = os.environ.get(var)
    if key:
        return key.strip()
    if CONFIG_FILE.exists():
         for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{var}="):
                return line.split("=", 1)[1]
    return ""


    
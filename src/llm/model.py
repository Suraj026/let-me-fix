"""OpenRouter LLM client wrapper for moonshotai/kimi-k2.6:free.
Uses OpenAI-compatible API format over httpx.
API key loaded from OPENROUTER_API_KEY env var.
"""

import httpx
from typing import Optional
from src.models.hypothesis import Hypothesis
from src.config import get_openrouter_api_key

MODEL = "moonshotai/kimi-k2.6:free"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
TIMEOUT = 60.0

SYSTEM_PROMPT = """You are a debugging assistant that analyzes software bugs.
Given error traces and code context, you identify possible root causes.
Be specific. Reference file paths and line numbers.
Output your analysis as plain text with clear sections."""

class LLMClient:
    """Wrapper around OpenRouter API for LLM calls."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_openrouter_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key is required. Set OPENROUTER_API_KEY env var.")
        self.client = httpx.Client(
            base_url=OPENROUTER_BASE,
            timeout=TIMEOUT,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

    def generate(self, 
                 prompt : str, 
                 system : Optional[str] = None, 
                 temperature : float = 0.2, 
                 max_tokens : int = 2048
                ) -> str:
        """Generate text from prompt using OpenRouter API."""
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system or SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = self.client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def close(self):
        self.client.close()

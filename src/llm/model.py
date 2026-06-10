"""OpenRouter LLM client wrapper using openrouter/free routing.
Uses OpenAI-compatible API format over httpx.
API key loaded from OPENROUTER_API_KEY env var.
"""

import httpx
from typing import Optional
from dataclasses import dataclass
from src.models.hypothesis import Hypothesis
from src.config import get_openrouter_api_key

MODEL = "openrouter/free"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
TIMEOUT = 120.0

SYSTEM_PROMPT = """You are a debugging assistant that analyzes software bugs.
Given error traces and code context, you identify possible root causes.
Be specific. Reference file paths and line numbers.
Output your analysis as plain text with clear sections."""


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    text: str
    model: str = ""
    usage: Optional[dict] = None


class LLMClient:
    """Wrapper around OpenRouter API for LLM calls."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_openrouter_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key is required. Set OPENROUTER_API_KEY env var.")
        self.last_model: str = MODEL
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
                ) -> LLMResponse:
        """Generate text from prompt using OpenRouter API. Returns LLMResponse."""
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
        self.last_model = data.get("model", MODEL)
        return LLMResponse(
            text=data["choices"][0]["message"]["content"].strip(),
            model=self.last_model,
            usage=data.get("usage"),
        )

    def close(self):
        self.client.close()

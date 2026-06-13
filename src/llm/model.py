"""OpenRouter LLM client wrapper using openrouter/free routing.
Uses OpenAI-compatible API format over httpx.
API key loaded from OPENROUTER_API_KEY env var.
"""

import httpx
import time
import random
from typing import Optional
from dataclasses import dataclass
from src.models.hypothesis import Hypothesis
from src.config import get_openrouter_api_key

MODEL = "openai/gpt-oss-120b:free"
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
                 max_tokens : int = 2048,
                 max_retries : int = 3,
                ) -> LLMResponse:
        """Generate text from prompt using OpenRouter API. Returns LLMResponse.

        Retries on 429 rate-limit responses with exponential backoff + jitter.
        """
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system or SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            resp = self.client.post("/chat/completions", json=body)
            # Retry on any 5xx / 429 (server errors, rate limits, upstream failures)
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                reason = "Rate limited" if resp.status_code == 429 else f"Upstream error ({resp.status_code})"
                last_error = httpx.HTTPStatusError(
                    f"{reason} (attempt {attempt + 1}/{max_retries})",
                    request=resp.request,
                    response=resp,
                )
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.random()
                    time.sleep(wait)
                    continue
                raise last_error
            resp.raise_for_status()

            # OpenRouter can return 200 with an error payload when the
            # upstream model is overloaded — check for that.
            data = resp.json()
            if "error" in data:
                err = data["error"]
                last_error = RuntimeError(
                    f"API error: {err.get('message', str(err))} (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.random()
                    time.sleep(wait)
                    continue
                raise last_error

            choices = data.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                last_error = RuntimeError(
                    f"API response missing choices (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.random()
                    time.sleep(wait)
                    continue
                raise last_error

            self.last_model = data.get("model", MODEL)
            content = choices[0]["message"]["content"]
            if not content:
                return LLMResponse(text="", model=self.last_model)
            return LLMResponse(
                text=content.strip(),
                model=self.last_model,
                usage=data.get("usage"),
            )

        # Shouldn't reach here — last_error should have been raised
        raise last_error or RuntimeError("LLM generation failed after all retries")

    def close(self):
        self.client.close()

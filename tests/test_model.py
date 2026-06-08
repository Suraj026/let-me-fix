"""Tests for LLM client. Only tests construction — real calls need an API key."""

import pytest
from src.llm.model import LLMClient


def test_llm_client_requires_key():
    """Construction without API key and without env var should raise."""
    with pytest.raises(ValueError, match="OpenRouter API key is required"):
        LLMClient(api_key="")


def test_llm_client_accepts_key():
    """Providing an API key directly should succeed."""
    client = LLMClient(api_key="sk-test-key")
    assert client.api_key == "sk-test-key"
    assert client.client is not None
    client.close()


@pytest.mark.skip(reason="Requires a real OPENROUTER_API_KEY in environment")
def test_real_generate():
    """Integration test — run manually with a real key."""
    client = LLMClient()
    result = client.generate("Say 'hello' and nothing else.")
    assert isinstance(result, str)
    assert len(result) > 0
    client.close()
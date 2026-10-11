import os
from app.llms.base import LLMClient
from app.llms.mock_client import MockLLMClient
from app.llms.anthropic_client import AnthropicClient


def get_llm_client() -> LLMClient:
    backend = os.environ.get("LLM_BACKEND", "mock").lower()

    if backend == "anthropic":
        return AnthropicClient()
    else:
        return MockLLMClient()
import os
from app.llms.base import LLMClient
from app.llms.mock_client import MockLLMClient


def get_llm_client(backend=None, api_key=None, model=None) -> LLMClient:
    backend = (backend or os.environ.get("LLM_BACKEND", "mock")).lower()

    if backend == "anthropic":
        from app.llms.anthropic_client import AnthropicClient
        return AnthropicClient()
    if backend == 'openai':
        from app.llms.openai_client import OpenAIClient
        return OpenAIClient(model=model, api_key=api_key)
    if backend == 'mock':
        return MockLLMClient()
    raise ValueError(f'Unsupported LLM backend: {backend}. Choose mock, openai, or anthropic.')

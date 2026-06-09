"""Shared LLM factory for all agents.

Prefers the official OpenAI API (`OPENAI_API_KEY`) and keeps OpenRouter as an
OpenAI-compatible fallback (`OPENROUTER_API_KEY`).
"""

import os

from langchain_openai import ChatOpenAI


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value and value != "your_key_here":
            return value
    return ""


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI client configured from environment variables.

    Supported key names:
    - OPENAI_API_KEY: official OpenAI API key, preferred
    - OPENAI_KEY_API / OPENAI_KEY: accepted aliases for local student configs
    - OPENROUTER_API_KEY: OpenRouter fallback
    """
    openai_key = _first_env("OPENAI_API_KEY", "OPENAI_KEY_API", "OPENAI_KEY")
    openrouter_key = _first_env("OPENROUTER_API_KEY")
    api_key = openai_key or openrouter_key
    if not api_key:
        raise RuntimeError(
            "Missing API key. Set OPENAI_API_KEY in .env "
            "(or OPENROUTER_API_KEY if you want to use OpenRouter)."
        )

    if openai_key:
        model = _first_env("OPENAI_MODEL") or "gpt-4o-mini"
        base_url = _first_env("OPENAI_BASE_URL")
    else:
        model = _first_env("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4-5"
        base_url = _first_env("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"

    kwargs = {
        "model": model,
        "openai_api_key": api_key,
    }
    if base_url:
        kwargs["openai_api_base"] = base_url

    return ChatOpenAI(**kwargs)

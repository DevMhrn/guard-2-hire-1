"""LLM factories. Use these — do not construct ChatAnthropic / ChatGroq directly."""
from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from hireguard.settings import require, settings


@lru_cache(maxsize=4)
def get_claude(model: str = "claude-sonnet-4-5-20250929", temperature: float = 0.1) -> BaseChatModel:
    """Primary reasoning LLM. Used by Intake, Policy, Counsel.

    Note: model name pinned to a current Sonnet release. Update when Anthropic
    releases a newer Sonnet.
    """
    return ChatAnthropic(
        model=model,
        api_key=require("ANTHROPIC_API_KEY"),
        temperature=temperature,
        max_tokens=4096,
        timeout=60,
    )


@lru_cache(maxsize=4)
def get_claude_fast(temperature: float = 0.0) -> BaseChatModel:
    """Cheap/fast Claude for routers + structured extraction. Haiku tier."""
    return ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=require("ANTHROPIC_API_KEY"),
        temperature=temperature,
        max_tokens=2048,
        timeout=30,
    )


@lru_cache(maxsize=4)
def get_groq(model: str = "llama-3.3-70b-versatile", temperature: float = 0.0) -> BaseChatModel:
    """Fast structured-output LLM. Used by Risk scorer (Member C).

    Falls back to Claude Haiku if GROQ_API_KEY is not set, so the demo never
    hard-blocks on a missing Groq key.
    """
    groq_key = settings()["GROQ_API_KEY"]
    if not groq_key:
        return get_claude_fast(temperature=temperature)
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        api_key=groq_key,
        temperature=temperature,
        max_tokens=2048,
        timeout=30,
    )


def get_embeddings():
    """OpenAI text-embedding-3-small (1536-dim). Used by Member B for pgvector."""
    from langchain_openai import OpenAIEmbeddings

    key = settings()["OPENAI_API_KEY"]
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY required for embeddings. Set it in .env (Member B uses this)."
        )
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=key)

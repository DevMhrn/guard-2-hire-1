"""Env-var loader. Single place that reads the environment."""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# Auto-disable LangSmith tracing if no API key is set — otherwise the SDK
# spams 401 errors every node. Teammates can enable it later by setting
# LANGCHAIN_API_KEY.
if not os.environ.get("LANGCHAIN_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.pop("LANGSMITH_TRACING", None)
    os.environ.pop("LANGSMITH_API_KEY", None)

# Allow our Pydantic models to round-trip through the LangGraph checkpointer
# without triggering the "unregistered type" deserialization warning.
os.environ.setdefault(
    "LANGGRAPH_ALLOWED_MSGPACK_MODULES",
    "hireguard.state",
)


def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Missing required env var: {key}. Copy .env.example to .env and fill it in."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@lru_cache(maxsize=1)
def settings() -> dict:
    """Reads env vars lazily. Missing required keys raise only when *used*
    (see `require()` below) — so importing this module never fails."""
    return {
        # LLMs
        "ANTHROPIC_API_KEY": _optional("ANTHROPIC_API_KEY"),
        "GROQ_API_KEY": _optional("GROQ_API_KEY"),
        "OPENAI_API_KEY": _optional("OPENAI_API_KEY"),
        # Supabase
        "SUPABASE_URL": _optional("SUPABASE_URL"),
        "SUPABASE_KEY": _optional("SUPABASE_KEY"),
        "SUPABASE_DB_URL": _optional("SUPABASE_DB_URL"),
        # LangSmith (handled by env vars directly by the SDK, but we read for sanity)
        "LANGCHAIN_TRACING_V2": _optional("LANGCHAIN_TRACING_V2", "true"),
        "LANGCHAIN_PROJECT": _optional("LANGCHAIN_PROJECT", "hireguard-v2"),
        # Tavily (optional)
        "TAVILY_API_KEY": _optional("TAVILY_API_KEY"),
    }


def require(key: str) -> str:
    """Fetch a required setting; raise a clear error at the call site if missing."""
    val = settings().get(key, "")
    if not val:
        raise RuntimeError(
            f"Missing required env var: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def use_postgres_checkpointer() -> bool:
    """If SUPABASE_DB_URL is set, use PostgresSaver. Else fall back to MemorySaver."""
    return bool(settings()["SUPABASE_DB_URL"])

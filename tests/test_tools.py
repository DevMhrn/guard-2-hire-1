"""Smoke tests for LangChain @tool-decorated tools.

These tests don't hit the network — they verify the tools exist, are properly
decorated as LangChain BaseTool instances, have the expected names + arg
schemas, and that the offline (no-key) path returns a usable message.
"""
from __future__ import annotations

import os

import pytest


def test_web_search_is_a_langchain_tool():
    """web_search must be a LangChain BaseTool with the right name + schema."""
    from langchain_core.tools import BaseTool

    from hireguard.tools.web_search import web_search

    assert isinstance(web_search, BaseTool)
    assert web_search.name == "web_search"
    schema = web_search.args_schema
    assert schema is not None
    # the only required arg is the query string
    field_names = set(schema.model_fields.keys())
    assert "query" in field_names


def test_verify_statute_currency_is_a_langchain_tool():
    """The pre-existing Tavily tool should also be a LangChain BaseTool."""
    from langchain_core.tools import BaseTool

    from hireguard.tools.statute_lookup import verify_statute_currency

    assert isinstance(verify_statute_currency, BaseTool)
    assert verify_statute_currency.name == "verify_statute_currency"


def test_web_search_offline_returns_unavailable_message(monkeypatch):
    """No TAVILY_API_KEY → tool returns a clear 'unavailable' string,
    NOT raises. The LLM should be able to see this and continue."""
    from hireguard.tools.web_search import _tavily, web_search

    # Clear any cached client + the env var
    import hireguard.tools.web_search as ws_mod

    ws_mod._client = None
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    # Clear the lru_cache so we don't get a previous-run hit
    web_search.func.cache_clear()  # type: ignore[attr-defined]

    result = web_search.invoke({"query": "test query"})
    assert isinstance(result, str)
    assert "unavailable" in result.lower()


def test_counsel_tools_are_bindable_to_an_llm():
    """The exact tool list Counsel exposes must be acceptable to bind_tools.
    This is a structural check — we don't actually call the LLM."""
    from hireguard.agents.counsel import COUNSEL_TOOLS, TOOL_MAP

    assert len(COUNSEL_TOOLS) == 2
    names = {t.name for t in COUNSEL_TOOLS}
    assert names == {"verify_statute_currency", "web_search"}
    # TOOL_MAP must round-trip
    assert set(TOOL_MAP.keys()) == names
    for name, tool in TOOL_MAP.items():
        assert tool.name == name

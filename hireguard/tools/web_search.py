"""Generic Tavily-backed web-search tool for LLM tool-calling.

Bound to Counsel's LLM via `bind_tools(...)` so the agent can decide WHEN to
gather external context (case law, regulatory news, industry benchmarks) before
finalising the audit memo. This is the real "LLM-driven tool-call" surface in
our system, distinct from `with_structured_output` which only enforces typed
output shape.

Best-effort by design:
  * If TAVILY_API_KEY is missing → returns a clear 'unavailable' message so the
    LLM stops trying and continues without external context.
  * If the network errors → returns the error string, same behavior.
  * @lru_cache keeps repeated demo queries cheap.

The tool's docstring is what the LLM sees as its "manual page" — it's written
to teach the LLM when to invoke and when to abstain.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

try:  # tool decorator is optional at import time so tests pass without LC
    from langchain_core.tools import tool as _lc_tool
except Exception:  # pragma: no cover
    def _lc_tool(fn=None, **_kw):  # type: ignore
        def _wrap(f):
            return f

        return _wrap(fn) if callable(fn) else _wrap

log = logging.getLogger(__name__)

_client = None


def _tavily():
    global _client
    if _client is None:
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            return None
        try:
            from tavily import TavilyClient

            _client = TavilyClient(api_key=key)
        except Exception as exc:  # pragma: no cover
            log.warning("web_search: failed to init Tavily client: %s", exc)
            return None
    return _client


@_lc_tool
@lru_cache(maxsize=128)
def web_search(query: str) -> str:
    """Search the public web for recent context that may post-date your training data.

    Use this tool when you need information that is genuinely external — examples
    of GOOD queries for a hiring-compliance audit:

      • "Indian Code on Wages 2019 enforcement cases Karnataka 2024"
      • "Transgender Persons Act 2019 employment ruling Supreme Court"
      • "Maternity Benefit Act 2017 amendment latest news"
      • "Software engineer salary Bengaluru 2024 industry benchmark"

    Do NOT use this tool for:
      • General legal definitions (you already know these from training data)
      • Constitutional Articles 14/15/16 (these never change)
      • Rephrasing of evidence already in the packet

    Returns a compact summary: the top 3 results with title, URL, and a short
    excerpt each. If web search is unavailable (no API key, network error), you
    will receive a clear 'unavailable' message — do not retry, just continue
    drafting the memo without external context.

    Args:
        query: A focused 5-12 word search query.

    Returns:
        A plain-text summary block, or an 'unavailable' message.
    """
    client = _tavily()
    if client is None:
        return (
            "web_search unavailable: TAVILY_API_KEY not set. "
            "Continue without external context."
        )
    try:
        res = client.search(query=query, search_depth="basic", max_results=3)
        results = res.get("results") or []
        if not results:
            return f"web_search returned no results for query: {query!r}"
        lines = [f"Top {len(results)} web results for {query!r}:"]
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "(no title)").strip()
            url = (r.get("url") or "(no url)").strip()
            content = (r.get("content") or "").strip()[:300].replace("\n", " ")
            lines.append(f"\n{i}. {title}\n   URL: {url}\n   {content}")
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("web_search failed: %s", exc)
        return (
            f"web_search failed: {type(exc).__name__}: {str(exc)[:120]}. "
            "Continue without external context."
        )

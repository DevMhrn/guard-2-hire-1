"""Focused Indian-statute lookup tool — bound to Policy's LLM.

When Policy is about to cite a statute (e.g. "Code on Wages, 2019 § 3") it can
call this tool to fetch the actual current text from an authoritative Indian
legal source. This guards against citing a section that has been amended or
renumbered since the model's training cutoff.

Architectural choice (cross-verified against agent audit):
  • Intake doesn't need tools — its job is structured extraction from the packet.
  • Risk doesn't need tools — its job is fast scoring; tool calls per finding
    would slow the audit and Risk is already calibrated by Harsh's prompt.
  • Counsel already has verify_statute_currency + web_search (minimal path).
  • Policy is the one place where targeted statute-text lookup adds genuine
    value — verifying the exact wording before emitting a citation.

Best-effort by design:
  * If TAVILY_API_KEY is missing → returns a clear 'unavailable' message so the
    LLM stops trying and continues without verification.
  * Network errors → returns an error string in the same shape.
  * @lru_cache keeps repeated demo queries cheap.

Tavily is scoped via the `include_domains` parameter to known Indian legal
sources (indiacode.nic.in is the Government of India's official statute
repository; legallyindia.com, lawctopus.com, scconline.com host case law +
amendments). The LLM sees this scoping inside the result.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

try:
    from langchain_core.tools import tool as _lc_tool
except Exception:  # pragma: no cover
    def _lc_tool(fn=None, **_kw):  # type: ignore
        def _wrap(f):
            return f

        return _wrap(fn) if callable(fn) else _wrap

log = logging.getLogger(__name__)

_client = None

# Authoritative Indian legal sources to scope Tavily searches to.
_INDIAN_LEGAL_DOMAINS = [
    "indiacode.nic.in",  # Government of India — official statute repository
    "labour.gov.in",  # Ministry of Labour & Employment
    "legislative.gov.in",  # Legislative Department
    "scconline.com",  # SCC Online — case law and statutes
    "legallyindia.com",  # legal news + amendments
    "lawctopus.com",  # legal analysis
    "barandbench.com",  # legal journalism + judgments
    "livelaw.in",  # legal news + recent rulings
]


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
            log.warning("fetch_indian_statute: Tavily init failed: %s", exc)
            return None
    return _client


@_lc_tool
@lru_cache(maxsize=128)
def fetch_indian_statute(statute_short_name: str, section: str = "") -> str:
    """Fetch the current text of a specific section of an Indian employment statute.

    Use this tool when you are about to cite a statute in a finding and want to
    verify the exact current wording — especially for:

      • Statutes amended in the last 5 years (RPwD 2016, Transgender Persons 2019,
        HIV/AIDS 2017, Maternity Benefit Act 2017 amendment)
      • Section numbers you are uncertain about
      • Statutes you want to confirm haven't been recently repealed

    Do NOT use this tool for:
      • Constitution Articles 14/15/16 — these are well-known and stable
      • Statutes you're already confident about (e.g. Code on Wages 2019 §3 is
        the canonical gender-neutral-recruitment provision)

    Returns top 3 results from authoritative Indian legal sources
    (indiacode.nic.in, labour.gov.in, scconline.com, livelaw.in, etc.), each
    with title + URL + a short excerpt. If unavailable, returns a clear
    'unavailable' message — do not retry, just continue without verification.

    Args:
        statute_short_name: The statute's short name, e.g. "Code on Wages 2019",
            "Maternity Benefit Act 1961", "RPwD Act 2016".
        section: Optional section number, e.g. "3", "20", "3(b)". Empty string
            means search the whole statute.

    Returns:
        Plain-text summary of search results, or an 'unavailable' message.
    """
    client = _tavily()
    if client is None:
        return (
            "fetch_indian_statute unavailable: TAVILY_API_KEY not set. "
            "Continue citing the statute from training-data knowledge."
        )
    section_clause = f" section {section}" if section else ""
    query = f'"{statute_short_name}"{section_clause} text amendments India 2024'
    try:
        res = client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_domains=_INDIAN_LEGAL_DOMAINS,
        )
        results = res.get("results") or []
        if not results:
            # Retry without domain scoping — sometimes the scoped search misses
            res = client.search(query=query, search_depth="basic", max_results=3)
            results = res.get("results") or []
        if not results:
            return (
                f"fetch_indian_statute: no results for {statute_short_name!r}"
                f"{section_clause}. Continue without verification."
            )
        header = (
            f"Top {len(results)} results for "
            f"{statute_short_name!r}{section_clause} "
            f"(Indian legal sources):"
        )
        lines = [header]
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "(no title)").strip()
            url = (r.get("url") or "(no url)").strip()
            content = (r.get("content") or "").strip()[:400].replace("\n", " ")
            lines.append(f"\n{i}. {title}\n   URL: {url}\n   {content}")
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("fetch_indian_statute failed for %s: %s", statute_short_name, exc)
        return (
            f"fetch_indian_statute failed: {type(exc).__name__}: "
            f"{str(exc)[:120]}. Continue without verification."
        )

"""HireGuard v2 — Streamlit UI.

Linear flow per tab. Light theme pinned in .streamlit/config.toml so cards and
backgrounds render consistently for everyone.

Run with:  streamlit run hireguard/ui/streamlit_app.py
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from hireguard.db import get_checkpointer, save_audit_memo  # noqa: E402
from hireguard.graph import build_graph  # noqa: E402
from hireguard.settings import langsmith_enabled, settings  # noqa: E402
from hireguard.state import HiringPacket, PipelineState  # noqa: E402

SAMPLES_DIR = Path("hireguard/samples")

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HireGuard v2",
    layout="wide",
    page_icon="🛡",
    initial_sidebar_state="expanded",
)

# Compact custom CSS — only for the hero, severity badges, and a couple of
# small polishes. Everything else uses Streamlit's native components, which
# automatically pick up the pinned light theme from .streamlit/config.toml.
st.markdown(
    """
<style>
/* Hide Streamlit's default chrome */
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}

/* Tighten top padding so the hero hugs the top */
.block-container {padding-top: 1.2rem !important;}

/* ── Hero banner ─────────────────────────────────────────────────────── */
.hero {
    background: linear-gradient(135deg, #4338ca 0%, #6366f1 55%, #FF9933 140%);
    border-radius: 14px; padding: 22px 28px; color: white;
    margin-bottom: 18px; box-shadow: 0 6px 28px -8px rgba(67,56,202,0.4);
}
.hero h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em;}
.hero h1 .v { opacity: 0.65; font-weight: 500;}
.hero p { margin: 6px 0 0 0; font-size: 14px; line-height: 1.55; opacity: 0.94;}
.hero .badges { margin-top: 12px; display:flex; gap:6px; flex-wrap:wrap;}
.hero .badge {
    background: rgba(255,255,255,0.18); padding: 3px 9px; border-radius: 5px;
    font-size: 10.5px; font-weight: 600; letter-spacing: 0.05em;
    text-transform: uppercase;
}

/* ── Verdict pills (for memo + history headers) ───────────────────────── */
.verdict {
    display:inline-block; padding:5px 12px; border-radius:6px;
    font-weight:700; font-size:12px; letter-spacing:0.04em;
    text-transform:uppercase;
}
.verdict.critical {background:#fee2e2; color:#991b1b; border:1px solid #fca5a5;}
.verdict.high     {background:#ffedd5; color:#9a3412; border:1px solid #fdba74;}
.verdict.medium   {background:#fef3c7; color:#854d0e; border:1px solid #fde68a;}
.verdict.clean    {background:#dcfce7; color:#166534; border:1px solid #86efac;}

/* ── Severity left-bar for finding rows ───────────────────────────────── */
.finding-row {
    background: white; border:1px solid #e4e4e7; border-radius:8px;
    padding: 12px 14px; margin-bottom: 8px;
    border-left-width: 4px; border-left-style: solid;
}
.finding-row.critical {border-left-color: #dc2626;}
.finding-row.high     {border-left-color: #ea580c;}
.finding-row.medium   {border-left-color: #ca8a04;}
.finding-row.low      {border-left-color: #16a34a;}
.finding-row .head {display:flex; gap:8px; align-items:center; margin-bottom:6px;}
.finding-row .rule {font-weight:600; font-size:13.5px; color:#18181b;}
.sev-tag {
    padding:2px 7px; border-radius:4px; font-size:9.5px; font-weight:700;
    letter-spacing:0.05em; text-transform:uppercase;
}
.sev-tag.critical {background:#fee2e2; color:#991b1b;}
.sev-tag.high     {background:#ffedd5; color:#9a3412;}
.sev-tag.medium   {background:#fef3c7; color:#854d0e;}
.sev-tag.low      {background:#dcfce7; color:#166534;}
.finding-row .evidence {
    background:#fafafa; padding: 8px 10px; border-radius:5px; margin-top:6px;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size:12px; color:#3f3f46; border-left:2px solid #e4e4e7;
}
.finding-row .meta {font-size:11.5px; color:#71717a; margin-top:6px;}

/* ── Sidebar status rows ─────────────────────────────────────────────── */
.status-row {
    display:flex; align-items:center; gap:8px; padding:6px 10px;
    background:#f4f4f5; border-radius:6px; margin-bottom:5px; font-size:13px;
    color:#27272a;
}
.status-dot {width:8px; height:8px; border-radius:50%; flex-shrink:0;}
.status-dot.up   {background:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,0.18);}
.status-dot.off  {background:#d4d4d8;}

/* ── Step label ───────────────────────────────────────────────────────── */
.step-label {
    display:inline-block; background:#eef2ff; color:#4338ca;
    font-size:10.5px; font-weight:700; letter-spacing:0.08em;
    text-transform:uppercase; padding:3px 8px; border-radius:4px;
    margin-bottom: 6px;
}

/* ── Pipeline strip ───────────────────────────────────────────────────── */
.pipeline {display:flex; gap:6px; align-items:center; margin:10px 0;}
.pipe-node {
    flex:1; padding:8px 10px; background:#f4f4f5; border-radius:6px;
    border:1px solid #e4e4e7; font-size:11.5px; font-weight:600;
    color:#71717a; text-align:center;
}
.pipe-node.done   {background:#dcfce7; border-color:#86efac; color:#166534;}
.pipe-node.paused {background:#ffedd5; border-color:#fdba74; color:#9a3412;}
.pipe-arrow {color:#d4d4d8; font-size:14px;}

/* ── Muted helper text ────────────────────────────────────────────────── */
.muted {color:#71717a; font-size:13px;}

/* ── Live terminal log ────────────────────────────────────────────────── */
.term {
    background: #0b0d12; color: #e4e4e7;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size: 12.5px; line-height: 1.7;
    padding: 14px 16px; border-radius: 8px;
    border: 1px solid #1f2937;
    max-height: 360px; overflow-y: auto;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
}
.term .ts { color: #71717a; }
.term .node { color: #93c5fd; font-weight: 600; }
.term .done { color: #86efac; }
.term .warn { color: #fdba74; }
.term .err  { color: #fca5a5; }
.term .info { color: #c4b5fd; }
.term .dim  { color: #71717a; }
.term .running {
    color: #fcd34d; animation: blink 1.2s ease-in-out infinite;
}
@keyframes blink {0%,100% {opacity: 1;} 50% {opacity: 0.4;}}
.term-empty { color: #71717a; font-style: italic;}
</style>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Hero
# ──────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
<div class="hero">
  <h1>🛡 HireGuard <span class="v">v2</span></h1>
  <p>Multi-agent AI auditor for <b>Indian hiring-compliance</b> — reviews job posting, comp band, and interview scorecard for violations of Indian employment law, with a human approval gate before any audit is finalised.</p>
  <div class="badges">
    <span class="badge">LangGraph</span>
    <span class="badge">Claude Sonnet</span>
    <span class="badge">Supabase + pgvector</span>
    <span class="badge">LangSmith</span>
    <span class="badge">🇮🇳 India-Central Law</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — system status, agent map, observability link
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("##### System status")
    s = settings()
    rows = [
        ("Anthropic (Claude)", bool(s["ANTHROPIC_API_KEY"])),
        ("OpenAI (embeddings)", bool(s["OPENAI_API_KEY"])),
        ("Supabase Postgres", bool(s["SUPABASE_DB_URL"])),
        ("LangSmith tracing", langsmith_enabled()),
    ]
    for label, up in rows:
        dot = "up" if up else "off"
        st.markdown(
            f"<div class='status-row'><span class='status-dot {dot}'></span>{label}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("##### Agents in this pipeline")
    st.markdown(
        """
- 🪪 **Intake** — extracts facts, redacts PII
- 📜 **Policy** — retrieves rules, finds violations
- ⚖️ **Risk** — scores severity + exposure
- ✍️ **Counsel** — writes the audit memo
- 🙋 **Human review** — approves / rejects / sends back
"""
    )

    st.markdown("##### Indian ruleset (10 rules)")
    st.markdown(
        """
- Code on Wages, 2019
- RPwD Act, 2016
- Maternity Benefit Act, 1961
- Transgender Persons Act, 2019
- HIV/AIDS Act, 2017
- Constitution Arts. 14 / 15 / 16
"""
    )

    if langsmith_enabled():
        st.markdown("##### Observability")
        st.markdown(
            "[📊 View traces in LangSmith ↗](https://apac.smith.langchain.com)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Runtime helpers (logic unchanged from prior version)
# ──────────────────────────────────────────────────────────────────────────────


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _trace_config(packet: HiringPacket, thread_id: str, phase: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "tags": [
            "hireguard",
            "surface:streamlit",
            f"phase:{phase}",
            f"packet:{packet.packet_id}",
            f"jurisdiction:{packet.primary_work_location}",
        ],
        "metadata": {
            "thread_id": thread_id,
            "packet_id": packet.packet_id,
            "company": packet.company,
            "company_size": packet.company_size,
            "jurisdiction": packet.primary_work_location,
            "surface": "streamlit",
            "phase": phase,
        },
    }


async def _run_until_pause(
    packet: HiringPacket,
    thread_id: str,
    on_event=None,
    callbacks: list | None = None,
):
    """Run pipeline until first __interrupt__. If `on_event` is provided, it's
    called synchronously after each LangGraph event so the UI can render live.
    `callbacks` is a list of LangChain CallbackHandlers — they receive every
    LLM start/end + tool call inside the nodes, propagated automatically.
    """
    async with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        config = _trace_config(packet, thread_id, phase="initial")
        if callbacks:
            config["callbacks"] = callbacks
        events: list[dict] = []
        interrupt_payload = None
        async for ev in graph.astream(
            PipelineState(packet=packet), config=config, stream_mode="updates"
        ):
            events.append(ev)
            if on_event is not None:
                try:
                    on_event(ev)
                except Exception:
                    # never let UI rendering kill the pipeline
                    pass
            if "__interrupt__" in ev:
                interrupt_payload = ev["__interrupt__"][0].value
                break
        snap = await graph.aget_state(config)
        return events, interrupt_payload, snap.values


async def _resume_with(
    approval: dict,
    thread_id: str,
    on_event=None,
    callbacks: list | None = None,
):
    """Resume the graph past a HITL interrupt with the given approval payload.

    Streams events to `on_event` synchronously (for UI live log) and detects if
    the graph re-pauses at a new HITL gate (happens after a `send_back` triggers
    the re-loop). Returns (events, new_interrupt_payload_or_None, final_state).
    """
    async with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        config = {
            "configurable": {"thread_id": thread_id},
            "tags": [
                "hireguard",
                "surface:streamlit",
                "phase:resume",
                f"decision:{approval.get('decision', '?')}",
            ],
            "metadata": {
                "thread_id": thread_id,
                "phase": "resume",
                "decision": approval.get("decision"),
            },
        }
        if callbacks:
            config["callbacks"] = callbacks
        events: list[dict] = []
        interrupt_payload = None
        async for ev in graph.astream(
            Command(resume=approval), config=config, stream_mode="updates"
        ):
            events.append(ev)
            if on_event is not None:
                try:
                    on_event(ev)
                except Exception:
                    pass
            if "__interrupt__" in ev:
                interrupt_payload = ev["__interrupt__"][0].value
                break
        snap = await graph.aget_state(config)
        return events, interrupt_payload, snap.values


def _verdict_class(counts: dict) -> tuple[str, str]:
    if counts.get("critical", 0) > 0:
        return ("critical", "HIGH RISK — DO NOT PUBLISH")
    if counts.get("high", 0) > 0:
        return ("high", "ELEVATED RISK — REVISE")
    if counts.get("medium", 0) > 0:
        return ("medium", "ADVISORY — MINOR ISSUES")
    return ("clean", "PASS — NO VIOLATIONS")


# ──────────────────────────────────────────────────────────────────────────────
# LangChain callback handler — surfaces LLM + tool internals to the live log
# ──────────────────────────────────────────────────────────────────────────────
import time
from typing import Any, Callable, Sequence
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler


def _model_name(serialized: dict | None) -> str:
    """Pull a readable model name out of the LangChain `serialized` dict."""
    if not serialized:
        return "?"
    name = serialized.get("name") or ""
    if name and "/" not in name:
        # Common in newer LangChain: 'ChatAnthropic' / 'ChatGroq'
        kw = serialized.get("kwargs", {}) or {}
        model = kw.get("model") or kw.get("model_name") or ""
        if model:
            return f"{name}({model})"
        return name
    return name or "?"


class StreamlitLogHandler(AsyncCallbackHandler):
    """Streams LLM + tool events from anywhere inside the graph into the
    Streamlit live log. Runs in the same asyncio loop as the pipeline."""

    def __init__(
        self,
        push: Callable[[str], None],
        get_current_node: Callable[[], str | None],
    ):
        super().__init__()
        self.push = push
        self.get_node = get_current_node
        self._llm_t0: dict[UUID, tuple[str, float]] = {}
        self._tool_t0: dict[UUID, tuple[str, float]] = {}

    # ── LLM lifecycle ──
    async def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        **_: Any,
    ) -> None:
        model = _model_name(serialized)
        self._llm_t0[run_id] = (model, time.time())
        node = self.get_node() or "?"
        size = sum(len(p) for p in prompts)
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='info'>🤖 [{node}] {model} ← prompt ({size:,} chars)…</span>"
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **_: Any,
    ) -> None:
        model = _model_name(serialized)
        self._llm_t0[run_id] = (model, time.time())
        node = self.get_node() or "?"
        n_msgs = sum(len(m) for m in messages)
        total_chars = 0
        try:
            for batch in messages:
                for m in batch:
                    content = getattr(m, "content", "") or ""
                    if isinstance(content, str):
                        total_chars += len(content)
        except Exception:
            pass
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='info'>🤖 [{node}] {model} ← {n_msgs} message(s), "
            f"{total_chars:,} chars total…</span>"
        )

    async def on_llm_end(
        self, response: Any, *, run_id: UUID, **_: Any
    ) -> None:
        model, t0 = self._llm_t0.pop(run_id, ("?", time.time()))
        latency = time.time() - t0
        node = self.get_node() or "?"
        # token usage if available
        tokens_in = tokens_out = None
        try:
            out = response.llm_output or {}
            usage = out.get("usage") or out.get("token_usage") or {}
            tokens_in = usage.get("input_tokens") or usage.get("prompt_tokens")
            tokens_out = usage.get("output_tokens") or usage.get("completion_tokens")
        except Exception:
            pass
        tok = ""
        if tokens_in or tokens_out:
            tok = f" · {tokens_in or '?'}→{tokens_out or '?'} tokens"
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='done'>✓ [{node}] {model} responded in {latency:.1f}s{tok}</span>"
        )

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **_: Any
    ) -> None:
        model, _t0 = self._llm_t0.pop(run_id, ("?", 0))
        node = self.get_node() or "?"
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='err'>✗ [{node}] {model} failed: {type(error).__name__}: {str(error)[:120]}</span>"
        )

    # ── Tool lifecycle ──
    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        **_: Any,
    ) -> None:
        name = (serialized or {}).get("name", "tool")
        self._tool_t0[run_id] = (name, time.time())
        node = self.get_node() or "?"
        snippet = (input_str or "").replace("\n", " ")[:80]
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='info'>🔧 [{node}] tool <b>{name}</b>({snippet}…)</span>"
        )

    async def on_tool_end(
        self, output: Any, *, run_id: UUID, **_: Any
    ) -> None:
        name, t0 = self._tool_t0.pop(run_id, ("tool", time.time()))
        latency = time.time() - t0
        node = self.get_node() or "?"
        out_str = str(output).replace("\n", " ")[:100]
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='done'>✓ [{node}] {name} → {out_str}{'…' if len(str(output)) > 100 else ''} ({latency:.2f}s)</span>"
        )

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **_: Any
    ) -> None:
        name, _t0 = self._tool_t0.pop(run_id, ("tool", 0))
        node = self.get_node() or "?"
        self.push(
            f"<span class='dim'>  ↳</span> "
            f"<span class='err'>✗ [{node}] tool {name} errored: {type(error).__name__}: {str(error)[:120]}</span>"
        )


NODE_ICONS = {
    "intake": "🪪",
    "policy": "📜",
    "risk": "⚖️",
    "counsel": "✍️",
    "human_review": "🙋",
}
NODE_ORDER = ["intake", "policy", "risk", "counsel", "human_review"]


def _attr(obj, key, default=None):
    """Get attribute on a Pydantic model OR key on a dict — for resilience."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _format_node_log(node: str, payload: dict) -> tuple[str, list[str]]:
    """Return (summary_line, extra_lines) — both raw text. Streamlit-side will
    HTML-escape and wrap with colours."""
    if node == "intake":
        facts = payload.get("facts")
        if facts is None:
            return ("Intake — no facts returned", [])
        jurisdiction = _attr(facts, "jurisdiction", "?")
        age_n = len(_attr(facts, "age_coded_phrases", []) or [])
        gender_n = len(_attr(facts, "gender_restrictive_phrases", []) or [])
        caste_n = len(_attr(facts, "caste_or_community_signals", []) or [])
        marital_n = len(_attr(facts, "marital_or_pregnancy_signals", []) or [])
        medical_n = len(_attr(facts, "medical_or_hiv_test_signals", []) or [])
        rpwd_n = len(
            _attr(facts, "non_essential_physical_requirements", []) or []
        )
        pii = _attr(facts, "pii_redacted_labels", []) or []
        injection = bool(_attr(facts, "injection_attempt_detected", False))
        subj_n = len(_attr(facts, "subjective_scorecard_criteria", []) or [])
        summary = (
            f"Intake done — jurisdiction={jurisdiction}, "
            f"age:{age_n} gender:{gender_n} caste:{caste_n} "
            f"marital:{marital_n} medical:{medical_n} disability:{rpwd_n} "
            f"subjective-scorecard:{subj_n}"
        )
        extras = []
        if pii:
            extras.append(f"  ↳ PII redacted: {', '.join(pii)}")
        if injection:
            extras.append("  ↳ ⚠ prompt-injection attempt detected (flagged, not refused)")
        return (summary, extras)

    if node == "policy":
        findings = payload.get("findings", []) or []
        errors = payload.get("errors", []) or []
        ids = [_attr(f, "rule_id", "?") for f in findings]
        summary = (
            f"Policy done — {len(findings)} finding(s): "
            f"{', '.join(ids) if ids else '(none)'}"
        )
        extras = []
        # Surface a few useful notes from policy errors (retrieval/heuristic/dropped)
        for e in errors[-4:]:
            if any(k in e for k in ("dropped", "retriev", "heuristic", "re-check")):
                extras.append(f"  ↳ {e.replace('[policy_node]', '').strip()}")
        return (summary, extras)

    if node == "risk":
        scored = payload.get("scored_findings", []) or []
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        flagged = 0
        for s in scored:
            sev = _attr(s, "severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
            if _attr(s, "needs_human_review", False):
                flagged += 1
        summary = (
            f"Risk done — scored {len(scored)}: "
            f"🔴{counts['critical']} 🟠{counts['high']} "
            f"🟡{counts['medium']} 🟢{counts['low']}"
        )
        extras = []
        if flagged:
            extras.append(f"  ↳ {flagged} finding(s) flagged for human review")
        return (summary, extras)

    if node == "counsel":
        memo = payload.get("audit_memo")
        revs = payload.get("revision_count", 0)
        if memo is None:
            return ("Counsel done — no memo", [])
        crit = _attr(memo, "critical_count", 0)
        high = _attr(memo, "high_count", 0)
        med = _attr(memo, "medium_count", 0)
        low = _attr(memo, "low_count", 0)
        re_review = bool(_attr(memo, "needs_re_review", False))
        memo_id = _attr(memo, "memo_id", "")
        summary = (
            f"Counsel done — memo {str(memo_id)[:8]} | "
            f"🔴{crit} 🟠{high} 🟡{med} 🟢{low} | revision={revs}"
        )
        extras = []
        if re_review:
            extras.append("  ↳ ↩ flagged for re-check (thin Critical evidence)")
        return (summary, extras)

    if node == "human_review":
        return ("Human review — paused for approval", [])

    return (f"{node} done", [])


def _now_hms() -> str:
    """Module-level timestamp helper for the live log."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


def _running_banner(node: str | None) -> str:
    """Yellow blinking 'X is running…' banner for the currently-in-flight node.
    Module-level so it can be used by both Run-Audit and Send-back flows.
    """
    if node is None:
        return ""
    icon = NODE_ICONS.get(node, "•")
    return (
        f"<div style='display:flex; gap:8px; align-items:center; "
        f"background:#fef9c3; border:1px solid #fde68a; border-radius:8px; "
        f"padding:8px 12px; margin: 8px 0; font-size:13px;'>"
        f"<span style='animation: blink 1.2s ease-in-out infinite;'>{icon}</span>"
        f"<span><b>{node}</b> is running…</span>"
        f"</div>"
    )


def _pipeline_strip(done: list[str], paused: bool = False) -> str:
    nodes = ["intake", "policy", "risk", "counsel", "human_review"]
    labels = {
        "intake": "🪪 Intake",
        "policy": "📜 Policy",
        "risk": "⚖️ Risk",
        "counsel": "✍️ Counsel",
        "human_review": "🙋 HITL",
    }
    parts = ['<div class="pipeline">']
    for i, n in enumerate(nodes):
        cls = "pipe-node"
        if n in done:
            cls = "pipe-node done"
        if n == "human_review" and paused:
            cls = "pipe-node paused"
        parts.append(f'<div class="{cls}">{labels[n]}</div>')
        if i < len(nodes) - 1:
            parts.append('<span class="pipe-arrow">›</span>')
    parts.append("</div>")
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────

tab_run, tab_review, tab_history = st.tabs(
    ["🔍  Run Audit", "⏸  Pending Approval", "📜  History"]
)

# ─── Run Audit ──────────────────────────────────────────────────────────────
with tab_run:
    # STEP 1 — pick a packet
    st.markdown("<div class='step-label'>Step 1 — choose</div>", unsafe_allow_html=True)
    st.markdown("##### Pick a hiring packet to audit")

    sample_files = sorted(p.stem for p in SAMPLES_DIR.glob("*.json"))
    if "selected_sample" not in st.session_state:
        st.session_state["selected_sample"] = (
            sample_files[0] if sample_files else None
        )

    # Two flagship quick-picks
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "🚨  Dirty packet — Acme (Bengaluru)",
            use_container_width=True,
            help="7 planted violations across gender, caste, marital, RPwD, HIV, age, subjective",
        ):
            st.session_state["selected_sample"] = "acme_se_role"
    with col_b:
        if st.button(
            "✅  Clean packet — Northwind (Hyderabad)",
            use_container_width=True,
            help="Compliant Indian PM role; expected verdict PASS",
        ):
            st.session_state["selected_sample"] = "northwind_pm_role"

    # More cases — chip strip
    st.caption("More cases")
    other_cases = [
        (
            "mumbai_factory_role",
            "🏭  Mumbai factory",
            "Maharashtra domicile + transgender exclusion + RPwD overreach",
        ),
        (
            "chennai_sales_role",
            "💼  Chennai sales",
            "Gender-coded title + pay-parity violation",
        ),
        (
            "delhi_startup_role",
            "🚀  Delhi startup",
            "Soft rules only — age-bar + culture-fit; tests calibrated medium ceiling",
        ),
        (
            "bengaluru_internship_role",
            "📝  Bengaluru internship",
            "Maternity / marital restriction + age bar",
        ),
        (
            "kolkata_injection_role",
            "🪤  Prompt injection",
            "Posting tries to subvert the auditor; real violations must still surface",
        ),
        (
            "gurgaon_frontdesk_role",
            "🛎  Front-desk scorecard",
            "Clean JD; ALL violations live in the interview scorecard — demonstrates rubric audit",
        ),
        (
            "pune_clean_finance_role",
            "🟢  Pune clean (finance)",
            "Second clean variant — Pune, finance industry",
        ),
    ]
    cols = st.columns(3)
    for i, (key, label, helptxt) in enumerate(other_cases):
        if key not in sample_files:
            continue
        with cols[i % 3]:
            if st.button(
                label,
                key=f"qp-{key}",
                use_container_width=True,
                help=helptxt,
            ):
                st.session_state["selected_sample"] = key

    # Dropdown / custom
    choice = st.selectbox(
        "or pick from full list",
        sample_files + ["(custom JSON)"],
        index=(
            sample_files.index(st.session_state["selected_sample"])
            if st.session_state["selected_sample"] in sample_files
            else 0
        ),
    )
    st.session_state["selected_sample"] = choice

    if choice == "(custom JSON)":
        raw_json = st.text_area(
            "Paste a HiringPacket JSON",
            height=240,
            placeholder='{"packet_id": "...", "company": "...", "primary_work_location": "Bengaluru, Karnataka", ...}',
        )
        packet_json = raw_json if raw_json.strip() else None
        preview = None
        if packet_json:
            try:
                preview = HiringPacket.model_validate_json(packet_json)
            except Exception as e:
                st.error(f"Packet parse error: {e}")
                packet_json = None
    else:
        packet_json = (SAMPLES_DIR / f"{choice}.json").read_text()
        try:
            preview = HiringPacket.model_validate_json(packet_json)
        except Exception as e:
            st.error(f"Packet parse error: {e}")
            preview = None

    # STEP 2 — preview
    st.markdown(
        "<div class='step-label' style='margin-top:18px;'>Step 2 — review</div>",
        unsafe_allow_html=True,
    )
    if preview is not None:
        with st.container(border=True):
            top_l, top_r = st.columns([3, 2])
            with top_l:
                st.markdown(f"**{preview.company}**")
                st.caption(
                    f"📍 {preview.primary_work_location}  ·  "
                    f"👥 {preview.company_size or '?'} employees"
                )
            with top_r:
                cb = preview.comp_band
                if cb.internal_band_min and cb.internal_band_max:
                    sym = "₹" if cb.currency == "INR" else cb.currency + " "
                    band = f"{sym}{cb.internal_band_min:,}–{sym}{cb.internal_band_max:,}"
                else:
                    band = "—"
                st.caption(f"💰 Internal band: **{band}**")
                st.caption(
                    f"📋 Posted range: "
                    f"{'**yes**' if cb.posted_range_in_listing else 'not in listing'}"
                )

            with st.expander("📄 Job posting text", expanded=False):
                st.text(preview.job_posting)
            with st.expander("📋 Interview scorecard", expanded=False):
                for c in preview.interview_scorecard.criteria:
                    anchor = "✓ anchored" if c.anchored else "⚠ unanchored"
                    note = f" — {c.note}" if c.note else ""
                    st.markdown(f"- **{c.name}** ({c.scale}, {anchor}){note}")
    else:
        st.info("No packet selected yet.")

    # STEP 3 — run
    st.markdown(
        "<div class='step-label' style='margin-top:18px;'>Step 3 — audit</div>",
        unsafe_allow_html=True,
    )
    run_clicked = st.button(
        "▶  Run multi-agent audit",
        type="primary",
        disabled=packet_json is None,
        use_container_width=True,
    )

    if run_clicked and packet_json:
        packet = HiringPacket.model_validate_json(packet_json)
        thread_id = f"ui-{packet.packet_id}"

        # ── Live UI scaffolding ───────────────────────────────────────────
        st.markdown(" ")
        pipeline_slot = st.empty()
        running_slot = st.empty()
        log_slot = st.empty()

        # Mutable state captured by the on_event closure
        seen: list[str] = []
        log_lines: list[str] = []

        def _push(html_line: str) -> None:
            log_lines.append(html_line)
            log_slot.markdown(
                f"<div class='term'>{'<br>'.join(log_lines)}</div>",
                unsafe_allow_html=True,
            )

        # Initial paint
        pipeline_slot.markdown(_pipeline_strip([]), unsafe_allow_html=True)
        running_slot.markdown(_running_banner("intake"), unsafe_allow_html=True)
        _push(
            f"<span class='ts'>{_now_hms()}</span> "
            f"<span class='info'>🚀 Pipeline starting for packet "
            f"<b>{packet.packet_id}</b> ({packet.primary_work_location})</span>"
        )
        _push(
            f"<span class='ts'>{_now_hms()}</span> "
            f"<span class='dim'>thread_id={thread_id} · checkpointer=Supabase Postgres "
            f"· LangSmith={'on' if langsmith_enabled() else 'off'}</span>"
        )

        # ── Per-event callback (runs synchronously from the asyncio loop) ──
        def on_event(ev: dict) -> None:
            for node, payload in ev.items():
                if node == "__interrupt__":
                    _push(
                        f"<span class='ts'>{_now_hms()}</span> "
                        f"<span class='warn'>⏸ INTERRUPT — pipeline paused for human approval</span>"
                    )
                    pipeline_slot.markdown(
                        _pipeline_strip(seen, paused=True), unsafe_allow_html=True
                    )
                    running_slot.markdown(
                        "<div style='background:#ffedd5; border:1px solid #fdba74; "
                        "border-radius:8px; padding:8px 12px; font-size:13px;'>"
                        "🙋 <b>Awaiting human decision</b></div>",
                        unsafe_allow_html=True,
                    )
                    continue

                seen.append(node)
                icon = NODE_ICONS.get(node, "•")
                summary, extras = _format_node_log(node, payload)
                _push(
                    f"<span class='ts'>{_now_hms()}</span> "
                    f"<span class='done'>✓</span> "
                    f"<span class='node'>{icon} {summary}</span>"
                )
                for ex in extras:
                    _push(f"<span class='dim'>{ex}</span>")

                # Update pipeline strip + next-running banner
                pipeline_slot.markdown(
                    _pipeline_strip(seen, paused=False), unsafe_allow_html=True
                )
                # Predict next node from order
                next_node = None
                for n in NODE_ORDER:
                    if n not in seen:
                        next_node = n
                        break
                if next_node and next_node != "human_review":
                    running_slot.markdown(
                        _running_banner(next_node), unsafe_allow_html=True
                    )
                elif next_node == "human_review":
                    running_slot.markdown(
                        _running_banner("human_review"), unsafe_allow_html=True
                    )

        # Helper the callback handler uses to know which node is in-flight.
        def _current_node() -> str | None:
            for n in NODE_ORDER:
                if n not in seen:
                    return n
            return None

        # LangChain callback handler — fires for every LLM start/end + tool call
        # that happens inside the graph, propagated automatically by LangGraph.
        cb_handler = StreamlitLogHandler(push=_push, get_current_node=_current_node)

        # ── Run the pipeline ──────────────────────────────────────────────
        events, interrupt_payload, snap = _run_async(
            _run_until_pause(
                packet,
                thread_id,
                on_event=on_event,
                callbacks=[cb_handler],
            )
        )

        # ── Final state ───────────────────────────────────────────────────
        paused = interrupt_payload is not None
        if paused:
            _push(
                f"<span class='ts'>{_now_hms()}</span> "
                f"<span class='info'>📋 Pipeline complete — memo drafted, "
                f"awaiting your decision in the <b>Pending Approval</b> tab.</span>"
            )
            st.session_state["pending"] = {
                "thread_id": thread_id,
                "payload": interrupt_payload,
                "snap": snap,
            }
            st.success(
                "🙋  Awaiting your decision — switch to **⏸ Pending Approval**."
            )
        else:
            _push(
                f"<span class='ts'>{_now_hms()}</span> "
                f"<span class='warn'>Pipeline terminated without HITL pause.</span>"
            )
            running_slot.empty()
            st.info("Graph terminated without a HITL pause.")


# ─── Pending Approval ───────────────────────────────────────────────────────
with tab_review:
    if "pending" not in st.session_state:
        with st.container(border=True):
            st.markdown(
                "<div style='text-align:center; padding:32px 16px;'>"
                "<div style='font-size:32px;'>🙋</div>"
                "<div style='font-size:15px; font-weight:600;'>No audit pending</div>"
                "<div class='muted' style='margin-top:4px;'>Start one in the <b>Run Audit</b> tab.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
    else:
        p = st.session_state["pending"]
        payload = p["payload"]
        snap = p["snap"]
        memo = snap.get("audit_memo")
        counts = payload.get("counts", {})
        v_cls, v_label = _verdict_class(counts)
        # Pull revision_count from state — incremented by each Counsel pass.
        # First pass = 1; after one send-back the re-checked memo is revision 2.
        revision = int(snap.get("revision_count") or 0)

        # Verdict + summary
        with st.container(border=True):
            top_l, top_r = st.columns([3, 1])
            with top_l:
                revision_badge = ""
                if revision >= 2:
                    revision_badge = (
                        f" <span style='margin-left:8px; padding:3px 8px; "
                        f"border-radius:5px; background:#e0e7ff; color:#3730a3; "
                        f"font-size:11px; font-weight:700; letter-spacing:0.05em; "
                        f"text-transform:uppercase;'>↩ Revision #{revision}</span>"
                    )
                st.markdown(
                    f"<span class='verdict {v_cls}'>{v_label}</span>{revision_badge}",
                    unsafe_allow_html=True,
                )
            with top_r:
                st.caption(f"Memo `{(payload.get('memo_id') or '')[:12]}`")

            st.markdown(" ")
            st.markdown(payload.get("executive_summary", ""))

        # Severity tiles (native metrics for consistent theme)
        st.markdown(" ")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔴 Critical", counts.get("critical", 0))
        m2.metric("🟠 High", counts.get("high", 0))
        m3.metric("🟡 Medium", counts.get("medium", 0))
        m4.metric("🟢 Low", counts.get("low", 0))

        # Findings
        findings = payload.get("findings_preview", [])
        st.markdown(f"##### Findings ({len(findings)})")
        if not findings:
            with st.container(border=True):
                st.markdown(
                    "<div style='text-align:center; padding:20px;'>"
                    "<div style='font-size:24px;'>✅</div>"
                    "<div>No findings — packet appears compliant.</div></div>",
                    unsafe_allow_html=True,
                )
        else:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for f in sorted(
                findings, key=lambda x: severity_order.get(x.get("severity"), 4)
            ):
                sev = f.get("severity", "low")
                rule_id = f.get("rule_id", "?")
                score = f.get("exposure_score", 0)
                evidence = f.get("evidence", "")
                st.markdown(
                    f"""
<div class='finding-row {sev}'>
  <div class='head'>
    <span class='sev-tag {sev}'>{sev}</span>
    <span class='rule'>{rule_id}</span>
  </div>
  <div class='evidence'>"{evidence[:300]}{'…' if len(evidence) > 300 else ''}"</div>
  <div class='meta'>📊 Exposure score: <b>{score}/100</b></div>
</div>
""",
                    unsafe_allow_html=True,
                )

        # Decision
        st.markdown("##### Your decision")
        note = st.text_area(
            "Reviewer note (optional)",
            value="",
            placeholder="Why are you approving / rejecting / sending back?",
            label_visibility="collapsed",
        )
        c1, c2, c3 = st.columns(3)

        # ── Approve ─────────────────────────────────────────────────────
        if c1.button(
            "✅  Approve & publish", type="primary", use_container_width=True
        ):
            approval = {"decision": "approve", "reviewer_note": note}
            _, _new_interrupt, final_snap = _run_async(
                _resume_with(approval, p["thread_id"])
            )
            if memo:
                _run_async(
                    save_audit_memo(
                        run_id=p["thread_id"],
                        packet_json=PipelineState.model_validate(
                            snap
                        ).packet.model_dump_json(),
                        memo_json=json.dumps(
                            memo if isinstance(memo, dict) else memo.model_dump(),
                            default=str,
                        ),
                    )
                )
            st.success("✓ Audit published. See the **📜 History** tab.")
            del st.session_state["pending"]
            st.rerun()

        # ── Send back — full live re-check loop ─────────────────────────
        if c2.button("↩  Send back for re-check", use_container_width=True):
            MAX_REVISIONS_UI = 2  # mirror graph.MAX_REVISIONS for the UI message

            if revision >= MAX_REVISIONS_UI:
                # The graph router will route to END (not loop) — warn before invoking.
                st.warning(
                    f"⛔ Revision limit reached ({MAX_REVISIONS_UI}). "
                    "Re-check will not run again — please Approve or Reject."
                )
            else:
                st.markdown(" ")
                with st.container(border=True):
                    st.markdown(
                        f"<div class='step-label'>Re-check in progress — revision #{revision + 1}</div>",
                        unsafe_allow_html=True,
                    )
                    pipeline_slot = st.empty()
                    running_slot = st.empty()
                    log_slot = st.empty()

                    seen: list[str] = []
                    log_lines: list[str] = []

                    def _push(html_line: str) -> None:
                        log_lines.append(html_line)
                        log_slot.markdown(
                            f"<div class='term'>{'<br>'.join(log_lines)}</div>",
                            unsafe_allow_html=True,
                        )

                    pipeline_slot.markdown(
                        _pipeline_strip([]), unsafe_allow_html=True
                    )
                    running_slot.markdown(
                        _running_banner("policy"), unsafe_allow_html=True
                    )
                    _push(
                        f"<span class='ts'>{_now_hms()}</span> "
                        f"<span class='warn'>↩ SEND-BACK — re-running pipeline "
                        f"from Policy with reviewer note: "
                        f"{(note or '(none)')[:80]}</span>"
                    )

                    def on_event(ev: dict) -> None:
                        for node, payload_ev in ev.items():
                            if node == "__interrupt__":
                                _push(
                                    f"<span class='ts'>{_now_hms()}</span> "
                                    f"<span class='warn'>⏸ INTERRUPT — "
                                    f"re-checked memo ready for review</span>"
                                )
                                pipeline_slot.markdown(
                                    _pipeline_strip(seen, paused=True),
                                    unsafe_allow_html=True,
                                )
                                running_slot.markdown(
                                    "<div style='background:#ffedd5; border:1px solid #fdba74; "
                                    "border-radius:8px; padding:8px 12px; font-size:13px;'>"
                                    "🙋 <b>Awaiting human decision (revised memo)</b></div>",
                                    unsafe_allow_html=True,
                                )
                                continue

                            # human_review fires its own update event when it
                            # consumes the resume Command — skip it from "seen"
                            # so the pipeline strip shows the re-loop fresh.
                            if node == "human_review":
                                continue

                            seen.append(node)
                            icon = NODE_ICONS.get(node, "•")
                            summary, extras = _format_node_log(node, payload_ev)
                            _push(
                                f"<span class='ts'>{_now_hms()}</span> "
                                f"<span class='done'>✓</span> "
                                f"<span class='node'>{icon} {summary}</span>"
                            )
                            for ex in extras:
                                _push(f"<span class='dim'>{ex}</span>")
                            pipeline_slot.markdown(
                                _pipeline_strip(seen, paused=False),
                                unsafe_allow_html=True,
                            )
                            next_node = None
                            for n in NODE_ORDER:
                                if n not in seen:
                                    next_node = n
                                    break
                            if next_node:
                                running_slot.markdown(
                                    _running_banner(next_node),
                                    unsafe_allow_html=True,
                                )

                    def _current_node() -> str | None:
                        for n in NODE_ORDER:
                            if n not in seen:
                                return n
                        return None

                    cb_handler = StreamlitLogHandler(
                        push=_push, get_current_node=_current_node
                    )
                    approval = {
                        "decision": "send_back",
                        "reviewer_note": note,
                    }
                    events, new_interrupt, new_snap = _run_async(
                        _resume_with(
                            approval,
                            p["thread_id"],
                            on_event=on_event,
                            callbacks=[cb_handler],
                        )
                    )

                if new_interrupt is not None:
                    # Re-checked memo is ready — refresh pending state + rerun.
                    st.session_state["pending"] = {
                        "thread_id": p["thread_id"],
                        "payload": new_interrupt,
                        "snap": new_snap,
                    }
                    st.success(
                        "↩  Re-checked memo is ready — refreshing view…"
                    )
                    st.rerun()
                else:
                    # No new interrupt: graph routed to END (e.g. revision cap hit).
                    st.warning(
                        "Audit terminated after re-check (no new HITL pause). "
                        "This usually means the revision limit was reached."
                    )
                    if "pending" in st.session_state:
                        del st.session_state["pending"]

        # ── Reject ──────────────────────────────────────────────────────
        if c3.button("❌  Reject", use_container_width=True):
            approval = {"decision": "reject", "reviewer_note": note}
            _run_async(_resume_with(approval, p["thread_id"]))
            st.error("❌  Audit rejected. Nothing published.")
            del st.session_state["pending"]
            st.rerun()


# ─── History ────────────────────────────────────────────────────────────────
with tab_history:
    st.markdown("##### Past approved audits")
    try:
        import psycopg

        url = os.environ.get("SUPABASE_DB_URL", "")
        if not url:
            st.warning("SUPABASE_DB_URL not set — history is empty.")
        else:
            with psycopg.connect(url, prepare_threshold=None) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT run_id,
                               memo->>'executive_summary',
                               (memo->>'critical_count')::int,
                               (memo->>'high_count')::int,
                               (memo->>'medium_count')::int,
                               (memo->>'low_count')::int,
                               approved_at,
                               packet->>'company',
                               packet->>'primary_work_location'
                        FROM audit_memos
                        ORDER BY approved_at DESC
                        LIMIT 50
                        """
                    )
                    rows = cur.fetchall()
            if not rows:
                with st.container(border=True):
                    st.markdown(
                        "<div style='text-align:center; padding:30px;'>"
                        "<div style='font-size:28px;'>📜</div>"
                        "<div style='font-weight:600;'>No audits yet</div>"
                        "<div class='muted'>Run + approve one to see it here.</div></div>",
                        unsafe_allow_html=True,
                    )
            else:
                for (
                    run_id,
                    summary,
                    crit,
                    high,
                    med,
                    low,
                    ts,
                    company,
                    loc,
                ) in rows:
                    counts_local = {
                        "critical": crit or 0,
                        "high": high or 0,
                        "medium": med or 0,
                        "low": low or 0,
                    }
                    v_cls, v_label = _verdict_class(counts_local)
                    with st.container(border=True):
                        top_l, top_r = st.columns([3, 1])
                        with top_l:
                            st.markdown(f"**{company or 'Unknown employer'}**")
                            st.caption(f"📍 {loc or '—'}  ·  🕐 {ts}")
                        with top_r:
                            st.markdown(
                                f"<div style='text-align:right;'>"
                                f"<span class='verdict {v_cls}'>{v_label}</span></div>",
                                unsafe_allow_html=True,
                            )
                        st.caption(
                            f"🔴 {crit or 0} critical  ·  🟠 {high or 0} high  ·  "
                            f"🟡 {med or 0} medium  ·  🟢 {low or 0} low"
                        )
                        if summary:
                            st.markdown(
                                summary[:280] + ("…" if len(summary) > 280 else "")
                            )
                        st.caption(f"thread: `{run_id}`")
    except Exception as e:
        st.error(f"Could not query history: {type(e).__name__}: {e}")

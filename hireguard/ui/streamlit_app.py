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


async def _run_until_pause(packet: HiringPacket, thread_id: str):
    async with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        config = _trace_config(packet, thread_id, phase="initial")
        events: list[dict] = []
        interrupt_payload = None
        async for ev in graph.astream(
            PipelineState(packet=packet), config=config, stream_mode="updates"
        ):
            events.append(ev)
            if "__interrupt__" in ev:
                interrupt_payload = ev["__interrupt__"][0].value
                break
        snap = await graph.aget_state(config)
        return events, interrupt_payload, snap.values


async def _resume_with(approval: dict, thread_id: str):
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
        events: list[dict] = []
        async for ev in graph.astream(
            Command(resume=approval), config=config, stream_mode="updates"
        ):
            events.append(ev)
        snap = await graph.aget_state(config)
        return events, snap.values


def _verdict_class(counts: dict) -> tuple[str, str]:
    if counts.get("critical", 0) > 0:
        return ("critical", "HIGH RISK — DO NOT PUBLISH")
    if counts.get("high", 0) > 0:
        return ("high", "ELEVATED RISK — REVISE")
    if counts.get("medium", 0) > 0:
        return ("medium", "ADVISORY — MINOR ISSUES")
    return ("clean", "PASS — NO VIOLATIONS")


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
            "🚨 Dirty packet — Acme (Bengaluru)",
            use_container_width=True,
            help="7 planted violations across gender, caste, marital, RPwD, HIV, age, subjective",
        ):
            st.session_state["selected_sample"] = "acme_se_role"
    with col_b:
        if st.button(
            "✅ Clean packet — Northwind (Hyderabad)",
            use_container_width=True,
            help="Compliant Indian PM role; expected verdict PASS",
        ):
            st.session_state["selected_sample"] = "northwind_pm_role"

    # Dropdown for other / custom
    choice = st.selectbox(
        "or pick another",
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
        pipeline_slot = st.empty()
        pipeline_slot.markdown(_pipeline_strip([]), unsafe_allow_html=True)

        with st.status("Running multi-agent pipeline…", expanded=True) as status:
            events, interrupt_payload, snap = _run_async(
                _run_until_pause(packet, thread_id)
            )
            seen: list[str] = []
            for ev in events:
                for node, _payload in ev.items():
                    if node == "__interrupt__":
                        continue
                    seen.append(node)
                    st.write(f"✓  **{node}** completed")
            paused = interrupt_payload is not None
            pipeline_slot.markdown(
                _pipeline_strip(seen, paused=paused), unsafe_allow_html=True
            )
            status.update(
                label=(
                    "✓ Pipeline paused at human-review gate"
                    if paused
                    else "Pipeline finished"
                ),
                state="complete",
            )

        if interrupt_payload is not None:
            st.session_state["pending"] = {
                "thread_id": thread_id,
                "payload": interrupt_payload,
                "snap": snap,
            }
            st.success(
                "🙋  Awaiting your decision — switch to **⏸ Pending Approval**."
            )
        else:
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

        # Verdict + summary
        with st.container(border=True):
            top_l, top_r = st.columns([3, 1])
            with top_l:
                st.markdown(
                    f"<span class='verdict {v_cls}'>{v_label}</span>",
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

        if c1.button(
            "✅  Approve & publish", type="primary", use_container_width=True
        ):
            approval = {"decision": "approve", "reviewer_note": note}
            _, final_snap = _run_async(_resume_with(approval, p["thread_id"]))
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

        if c2.button("↩  Send back for re-check", use_container_width=True):
            approval = {"decision": "send_back", "reviewer_note": note}
            _, final_snap = _run_async(_resume_with(approval, p["thread_id"]))
            st.warning("↩  Sent back to Policy for re-check (max 2 loops).")

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

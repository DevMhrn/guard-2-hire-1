"""HireGuard v2 — top-level LangGraph StateGraph.

This is the orchestration spine. Five nodes:

    intake → policy → risk → counsel → (router) → human_review → END
                                              │
                                              └──→ policy   (re-check loop, max 2x)

Conditional edges:
    after counsel: re-check if any critical finding has thin evidence
    after human_review: approve→END, reject→END, send_back→policy

Human-in-the-loop:
    `human_review_node` calls `interrupt(...)`. The graph pauses; the caller
    resumes with `Command(resume=<dict matching HumanApproval>)`.

Public API:
    build_graph(checkpointer) -> CompiledGraph
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from hireguard.agents.counsel import counsel_node
from hireguard.agents.intake import intake_node
from hireguard.agents.policy import policy_node
from hireguard.agents.risk import risk_node
from hireguard.state import HumanApproval, PipelineState

log = logging.getLogger(__name__)

MAX_REVISIONS = 2


# ──────────────────────────────────────────────────────────────────────────────
# Routers (conditional edges)
# ──────────────────────────────────────────────────────────────────────────────


def route_after_counsel(state: PipelineState) -> str:
    """If Counsel asked for a re-check AND we haven't hit the cap → loop back to Policy."""
    memo = state.audit_memo
    if memo and memo.needs_re_review and state.revision_count < MAX_REVISIONS:
        log.info(
            "Re-check triggered (revision=%s, reason=%s)",
            state.revision_count,
            memo.re_review_reason,
        )
        return "policy"
    return "human_review"


def route_after_human(state: PipelineState) -> str:
    """approve → END, reject → END, send_back → policy."""
    if state.human_approval is None:
        # Defensive: should not happen — interrupt() must have resumed before this runs.
        return END  # type: ignore[return-value]
    decision = state.human_approval.decision
    if decision == "send_back" and state.revision_count < MAX_REVISIONS:
        return "policy"
    return END  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────────────
# HITL node — pauses the graph
# ──────────────────────────────────────────────────────────────────────────────


def human_review_node(state: PipelineState) -> dict:
    """Pauses the graph until a human approves / rejects / sends back.

    The caller resumes via `Command(resume={"decision": "...", "reviewer_note": "..."})`.
    """
    memo = state.audit_memo
    payload: dict[str, Any] = {
        "action": "approve_audit_memo",
        "memo_id": memo.memo_id if memo else None,
        "executive_summary": memo.executive_summary if memo else "",
        "counts": {
            "critical": memo.critical_count if memo else 0,
            "high": memo.high_count if memo else 0,
            "medium": memo.medium_count if memo else 0,
            "low": memo.low_count if memo else 0,
        },
        "findings_preview": [
            {
                "rule_id": s.finding.rule_id,
                "severity": s.severity,
                "exposure_score": s.exposure_score,
                "evidence": s.finding.evidence_quote[:200],
            }
            for s in (memo.scored_findings if memo else [])
        ],
        "errors": state.errors,
    }
    raw = interrupt(payload)
    # `raw` is whatever the caller passed via Command(resume=...).
    # Validate against the HumanApproval schema.
    approval = HumanApproval.model_validate(raw)
    return {"human_approval": approval}


# ──────────────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────────────


def build_graph(checkpointer=None):
    """Compile the graph. Pass a checkpointer from db.get_checkpointer()."""
    g = StateGraph(PipelineState)

    g.add_node("intake", intake_node)
    g.add_node("policy", policy_node)
    g.add_node("risk", risk_node)
    g.add_node("counsel", counsel_node)
    g.add_node("human_review", human_review_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "policy")
    g.add_edge("policy", "risk")
    g.add_edge("risk", "counsel")
    g.add_conditional_edges(
        "counsel",
        route_after_counsel,
        {"policy": "policy", "human_review": "human_review"},
    )
    g.add_conditional_edges(
        "human_review",
        route_after_human,
        {"policy": "policy", END: END},
    )

    return g.compile(checkpointer=checkpointer)

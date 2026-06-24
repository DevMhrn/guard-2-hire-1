"""End-to-end smoke test for Member A's graph. Mocks the LLM call inside
intake so the test runs without an ANTHROPIC_API_KEY. Verifies:

  - graph compiles
  - all 5 nodes execute
  - HITL interrupt fires
  - Command(resume=...) advances past interrupt
  - final state has audit_memo + human_approval
"""
from __future__ import annotations

import pytest
from langgraph.types import Command

from hireguard.db import get_checkpointer
from hireguard.graph import build_graph
from hireguard.state import IntakeFacts, PipelineState, load_packet


async def _fake_intake(state: PipelineState) -> dict:
    return {
        "facts": IntakeFacts(
            jurisdiction="CA",
            pay_range_disclosed=False,
            benefits_disclosed=False,
            salary_history_question_present=True,
            age_coded_phrases=["young", "energetic"],
            criminal_history_question_present=False,
            scorecard_question_count=4,
            subjective_scorecard_criteria=["Culture fit"],
            notes="test mock",
        ),
        "errors": ["[intake] mocked in test"],
    }


def _parse_interrupt(payload):
    item = payload[0] if isinstance(payload, (list, tuple)) else payload
    return item.value if hasattr(item, "value") else item


@pytest.mark.asyncio
async def test_full_pipeline_with_approve(monkeypatch):
    monkeypatch.setattr("hireguard.graph.intake_node", _fake_intake)

    packet = load_packet("hireguard/samples/acme_se_role.json")
    async with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "pytest-approve"}}

        interrupt_payload = None
        async for ev in graph.astream(
            PipelineState(packet=packet),
            config=cfg,
            stream_mode="updates",
        ):
            if "__interrupt__" in ev:
                interrupt_payload = _parse_interrupt(ev["__interrupt__"])
                break

        assert interrupt_payload is not None, "graph never paused at HITL"
        assert "memo_id" in interrupt_payload
        assert "counts" in interrupt_payload

        async for _ in graph.astream(
            Command(resume={"decision": "approve", "reviewer_note": "ok"}),
            config=cfg,
            stream_mode="updates",
        ):
            pass

        final = await graph.aget_state(cfg)
        v = final.values
        assert v.get("audit_memo") is not None
        assert v["human_approval"].decision == "approve"
        # graph should have terminated (no next nodes)
        assert not final.next


@pytest.mark.asyncio
async def test_hitl_gate_blocks_finalization(monkeypatch):
    """The graph MUST not reach END without a human_approval payload."""
    monkeypatch.setattr("hireguard.graph.intake_node", _fake_intake)

    packet = load_packet("hireguard/samples/acme_se_role.json")
    async with get_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "pytest-blocked"}}

        async for _ in graph.astream(
            PipelineState(packet=packet),
            config=cfg,
            stream_mode="updates",
        ):
            pass

        snap = await graph.aget_state(cfg)
        # We should be paused at human_review with no approval yet.
        assert snap.values.get("human_approval") is None
        assert "human_review" in snap.next

"""PolicyAgent — Member B's node.

THIS IS A STUB so Member A's graph runs end-to-end. Member B replaces the
body of `policy_node` with the real implementation:

  1. Build a query string from state.facts.
  2. Call retrieve_relevant_rules(query, jurisdiction) tool.
  3. LLM analyzes retrieved rules vs the packet → list[Finding]
     via Claude with_structured_output.
  4. Return {"findings": [...]} (extends the list).

DO NOT change the function signature or the return shape — A's graph wiring
depends on it.
"""
from __future__ import annotations

from hireguard.state import Finding, PipelineState


async def policy_node(state: PipelineState) -> dict:
    """STUB. Member B replaces this body."""
    stub = Finding(
        rule_id="STUB-RULE",
        citation="Stubbed by Member A — Member B will replace.",
        evidence_quote=(state.packet.job_posting[:120] if state.packet.job_posting else ""),
        evidence_quality=0.5,
        rationale="Placeholder finding so the graph runs end-to-end before B lands.",
    )
    return {
        "findings": [stub],
        "errors": ["[policy_node] STUB ACTIVE — Member B has not landed yet"],
    }

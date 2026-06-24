"""RiskScorer — Member C's node.

STUB so Member A's graph runs end-to-end. Member C replaces the body:

  1. For each Finding in state.findings: call Groq (or Claude fallback)
     with_structured_output(ScoredFinding) to produce severity + likelihood
     + exposure_score + jurisdiction_attaches.
  2. Run validators: rule_id exists, severity-band/exposure-score aligned,
     evidence_quote actually in the packet.
  3. If a validator fails → set needs_human_review=True instead of crashing.
  4. Return {"scored_findings": [...]}.

DO NOT change the function signature.
"""
from __future__ import annotations

from hireguard.state import Finding, PipelineState, ScoredFinding


async def risk_node(state: PipelineState) -> dict:
    """STUB. Member C replaces this body."""
    scored: list[ScoredFinding] = []
    for f in state.findings:
        scored.append(
            ScoredFinding(
                finding=f,
                severity="medium",
                likelihood=0.5,
                jurisdiction_attaches=True,
                exposure_score=35,
                scorer_rationale="STUB — Member C will replace.",
                needs_human_review=True,
            )
        )
    return {
        "scored_findings": scored,
        "errors": ["[risk_node] STUB ACTIVE — Member C has not landed yet"],
    }

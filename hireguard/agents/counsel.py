"""CounselAgent — Member D's node.

STUB so Member A's graph runs end-to-end. Member D replaces the body:

  1. LLM (Claude Sonnet) with_structured_output(AuditMemo).
  2. Compute critical/high/medium/low counts from state.scored_findings.
  3. Set needs_re_review = True iff any critical finding has
     evidence_quality < 0.6 — that drives A's conditional edge.
  4. Return {"audit_memo": memo, "revision_count": state.revision_count + 1}.

DO NOT change the function signature.
"""
from __future__ import annotations

from hireguard.state import AuditMemo, PipelineState, RecommendedFix


async def counsel_node(state: PipelineState) -> dict:
    """STUB. Member D replaces this body."""
    sf = state.scored_findings
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for s in sf:
        counts[s.severity] += 1

    needs_re_review = any(
        s.severity == "critical" and s.finding.evidence_quality < 0.6 for s in sf
    )

    memo = AuditMemo(
        executive_summary=(
            f"STUB MEMO — Member D will replace. Reviewed {len(sf)} finding(s) "
            f"({counts['critical']} critical, {counts['high']} high, "
            f"{counts['medium']} medium, {counts['low']} low)."
        ),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        scored_findings=sf,
        recommended_fixes=[
            RecommendedFix(
                finding_id=s.finding.finding_id,
                fix_text="STUB fix — Member D will replace.",
                priority="should_fix",
            )
            for s in sf
        ],
        needs_re_review=needs_re_review,
        re_review_reason="Thin Critical evidence" if needs_re_review else None,
    )
    return {
        "audit_memo": memo,
        "revision_count": state.revision_count + 1,
        "errors": ["[counsel_node] STUB ACTIVE — Member D has not landed yet"],
    }

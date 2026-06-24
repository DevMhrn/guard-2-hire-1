"""PolicyAgent — Member B's node.

Scope: INDIAN hiring-compliance law (Code on Wages 2019, RPwD Act 2016,
Transgender Persons Act 2019, Maternity Benefit Act 1961, HIV/AIDS Act 2017,
Constitution Arts. 14/15/16 — see hireguard/rag/ruleset.json).

Pipeline:
  1. Build a retrieval query from state.facts (Intake's output).
  2. retrieve_rules(...) — hybrid RAG: jurisdiction filter (India-Central + the
     role's state) + semantic ranking (see hireguard/tools/retrieve_rules.py).
  3. Claude with_structured_output(PolicyFindings) decides, per retrieved rule,
     whether the packet violates it → list[Finding].
     (Offline / no ANTHROPIC_API_KEY → deterministic heuristic fallback, so the
     graph still runs and the demo never hard-blocks.)
  4. Guardrail: drop any finding whose rule_id is not in the retrieved set
     (no fabricated citations leave this node).
  5. Return {"findings": [...]} (+ errors notes). On a re-check loop, also bump
     revision_count so the bounded loop terminates.

Signature + return shape are fixed by Member A's graph wiring — do not change them.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, Field

from hireguard.settings import settings
from hireguard.state import Finding, HiringPacket, IntakeFacts, PipelineState
from hireguard.tools.fetch_indian_statute import fetch_indian_statute
from hireguard.tools.retrieve_rules import retrieve_rules

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "policy.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

TOP_K = 10

# ─── LLM tool-calling configuration ─────────────────────────────────────────
# Policy keeps `retrieve_rules` as a deterministic CODE call — the RAG pattern
# is reliability-critical and the LLM has no business deciding whether to
# retrieve. But `fetch_indian_statute` is genuinely LLM-decision territory:
# the LLM may verify exact statute wording when a citation references a
# recently-amended statute (RPwD 2016, Transgender 2019, HIV/AIDS 2017).
POLICY_TOOLS = [fetch_indian_statute]
TOOL_MAP = {t.name: t for t in POLICY_TOOLS}
MAX_TOOL_ROUNDS = 2  # cap — typically 0-2 statute verifications per audit

# Broad seed of Indian-law signal terms so retrieval ranks the relevant rules
# even when the structured facts are sparse. Covers all 12 IND-* rules across
# every employment sector — IT, manufacturing, hospitality, sales, BPO,
# healthcare, finance, gig / contract — grounded in Constitution Arts 14/15/16.
_QUERY_SEED = (
    "gender caste religion community marital status pregnancy maternity "
    "disability transgender third gender HIV medical test age domicile "
    "native language local subjective culture fit recruitment discrimination "
    "POSH Act 2013 internal complaints committee workplace safety night shift "
    "field travel customer facing women safety harassment "
    "working hours overtime 24x7 availability always on call exploitation "
    "Code on Wages 2019 Shops Establishments Act Factories Act rest period "
    "Constitution Article 14 15 16 equality non-arbitrariness "
    "any employment IT manufacturing hospitality sales BPO healthcare finance gig contract"
)

# Maps each India-specific IntakeFacts signal field (populated with exact quotes
# by the Intake agent) to the rule it evidences. Lets Policy cite a violation
# directly from the structured facts, even when the posting's wording does not
# match a detection hint verbatim (e.g. "Maharashtra domicile" -> IND-DOMICILE-LANGUAGE).
_SIGNAL_RULE_MAP = {
    "gender_restrictive_phrases": "IND-GENDER-CODED",
    "caste_or_community_signals": "IND-CASTE-RELIGION",
    "marital_or_pregnancy_signals": "IND-MATERNITY-MARITAL",
    "medical_or_hiv_test_signals": "IND-HIV-MEDICAL",
    "non_essential_physical_requirements": "IND-DISABILITY-RPWD",
    "domicile_or_language_restriction": "IND-DOMICILE-LANGUAGE",
    "age_coded_phrases": "IND-AGE-BAR",
    "subjective_scorecard_criteria": "IND-SUBJECTIVE-CRITERIA",
}


def _signal_phrases(facts: IntakeFacts) -> list[str]:
    """All exact phrases Intake lifted across the India signal fields."""
    out: list[str] = []
    for field in _SIGNAL_RULE_MAP:
        out += [p for p in (getattr(facts, field, []) or []) if p]
    return out


class PolicyFindings(BaseModel):
    """Bag model — `with_structured_output` is more reliable with a wrapper than
    with a bare `list[Finding]` (see PROJECT_PLAN §11 risk register)."""

    findings: list[Finding] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Query + context building
# ──────────────────────────────────────────────────────────────────────────────


def build_query(facts: IntakeFacts) -> str:
    """Turn the extracted facts into a retrieval query for semantic matching."""
    parts: list[str] = _signal_phrases(facts)
    if facts.notes:
        parts.append(facts.notes)
    parts.append(_QUERY_SEED)
    return " ".join(p for p in parts if p).strip()


def _scorecard_text(packet: HiringPacket) -> str:
    lines = []
    for c in packet.interview_scorecard.criteria:
        seg = c.name
        if c.note:
            seg += f": {c.note}"
        lines.append(seg)
    return "\n".join(lines)


def _packet_context(packet: HiringPacket) -> str:
    cb = packet.comp_band
    return (
        f"## JOB POSTING\n{packet.job_posting}\n\n"
        f"## COMP BAND\n"
        f"  currency: {cb.currency}\n"
        f"  posted_range_in_listing: {cb.posted_range_in_listing}\n\n"
        f"## INTERVIEW SCORECARD ({packet.interview_scorecard.title})\n"
        f"{_scorecard_text(packet)}\n"
    )


def _facts_context(facts: IntakeFacts) -> str:
    lines = [f"jurisdiction: {facts.jurisdiction}"]
    for field in _SIGNAL_RULE_MAP:
        vals = getattr(facts, field, []) or []
        if vals:
            lines.append(f"{field}: {vals}")
    if facts.notes:
        lines.append(f"notes: {facts.notes}")
    return "\n".join(lines) + "\n"


def _rules_context(rules: list[dict]) -> str:
    blocks = []
    for r in rules:
        blocks.append(
            f"### {r['rule_id']}  [{r['jurisdiction']}]\n"
            f"- citation: {r['citation']}\n"
            f"- summary: {r['summary']}\n"
            f"- detection_hints: {r['detection_hints']}\n"
        )
    return "\n".join(blocks)


def _build_user_message(facts: IntakeFacts, packet: HiringPacket, rules: list[dict]) -> str:
    return (
        f"# EXTRACTED FACTS\n{_facts_context(facts)}\n"
        f"# RETRIEVED RULES (only these rule_ids are valid)\n{_rules_context(rules)}\n"
        f"# THE PACKET\n{_packet_context(packet)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Heuristic fallback (no LLM key) — deterministic rule-vs-text matcher
# ──────────────────────────────────────────────────────────────────────────────


def _phrase_in(hint: str, text: str) -> bool:
    """Word-boundary match — so a short hint like 'he will' does not match inside
    a larger word. Lookarounds (not \\b) so hints with non-word edges still work."""
    h = hint.strip().lower()
    if not h:
        return False
    return re.search(r"(?<!\w)" + re.escape(h) + r"(?!\w)", text.lower()) is not None


def _segments(packet: HiringPacket) -> list[str]:
    segs: list[str] = []
    for chunk in re.split(r"[\n.]+", packet.job_posting):
        chunk = chunk.strip()
        if chunk:
            segs.append(chunk)
    for c in packet.interview_scorecard.criteria:
        segs.append(c.name + (f": {c.note}" if c.note else ""))
    return segs


def _heuristic_findings(facts: IntakeFacts, packet: HiringPacket, rules: list[dict]) -> list[Finding]:
    by_rule = {r["rule_id"]: r for r in rules}
    segments = _segments(packet)
    hay = " \n ".join(segments)
    found: dict[str, Finding] = {}

    # Pass 1 — facts-driven: use the exact phrases Intake lifted (best evidence).
    for field, rule_id in _SIGNAL_RULE_MAP.items():
        phrases = [p for p in (getattr(facts, field, []) or []) if p]
        if phrases and rule_id in by_rule and rule_id not in found:
            r = by_rule[rule_id]
            found[rule_id] = Finding(
                rule_id=rule_id,
                citation=r["citation"],
                evidence_quote=("; ".join(phrases))[:500],
                evidence_quality=0.95,
                rationale=f"{r['title']} — Intake flagged: {phrases[0]}",
            )

    # Pass 2 — posting-text hint match (recall-first; catches what Intake missed).
    for r in rules:
        if r["rule_id"] in found:
            continue
        evidence: Optional[str] = None
        for hint in r["detection_hints"]:
            if _phrase_in(hint, hay):
                for seg in segments:
                    if _phrase_in(hint, seg):
                        evidence = seg[:500]
                        break
                break
        if evidence is None:
            continue
        found[r["rule_id"]] = Finding(
            rule_id=r["rule_id"],
            citation=r["citation"],
            evidence_quote=evidence[:500],
            evidence_quality=0.9,
            rationale=f"{r['title']} — packet text matches a detection hint for this rule.",
        )
    return list(found.values())


# ──────────────────────────────────────────────────────────────────────────────
# LLM tool-calling path — two-phase (reason w/ tools → structured output)
# ──────────────────────────────────────────────────────────────────────────────


async def _llm_findings_with_tools(
    *,
    facts: IntakeFacts,
    packet: HiringPacket,
    rules: list[dict],
    errors: list[str],
) -> list[Finding]:
    """LLM path with tool-binding.

    Architecture:
      Phase 1 — Reason about which findings apply to the retrieved rules, and
                optionally call fetch_indian_statute to verify exact wording
                before citing recently-amended statutes. Capped at 2 rounds.
      Phase 2 — Force structured output (PolicyFindings) from the accumulated
                reasoning history.

    `retrieve_rules` deliberately stays as a code-call (not tool-bound) — the
    RAG retrieval pattern is reliability-critical for grounded findings; the
    LLM should not decide whether to retrieve.
    """
    from hireguard.llm import get_claude

    user_msg = _build_user_message(facts, packet, rules)

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    llm_with_tools = get_claude().bind_tools(POLICY_TOOLS)
    total_tool_calls = 0
    for round_n in range(MAX_TOOL_ROUNDS):
        response: AIMessage = await llm_with_tools.ainvoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            tool = TOOL_MAP.get(name)
            total_tool_calls += 1
            log.info(
                "policy_node: LLM tool call #%d → %s(%s)",
                total_tool_calls,
                name,
                str(args)[:120],
            )
            if tool is None:
                tool_out = f"unknown tool: {name}"
                errors.append(f"[policy_node] LLM tried unknown tool {name!r}")
            else:
                try:
                    tool_out = await tool.ainvoke(args)
                except Exception as exc:  # noqa: BLE001
                    tool_out = (
                        f"tool error: {type(exc).__name__}: {str(exc)[:120]}"
                    )
                    errors.append(
                        f"[policy_node] tool {name} errored: {type(exc).__name__}"
                    )
            messages.append(
                ToolMessage(
                    content=str(tool_out),
                    tool_call_id=tc.get("id", f"call-{total_tool_calls}"),
                )
            )

    if total_tool_calls:
        errors.append(
            f"[policy_node] LLM made {total_tool_calls} tool call(s) "
            f"to fetch_indian_statute"
        )

    # Phase 2: force the typed PolicyFindings using the full reasoning history.
    final_prompt = HumanMessage(
        content=(
            "Based on the rules I retrieved + any statute verifications you "
            "performed, emit the final PolicyFindings — one Finding per "
            "violation you are confident the packet commits. Cite ONLY rule_ids "
            "from the retrieved set. Quote exact evidence from the packet."
        )
    )
    llm_typed = get_claude().with_structured_output(PolicyFindings)
    result: PolicyFindings = await llm_typed.ainvoke(messages + [final_prompt])
    return result.findings


# ──────────────────────────────────────────────────────────────────────────────
# Node
# ──────────────────────────────────────────────────────────────────────────────


async def policy_node(state: PipelineState) -> dict:
    facts = state.facts
    packet = state.packet
    errors: list[str] = []

    if facts is None:
        return {"findings": [], "errors": ["[policy_node] no facts in state — Intake did not run"]}

    query = build_query(facts)
    rules = retrieve_rules(query, facts.jurisdiction, k=TOP_K)
    valid_ids = {r["rule_id"] for r in rules}
    log.info("policy_node: retrieved %d rules for %s: %s",
             len(rules), facts.jurisdiction, sorted(valid_ids))

    use_llm = bool(settings()["ANTHROPIC_API_KEY"])
    if use_llm:
        try:
            findings = await _llm_findings_with_tools(
                facts=facts, packet=packet, rules=rules, errors=errors
            )
        except Exception as exc:  # never fail the audit on an LLM hiccup
            log.warning("policy_node: LLM call failed (%s); using heuristic fallback", exc)
            errors.append(f"[policy_node] LLM failed, heuristic fallback used: {exc}")
            findings = _heuristic_findings(facts, packet, rules)
    else:
        errors.append("[policy_node] no ANTHROPIC_API_KEY — deterministic heuristic findings")
        findings = _heuristic_findings(facts, packet, rules)

    # Guardrail: drop any fabricated rule_id (must come from the retrieved set).
    clean: list[Finding] = []
    for f in findings:
        if f.rule_id in valid_ids:
            clean.append(f)
        else:
            errors.append(f"[policy_node] dropped finding citing unknown rule_id={f.rule_id}")

    # Optional best-effort freshness check (2nd external API). Off by default;
    # never blocks or changes which findings surface — just annotates the trace.
    try:
        from hireguard.tools.statute_lookup import is_enabled, verify_statute_currency

        if is_enabled():
            for rid in sorted({f.rule_id for f in clean}):
                sig = verify_statute_currency.invoke(
                    {"rule_id": rid, "citation": "", "statute_short_name": rid}
                )
                if not sig.get("is_current", True):
                    errors.append(f"[policy_node] statute currency check flagged {rid}")
    except Exception as exc:  # pragma: no cover
        log.warning("policy_node: Tavily enrichment skipped (%s)", exc)

    out: dict = {"findings": clean, "errors": errors}

    # Re-check loop bookkeeping: if Counsel already produced a memo, this is a
    # re-entry — bump revision_count so the bounded loop in graph.py terminates.
    # (revision_count has no reducer, so we set the new absolute value.)
    if state.audit_memo is not None:
        out["revision_count"] = state.revision_count + 1
        errors.append(f"[policy_node] re-check pass #{state.revision_count + 1}")

    log.info("policy_node: %d findings (%d after guardrail)", len(findings), len(clean))
    return out

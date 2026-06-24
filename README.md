# HireGuard v2 — Member A's first draft

Multi-agent hiring-compliance auditor. **Read `PROJECT_PLAN.md` first** for the
full design + your individual brief.

This first draft lands the **orchestration spine** so B/C/D are unblocked:

- ✅ Pydantic state contract (`hireguard/state.py`)
- ✅ LangGraph `StateGraph` with conditional edges + HITL `interrupt()`
- ✅ Supabase Postgres checkpointer (uses transaction pooler, IPv4-safe)
- ✅ Real `IntakeAgent` with PII redaction + prompt-injection flagging
- ✅ **Stub** Policy / Risk / Counsel agents so the pipeline runs end-to-end TODAY
- ✅ CLI demo (`python run_demo.py --sample acme_se_role`)
- ✅ Streamlit UI shell (3 tabs: Run / Approve / History)
- ✅ Schema migrations applied to Supabase (`audit_memos`, `rules`, `rule_detection_hints`, pgvector enabled)
- ✅ 12 tests passing (`make eval`)

## Quick start

```bash
make install            # creates .venv, installs deps
cp .env.example .env    # fill in ANTHROPIC_API_KEY (+ LangSmith optional)
make migrate            # already done — idempotent
make demo               # opens the Streamlit UI — THE demo
make cli                # headless CLI fallback (dev / debugging / demo backup)
make eval               # runs the 12 schema + smoke tests
```

`.env` already has the Supabase creds. Drop your `ANTHROPIC_API_KEY` in to run
the real intake. Without it, the stubs still work (tests pass without any LLM key).

## Where your work goes (B / C / D)

| Member | File to replace | Spec |
|---|---|---|
| **Gowtham (B)** | `hireguard/agents/policy.py` | §7.2 of `PROJECT_PLAN.md` — pgvector retrieval + Findings |
| **Harsh (C)** | `hireguard/agents/risk.py` | §7.3 — Groq structured-output ScoredFinding + validators |
| **Aditya (D)** | `hireguard/agents/counsel.py` + `tests/eval_scenarios.py` | §7.4 — AuditMemo + 5+ scenarios |

Each stub returns a valid Pydantic object so the rest of the graph runs. Replace
the body of the `*_node` function. **Do not change the function signature.**

## What runs without your changes

The graph already executes intake → policy(stub) → risk(stub) → counsel(stub)
→ HITL pause → approve → end → persist-to-Supabase. So you can:

1. Start your work whenever — the graph won't break.
2. Validate your node in isolation by importing `PipelineState` and calling
   your `*_node` function directly.
3. Run `make demo` after landing your changes to see your node light up.

## Architecture summary

```
START → intake → policy → risk → counsel ──(cond)──► human_review ──(cond)──► END
                            ▲                  │                     │
                            └────── send_back ─┘                     │
                            └────── re-check ──────────────────────  ┘ (cap: 2 loops)
```

See `PROJECT_PLAN.md` §3 and §7.5 (rubric coverage) for details.

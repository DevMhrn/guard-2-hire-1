# 🛡 SafeHire

**A multi-agent AI auditor for Indian hiring compliance.** SafeHire reads a company's hiring packet (job posting + compensation band + interview scorecard), checks it against Indian employment law, produces a cited audit memo, and routes every recommendation through a human reviewer before anything is published.

Built for the *Multi-Agent Orchestration (AI/ML)* capstone — LangGraph + Claude + Supabase + LangSmith.

---

## What problem we solve

Companies in India publish hiring artifacts every day that unintentionally violate Indian employment law. The violations are:

- **Distributed across artifacts** — a clean-looking job posting can hide bias in the scorecard or pay band.
- **Spread across legal areas** — gender (Code on Wages 2019), caste/religion (Constitution Arts. 15/16), marital status / pregnancy (Maternity Benefit Act 1961), disability (RPwD Act 2016), HIV/medical status (HIV/AIDS Act 2017), age (general fairness), domicile (Constitution Art. 16), subjective criteria (disparate-impact doctrine), workplace safety (POSH Act 2013).
- **Subtle** — a scorecard criterion *"culture fit — feels like one of us"* is disparate-impact risk; *"Marathi fluency for shop-floor instruction"* is a defensible operational requirement. Context matters.

A single human reviewer is slow and inconsistent. A single LLM prompt is either too broad to be reliable or too narrow to catch everything. SafeHire splits the job across four specialised agents that hand off typed data, route through a human gate, and trace every step.

## Why multi-agent

| Agent | Job | Why a dedicated agent |
|---|---|---|
| 🪪 **Intake** | Read the packet, redact PII, detect prompt injection, extract Indian-law signals as typed facts | Fast structured extraction — its own prompt + fast LLM tier |
| 📜 **Policy** | Retrieve relevant compliance rules via pgvector + LLM-decide which statutes to verify; emit cited findings | Needs RAG grounding + LLM tool-calling. Specialised prompt + retrieval |
| ⚖️ **Risk** | Score each finding's severity, likelihood, statutory exposure (0–100) | Calibrated scoring + three deterministic validators that prevent fabricated citations |
| ✍️ **Counsel** | Write the audit memo, optionally call `web_search` + `verify_statute_currency` for case-law context | Synthesis with LangChain tool-calling — different model + prompt than Policy |
| 🙋 **Human reviewer** | Approve / Reject / Send back via `interrupt()` HITL gate | The legal-decision authority. No memo is published without this |

Wired through a LangGraph `StateGraph` with two conditional edges (Counsel→Policy re-loop on weak evidence; Human→Policy on send-back). State is checkpointed in Supabase Postgres — a run can resume across a HITL pause.

## What's in the system

- **5-stage LangGraph pipeline** with bounded self-correction loop
- **12 cited Indian compliance rules** with pgvector embeddings
- **Real LangChain tool-calling** — Policy binds `fetch_indian_statute`; Counsel binds `verify_statute_currency` + `web_search`
- **Two-phase reasoning** per LLM agent: tool-call loop first, then forced structured output
- **Pydantic state contract** so every agent boundary is type-checked
- **9 hand-authored Indian sample packets** spanning 6 states and 8 industries
- **Live in-product log** showing every agent step + every LLM/tool call as it happens
- **LangSmith APAC tracing** auto-enabled when key is set
- **Three-tab Streamlit UI** (Run Audit / Pending Approval / History) + CLI fallback
- **52 tests passing** including HITL-gate-integrity and prompt-injection refusal

## Quick start

```bash
make install            # python -m venv .venv + pip install -e ".[dev]"
cp .env.example .env    # add ANTHROPIC_API_KEY (+ optionally TAVILY + LangSmith)
make migrate            # applies Supabase schema (idempotent)
make seed               # embeds the 12 rules + detection hints into pgvector
make demo               # opens the Streamlit UI on http://localhost:8501
make cli                # headless CLI fallback for debugging / demo backup
make eval               # runs 52 tests (hermetic — no API keys needed)
```

## Architecture at a glance

```
       ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
INPUT ─►│ Intake │──►│ Policy │──►│  Risk  │──►│Counsel │──┐
       └────────┘   └────────┘   └────────┘   └────────┘  │
                         ▲                                │
                         │   thin Critical evidence       │
                         └──── (max 2 re-loops) ◄─────────┤
                                                          │
                                              ┌───────────▼───────────┐
                                              │  Human Review (HITL)  │
                                              │  approve / reject /   │
                                              │  send_back            │
                                              └─────────┬─────────────┘
                                                        │
                                              ┌─────────▼─────────────┐
                                              │  Persist to Supabase  │
                                              └───────────────────────┘
```

## Tech stack

- **Orchestration:** LangGraph (`StateGraph`, conditional edges, `interrupt()`, `PostgresSaver`)
- **LLMs:** Anthropic Claude (Sonnet for reasoning, Haiku for extraction); Groq Llama 3.3 for fast scoring
- **State:** Pydantic v2 with `with_structured_output` enforcement
- **RAG:** Supabase Postgres + pgvector + OpenAI embeddings + custom `match_rules` RPC
- **Tools (LLM-bound):** `fetch_indian_statute`, `verify_statute_currency`, `web_search` — all Tavily-backed
- **Observability:** LangSmith APAC tenant + custom in-product `StreamlitLogHandler`
- **Frontend:** Streamlit with light-theme custom CSS

## Scope — any Indian employment type

SafeHire applies **across any Indian employment type** — IT services, manufacturing, hospitality, sales, BPO, healthcare, finance, internships, gig/contract, and public-sector hiring.

Compliance rules are grounded in:

- **Constitutional values** — Articles 14 (equality), 15 (non-discrimination on religion / race / caste / sex / place of birth), 16 (equality of opportunity in employment)
- **Union/Central statutes** — Code on Wages 2019, RPwD Act 2016, Maternity Benefit Act 1961, Transgender Persons (Protection of Rights) Act 2019, HIV/AIDS (Prevention & Control) Act 2017, POSH Act 2013
- **Operational doctrines** — disparate-impact reasoning, bona-fide occupational requirement standard

## Team

| Member | Slice |
|---|---|
| **Dev (Member A)** | Orchestration spine, IntakeAgent, Streamlit demo surface, observability |
| **Gowtham (Member B)** | PolicyAgent + hybrid retrieval (pgvector) + Tavily statute-freshness check |
| **Harsh (Member C)** | RiskScorer + the three validators that prevent fabricated citations |
| **Aditya (Member D)** | CounselAgent + 7 scenario evals + CI workflow + failure-modes appendix |



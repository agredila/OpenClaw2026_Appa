# RADAR — Scoring Rubric Analysis

Self-assessment against judging criteria. Honest gaps included.

---

## 1. Use Case Clarity & Impact (10%)

**Target: 9.5/10**

- Problem is concrete and quantified: professionals miss business opportunities in noisy Telegram/Discord groups
- Pain is universal to freelancers and agencies in Indonesia
- Impact is measurable: time saved per week, proposals sent per opportunity detected
- Two distinct use cases: opportunity pipeline + LinkedIn contact intelligence

**What could lower this score:** narrow audience (requires Telegram/Discord monitoring setup)

---

## 2. Creativity & Originality (30%)

**Target: 9.0/10**

Differentiators that don't exist in any single product today:
- **APPA self-rewriting scoring prompt** — agent rewrites its own judgment criteria weekly based on user feedback
- **Persona-aware proposals** — Pippoy matches the user's writing style from past accepted proposals
- **Competitor detection** — Pippi detects if others have already responded to the same post
- **Clarification sub-loop** — APPA posts a question back to the source channel for ambiguous messages
- **"Why RADAR flagged this" card** — every alert explains APPA's reasoning in plain language

**What could lower this score:** individual components (LLM classifier, proposal drafter) exist separately elsewhere

---

## 3. Autonomy & Agent Behaviour (30%)

**Target: 9.5/10**

Evidence of genuine autonomy:
- Continuous monitoring with no human trigger (Kiyo)
- Multi-step reasoning with visible chain-of-thought (APPA)
- Dynamic routing based on runtime scoring (APPA)
- Clarification sub-loop for ambiguous cases (APPA)
- Sequential dependency enforcement: Pippoy waits for Pippi (correct agent design)
- Parallel paths: opportunity pipeline and LinkedIn path run independently
- Self-improvement: APPA rewrites its own scoring prompt weekly (appa_learner.py)
- Graceful degradation: timeouts produce partial alerts, never silent failures

**What could lower this score:** clarification reply handling is async (Hermes/QwenPaw gateway dependent)

---

## 4. Technical Execution (20%)

**Target: 8.5/10**

- Clean separation of concerns: each agent is a single-responsibility Python module
- Shared infrastructure in `base.py` — no duplication across agents
- Canonical types in `types.py` — single source of truth for all data models
- Guard pattern (`guard.py`) as cross-cutting concern — not mixed into business logic
- Sequential Pippi→Pippoy enforced at code level, not by convention
- All files pass `python3 -m py_compile` syntax check
- No hardcoded credentials anywhere — verified by grep scan
- Docker Compose for reproducible deployment

**What could lower this score:** no automated test suite (time constraint); Drive API error handling is basic

---

## 5. Real-World Deployability (10%)

**Target: 9.0/10**

- Single `docker-compose up` deploys entire system on SumoPod VPS
- `.env.example` documents every required variable
- Budget fits within Rp 100.000: Rp 45.000 VPS + ~$3.30 model API
- QwenPaw handles Telegram/Discord gateway — no custom webhook server needed
- Rate limiter prevents runaway API costs in production
- `docs/autonomous-loop.md` explicitly documents the loop for jury review

**What could lower this score:** no auth on dashboard; first-run onboarding not yet implemented

---

## Projected Weighted Score

| Criterion | Weight | Score | Weighted |
|---|---|---|---|
| Use Case Clarity & Impact | 10% | 9.5 | 0.95 |
| Creativity & Originality | 30% | 9.0 | 2.70 |
| Autonomy & Agent Behaviour | 30% | 9.5 | 2.85 |
| Technical Execution | 20% | 8.5 | 1.70 |
| Real-World Deployability | 10% | 9.0 | 0.90 |
| **Total** | | | **9.10 / 10** |

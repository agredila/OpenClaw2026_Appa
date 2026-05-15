# RADAR Autonomous Loop

> Jury note: This document explicitly describes RADAR's autonomous loop as required by the judging criteria.

## The Loop

RADAR runs continuously without human intervention. Here is the exact sequence:

```
[QwenPaw cron — continuous monitoring]
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  STEP 1: KIYO — Scout & Listener                    │
│  File: skills/kiyo.py                               │
│  No human trigger. Reads every message.             │
│  Tool: classify_opportunity(text)                   │
│  Tool: flag_linkedin_url(text)                      │
│  → type: opportunity | linkedin_url | noise         │
│  Noise → silently discarded, zero cost              │
└─────────────────────────────────────────────────────┘
         │ OpportunityPayload
         ▼
┌─────────────────────────────────────────────────────┐
│  STEP 2: APPA — Orchestrator                        │
│  File: skills/appa.py                               │
│  Tool: reason(payload) → streaming chain-of-thought │
│  Tool: score_routing() → 1–10                       │
│  Tool: check_and_increment() → cost guard           │
│                                                     │
│  score < 4  → reject_if_noise() → log + stop        │
│  score 4–6  → reply_for_clarification()             │
│               Post question to source channel       │
│               Wait for reply → re-score → continue  │
│  score 7+   → delegate_to_pippi()                   │
│               delegate_to_cepoy() if LinkedIn URL   │
└─────────────────────────────────────────────────────┘
         │
    ┌────┴──────────────────┐
    │ opportunity path       │ linkedin path
    ▼                        ▼
┌──────────────┐    ┌──────────────────────┐
│ PIPPI        │    │ CEPOY                │
│ skills/      │    │ skills/cepoy.py      │
│ pippi.py     │    │                      │
│              │    │ Tool: fetch_public_  │
│ Tool: search_│    │   profile(url)       │
│  market_     │    │ Tool: search_web()   │
│  context()   │    │ Tool: summarize_     │
│ Tool: fetch_ │    │   profile()          │
│  company_    │    │ Tool: generate_      │
│  info()      │    │   warm_intro()       │
│ Tool: score_ │    │ Tool: save_to_       │
│  fit()       │    │   firestore()        │
│ Tool: detect_│    └──────────────────────┘
│  competitors()│            │
└──────────────┘             │
         │ ResearchContext    │
         ▼ (sequential)       │
┌──────────────┐             │
│ PIPPOY       │             │
│ skills/      │             │
│ pippoy.py    │             │
│              │             │
│ Tool: load_  │             │
│  past_       │             │
│  proposals() │             │
│ Tool: draft_ │             │
│  proposal()  │             │
│ Tool: save_  │             │
│  to_drive()  │             │
└──────────────┘             │
         │ Drive link         │
         └────────┬───────────┘
                  │ full summary
                  ▼
┌─────────────────────────────────────────────────────┐
│  STEP 3: PIYO — Notifier                            │
│  File: skills/piyo.py                               │
│  Tool: build_leaderboard() → rank by APPA score     │
│  Tool: compose_alert() → "Why RADAR flagged" card   │
│  Tool: send_gmail_alert() → Gmail + Drive link      │
│  Tool: send_telegram_dm() → DM + ✅/❌ buttons      │
└─────────────────────────────────────────────────────┘
         │ user taps ✅ or ❌
         ▼
┌─────────────────────────────────────────────────────┐
│  STEP 4: FEEDBACK → SELF-IMPROVEMENT                │
│  File: skills/appa_learner.py                       │
│  handle_feedback() → writes signal to Firestore     │
│                                                     │
│  Every Sunday 08:00 WIB (QwenPaw cron):             │
│  Tool: load_feedback() → last 7 days ✅/❌          │
│  Tool: rewrite_scoring_prompt() → LLM rewrites      │
│         APPA's own scoring criteria                 │
│  Tool: save_new_version() → Firestore v{n}          │
│  APPA loads new criteria on next run                │
└─────────────────────────────────────────────────────┘
         │
         └──────────────────────────────────────────┐
                                                    │
                                    Loop repeats, smarter than before
```

## Why This Qualifies as an Autonomous Loop

1. **No human trigger** — Kiyo monitors channels continuously via QwenPaw gateway. Zero manual intervention required.
2. **Autonomous decision-making** — APPA decides to process, reject, or ask for clarification without human input. Every decision is logged.
3. **Dynamic tool usage** — each agent calls external tools (Google Search, Drive API, Gmail, Telegram Bot API) based on runtime context, not hardcoded paths.
4. **Self-correction sub-loop** — ambiguous messages (score 4–6) trigger a clarification loop: APPA posts a question to the source channel, waits for reply, re-scores, then continues or rejects.
5. **Self-improvement loop** — APPA rewrites its own scoring prompt weekly based on user feedback. The agent's judgment improves over time without developer intervention.
6. **Edge case handling** — Guard (skills/guard.py) enforces daily limits and per-agent timeouts. Pipeline degrades gracefully: if Pippi times out, Piyo still delivers with "research unavailable" note.

## Agent → Tool → External Service Map

| Agent | Tool Call | External Service |
|---|---|---|
| Kiyo | `classify_opportunity()` | SumoPod LLM API |
| APPA | `reason()` streaming | SumoPod LLM API |
| APPA | `reply_for_clarification()` | Telegram Bot API |
| Pippi | `search_market_context()` | Google Custom Search |
| Pippi | `detect_competitors()` | Google Custom Search |
| Pippoy | `load_past_proposals()` | Firestore |
| Pippoy | `draft_proposal()` | SumoPod LLM API |
| Pippoy | `save_to_drive()` | Google Drive API |
| Cepoy | `fetch_public_profile()` | Google Custom Search |
| Cepoy | `save_to_firestore()` | Firestore |
| Piyo | `send_gmail_alert()` | Gmail API |
| Piyo | `send_telegram_dm()` | Telegram Bot API |
| APPA Learner | `rewrite_scoring_prompt()` | SumoPod LLM API |

## Scheduled Automations (QwenPaw cron)

| Schedule | UTC | WIB | Action | File |
|---|---|---|---|---|
| Continuous | — | — | Kiyo monitors channels | `skills/kiyo.py` |
| `0 0 * * *` | 00:00 | 07:00 | Morning LinkedIn digest | `skills/piyo.py` |
| `0 1 * * 0` | 01:00 Sun | 08:00 Sun | APPA self-improvement | `skills/appa_learner.py` |

## State Machine

All pipeline state lives in Firestore `pipelines/{pipeline_id}`:

```
initiated → research → proposal_ready → delivered
    ↓                                      ↑
awaiting_clarification ──────────────────→ (re-enters)
    ↓
rejected  (score < 4 or no clarification received)
    ↓
failed    (unhandled exception — logged, never silent)
```

## Firestore Collections

| Collection | Written by | Read by |
|---|---|---|
| `pipelines` | APPA, all agents | Dashboard, APPA Learner |
| `user_profiles` | Onboarding, APPA Learner | APPA, Pippi, Pippoy |
| `contacts` | Cepoy | Piyo (morning digest) |
| `usage` | Guard | Guard |
| `proposals` | Pippoy | Pippoy (style matching) |
| `scoring_prompt_history` | APPA Learner | Dashboard (diff view) |
| `clarifications` | APPA | QwenPaw gateway |

# RADAR Architecture

## Pipeline Flow

```
[Telegram Group / Discord Channel]
        |
        | webhook / gateway event
        ↓
┌─────────────────────────────────────────┐
│  KIYO — Scout & Listener                │
│  classify_opportunity(text)             │
│  → type: opportunity | linkedin | noise │
└─────────────────────────────────────────┘
        |
        | OpportunityPayload
        ↓
┌─────────────────────────────────────────┐
│  APPA — Orchestrator                    │
│  reason(payload) → streaming CoT        │
│  score_routing() → 1–10                 │
│                                         │
│  score < 4  → reject, log reason        │
│  score 4–6  → reply_for_clarification() │
│               wait → re-score           │
│  score 7+   → delegate                  │
│  linkedin   → delegate to Cepoy         │
└─────────────────────────────────────────┘
        |                    |
        | opportunity         | linkedin url
        ↓                    ↓
┌──────────────┐    ┌──────────────────────┐
│ PIPPI        │    │ CEPOY                │
│ Research     │    │ Contact Intelligence │
│ + competitor │    │ + warm intro         │
│ detection    │    │ → Firestore /contacts│
└──────────────┘    └──────────────────────┘
        |                    |
        | research context    | (morning digest path)
        ↓                    |
┌──────────────┐             |
│ PIPPOY       │             |
│ Persona-aware│             |
│ proposal     │             |
│ → Drive link │             |
└──────────────┘             |
        |                    |
        └──────────┬─────────┘
                   | full summary
                   ↓
        ┌─────────────────────────┐
        │ PIYO — Notifier         │
        │ leaderboard (rank opps) │
        │ "Why RADAR flagged"card │
        │ Gmail alert + Drive link│
        │ Telegram DM + ✅/❌ btns│
        └─────────────────────────┘
                   |
                   | ✅/❌ feedback
                   ↓
        ┌─────────────────────────┐
        │ APPA LEARNER (weekly)   │
        │ reads feedback signals  │
        │ rewrites scoring prompt │
        │ saves prompt v{n}       │
        └─────────────────────────┘
```

## Agent Contracts

### Kiyo
- **Input:** raw message text + source metadata
- **Output:** `OpportunityPayload`
- **Model:** MiniMax-M2.7-highspeed (fast, cheap, high-frequency)
- **Tools:** `classify_opportunity`, `extract_details`, `flag_linkedin_url`

### APPA
- **Input:** `OpportunityPayload`
- **Output:** routing decision + `PipelineState` written to Firestore
- **Model:** kimi-k2.6 (reasoning quality needed)
- **Tools:** `reason`, `score_routing`, `reject_if_noise`, `reply_for_clarification`, `delegate_*`, `update_state`
- **Special:** chain-of-thought streamed token-by-token to Firestore for dashboard

### Pippi
- **Input:** `PipelineState` with opportunity details
- **Output:** `ResearchContext` (market summary + competitor count + fit score)
- **Model:** kimi-k2.6
- **Tools:** `search_market_context`, `fetch_company_info`, `score_fit`, `detect_competitors`
- **Dependency:** reads `UserProfile` from Firestore

### Pippoy
- **Input:** `ResearchContext` (sequential — waits for Pippi)
- **Output:** Google Drive shareable link
- **Model:** kimi-k2.6
- **Tools:** `load_past_proposals`, `draft_proposal`, `save_to_drive`
- **Special:** persona-aware — matches user's writing style from past proposals

### Cepoy
- **Input:** LinkedIn URL
- **Output:** `ContactSummary` saved to Firestore `/contacts`
- **Model:** kimi-k2.6
- **Tools:** `fetch_public_profile`, `search_web`, `summarize_profile`, `generate_warm_intro`
- **Special:** Google Custom Search only — no scraping

### Piyo
- **Input:** full pipeline summary from APPA
- **Output:** Gmail alert + Telegram DM with inline buttons
- **Model:** MiniMax-M2.7-highspeed
- **Tools:** `build_leaderboard`, `compose_alert`, `send_gmail_alert`, `send_telegram_dm`, `handle_feedback`, `send_morning_digest`
- **Special:** "Why RADAR flagged this" card from APPA's reasoning trace

### APPA Learner
- **Input:** last 7 days of `pipeline.user_feedback` from Firestore
- **Output:** new scoring prompt version saved to Firestore
- **Model:** kimi-k2.6
- **Schedule:** Hermes cron — every Sunday 08:00 WIB

### Guard
- **Role:** cross-cutting concern, called by APPA before any delegation
- **Checks:** daily opportunity limit, per-agent timeout (30s), token budget
- **On limit hit:** log + skip gracefully, never crash pipeline

## State Machine (Firestore `pipelines/{id}`)

```
initiated → research → proposal_ready → delivered
                                      ↘ failed (partial delivery noted in alert)
```

## Data Models

See `skills/types.py` for canonical type definitions.

## Deployment

Single `docker-compose up` on SumoPod VPS.
QwenPaw handles: Telegram/Discord gateway, cron scheduling, multi-agent delegation, persistent memory.
RADAR skills are registered in `qwenpaw.yml` and loaded at startup.

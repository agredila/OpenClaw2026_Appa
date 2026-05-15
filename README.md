# RADAR — Real-time Autonomous Detection and Response

> 6-agent system that monitors Telegram & Discord for business opportunities, researches context, drafts proposals, enriches contacts, and delivers actionable alerts — autonomously.

## Agents

| # | Name | Role |
|---|---|---|
| 1 | **APPA** | Orchestrator — reasoning, scoring, delegation, self-improvement |
| 2 | **Kiyo** | Scout & Listener — classifies messages from Telegram & Discord |
| 3 | **Pippi** | Research — market context + competitor detection |
| 4 | **Pippoy** | Proposal Drafter — persona-aware, saves to Google Drive |
| 5 | **Piyo** | Notifier — "Why" card + feedback buttons + leaderboard |
| 6 | **Cepoy** | Contact Intelligence — LinkedIn enrichment + warm intro |

## Autonomous Loop

```
[QwenPaw cron — continuous]
    Kiyo monitors channels (no human trigger)
        ↓
    APPA reasons + scores (chain-of-thought streamed live)
        ↓
    score < 4  → reject + log reason
    score 4–6  → APPA asks clarifying question → re-score
    score 7+   → Pippi → Pippoy → Piyo
    LinkedIn   → Cepoy → morning digest via Piyo
        ↓
    User gives ✅/❌ feedback via Telegram inline button
        ↓
    APPA rewrites its own scoring prompt weekly
        ↓
    Loop repeats, smarter than before
```

## Stack

| Component | Tool |
|---|---|
| Agent runtime | QwenPaw (AgentScope) |
| Primary model | kimi-k2.6 via SumoPod API |
| Fast model | MiniMax-M2.7-highspeed via SumoPod API |
| State | Firestore |
| Search | Google Custom Search API |
| Storage | Google Drive API |
| Notifications | Gmail API + Telegram Bot |
| Scheduler | QwenPaw built-in cron |
| Deploy | Docker Compose on SumoPod VPS |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/agredila/OpenClaw2026_Appa
cd OpenClaw2026_Appa

# 2. Configure
cp .env.example .env
# Fill in all values in .env

# 3. Deploy (one command)
docker-compose up -d

# Console available at http://localhost:8088
```

## Local Development

```bash
pip install qwenpaw
qwenpaw init --defaults
# Edit qwenpaw.yml and .env
qwenpaw app
```

## Project Structure

```
skills/           # All 6 agent skills + guard + shared base
docs/             # Architecture docs, demo script, scoring rubric
qwenpaw.yml       # QwenPaw configuration
RADAR.context.md  # APPA persona + scoring prompt
docker-compose.yml
.env.example      # Template — never commit .env
```

## Budget

| Item | Cost |
|---|---|
| SumoPod VPS (QwenPaw) | Rp 45.000/mo |
| Model API (~1,650 runs) | ~$3.30 |
| Everything else | Free tier |

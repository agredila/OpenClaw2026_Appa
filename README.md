# RADAR — Real-time Autonomous Detection and Response

6-agent autonomous system that monitors Telegram & Discord for business opportunities, researches context, drafts proposals, enriches LinkedIn contacts, and delivers alerts via Gmail and Telegram DM — with a self-improving scoring loop.

## Architecture

```
Telegram/Discord → Kiyo → APPA → Pippi → Pippoy → Piyo → Gmail + Telegram DM
                              ↘ Cepoy → Piyo → Morning Digest
                              ↑
                         APPA Learner (weekly self-improvement)
```

**Agents:**

| File | Agent | Role |
|---|---|---|
| `skills/kiyo.py` | Kiyo | Classify messages: opportunity / linkedin_url / noise |
| `skills/appa.py` | APPA | Orchestrate: reason, score, route, stream chain-of-thought |
| `skills/pippi.py` | Pippi | Research: market context + competitor detection |
| `skills/pippoy.py` | Pippoy | Draft persona-aware proposal → save to Google Drive |
| `skills/cepoy.py` | Cepoy | Enrich LinkedIn contacts via Google Search |
| `skills/piyo.py` | Piyo | Deliver: Gmail alert + Telegram DM with feedback buttons |
| `skills/appa_learner.py` | APPA Learner | Rewrite APPA's scoring prompt weekly from feedback |
| `skills/guard.py` | Guard | Rate limiter + per-agent timeout |
| `skills/base.py` | — | Shared: LLM client, Firestore helpers, Google Search |
| `skills/types.py` | — | Canonical data models for all agents |

## Requirements

- Python 3.9+
- Docker + Docker Compose (for VPS deploy)
- Accounts needed: SumoPod API, Telegram Bot, Discord Bot, Google Cloud (Firestore + Drive + Gmail + Custom Search)

## Local Setup

```bash
# 1. Clone
git clone https://github.com/agredila/OpenClaw2026_Appa
cd OpenClaw2026_Appa

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — fill in all values (see .env.example for required keys)

# 4. Run tests (no API keys needed — all external calls are mocked)
python -m pytest tests/ -v

# 5. Start QwenPaw with RADAR skills
qwenpaw init --defaults
qwenpaw app
# Console at http://localhost:8088
```

## VPS Deploy (Docker)

```bash
cp .env.example .env
# Fill in .env

docker-compose up -d
# Console at http://localhost:8088
```

## Environment Variables

See `.env.example` for the full list. Required keys:

| Variable | Description |
|---|---|
| `SUMOPOD_API_KEY` | SumoPod AI API key |
| `SUMOPOD_API_BASE` | `https://api.sumopod.com/v1` |
| `MODEL_PRIMARY` | `kimi-k2.6` |
| `MODEL_FAST` | `MiniMax-M2.7-highspeed` |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_USER_CHAT_ID` | Your personal chat ID |
| `TELEGRAM_MONITOR_CHAT_IDS` | Comma-separated group IDs to monitor |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DISCORD_MONITOR_CHANNEL_IDS` | Comma-separated channel IDs |
| `GOOGLE_CUSTOM_SEARCH_API_KEY` | Google Custom Search API key |
| `GOOGLE_CUSTOM_SEARCH_ENGINE_ID` | Custom Search Engine ID |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | Path to Drive service account JSON |
| `GMAIL_CREDENTIALS_JSON` | Path to Gmail OAuth2 credentials JSON |
| `FIRESTORE_PROJECT_ID` | GCP project ID |
| `FIRESTORE_CREDENTIALS_JSON` | Path to Firestore service account JSON |
| `MAX_OPPORTUNITIES_PER_DAY` | Daily pipeline limit (default: 20) |

## Running Tests

Tests use mocks — no real API keys required:

```bash
python -m pytest tests/ -v
```

Tests cover: type validation, guard rate limiting, guard timeout, Kiyo classification (opportunity/noise/LinkedIn/malformed), APPA decision parsing, Cepoy URL parsing, APPA Learner skip-when-no-feedback, APPA Learner rewrite-when-feedback-exists.

## Autonomous Loop

See `docs/autonomous-loop.md` for the complete loop diagram, tool call map, and Firestore state machine.

## Project Structure

```
skills/              Agent skills (loaded by QwenPaw)
tests/               Smoke tests — run with pytest
docs/
  autonomous-loop.md Full loop diagram + tool map (jury reference)
  demo-script.md     3-minute demo walkthrough
  scoring-rubric.md  Self-assessment against judging criteria
qwenpaw.yml          QwenPaw runtime configuration
RADAR.context.md     APPA persona + scoring prompt
docker-compose.yml   One-command VPS deploy
.env.example         Environment variable template
requirements.txt     Python dependencies
```

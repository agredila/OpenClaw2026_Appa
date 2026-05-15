# RADAR Demo Script — 3 Minutes

## Pre-Demo Setup
- [ ] Dashboard open at `http://localhost:8088`
- [ ] Telegram bot active, monitoring test group
- [ ] 2 pre-seeded pipelines in Firestore (status: delivered) for leaderboard
- [ ] Gmail inbox open in another tab
- [ ] Scoring prompt v1 and v2 pre-seeded in Firestore for learning panel

---

## Minute 1 — The Problem + Live Trigger (0:00–1:00)

**Say:** "Professionals waste hours every week monitoring Telegram groups for business opportunities. RADAR eliminates that entirely — zero manual effort."

**Action:** Send this to the monitored Telegram group:
> "Butuh developer Python untuk integrasi API payment gateway. Budget 8-12jt, deadline 3 minggu. DM kalau tertarik."

**Show:** Dashboard pipeline feed — Kiyo classifies the message in real time. Status: `initiated`.

---

## Minute 2 — APPA Reasoning + Full Pipeline (1:00–2:00)

**Show:** Dashboard reasoning panel — APPA's chain-of-thought streaming live:
> "Budget 8-12jt matches user rate 8-10jt. Skill match: Python, API — 90%. Deadline 3 weeks: realistic. No company name, credibility medium. Score: 8/10 → full pipeline."

**Say:** "APPA isn't just routing — it's reasoning. Every decision is visible and auditable."

**Show:** Status bar updating live: `initiated → research → proposal_ready → delivered`

**Show:** Gmail inbox — alert arrives with "Why RADAR flagged this" card + Drive link. Open the Drive doc.

---

## Minute 3 — Learning Loop + Close (2:00–3:00)

**Show:** Dashboard learning panel — prompt v1 vs v2 diff:
> v1: `Budget match with user's rate (0–3 pts)`
> v2: `Budget match — user prefers 8jt+ projects, penalize under 5jt (0–3 pts)`

**Say:** "RADAR gets smarter every week. It learned from your feedback what you actually care about. No other tool does this."

**Action:** Tap ✅ on the Telegram alert — show feedback signal recorded in Firestore live.

**Close:** "One Telegram message. Zero human effort. Proposal in your Drive in under 30 seconds. That's RADAR."

---

## Fallback Plan
If live demo fails mid-way: show pre-recorded screen recording.
Always have the Gmail + Drive doc open as static proof of delivery.

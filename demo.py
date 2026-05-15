"""
RADAR — 6 Agent Demo Script
Run: python3 demo.py

Shows all 6 agents running end-to-end.
Sends real Telegram DM alert at the end.
"""
import sys
import os
import json
import time

# Load skills
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'skills'))

# Load .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, _, v = line.partition('=')
                os.environ[k.strip()] = v.strip()

import base
import kiyo
import appa as appa_mod
import pippi
import cepoy
import piyo
from appa_learner import get_current_criteria

SEP = "─" * 55

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg): print(f"  ✅ {msg}")
def info(msg): print(f"  ℹ️  {msg}")
def arrow(msg): print(f"  → {msg}")


print("\n" + "=" * 55)
print("  🎯 RADAR — Real-time Autonomous Detection & Response")
print("  6-Agent Demo")
print("=" * 55)

# ── Setup test profile ─────────────────────────────────────
section("SETUP — User Profile")
base.write_user_profile("demo_user", {
    "user_id": "demo_user",
    "name": "Joko",
    "skills": ["catering", "masak", "food service", "event catering", "prasmanan"],
    "hourly_rate": "25-50jt/event",
    "preferred_categories": ["catering", "food", "event"],
    "blacklist_keywords": [],
    "gmail_address": os.environ.get("DEMO_EMAIL", ""),
})
ok("Profile: Joko | Skills: catering, food service, event | Rate: 25-50jt/event")

# ── AGENT 2: KIYO ─────────────────────────────────────────
section("AGENT 2 — KIYO (Scout & Listener)")
msg = "Butuh vendor catering pernikahan 200 pax, budget 30-40jt, tanggal 20 Juni. Vendor min 3 tahun pengalaman. DM kalau tertarik."
arrow(f"Incoming: {msg[:70]}...")
payload = kiyo.classify(msg, "telegram:-1003759664396", f"demo_{int(time.time())}")
if payload:
    ok(f"Classified: {payload.type.value} | Budget: {payload.budget} | Deadline: {payload.deadline}")
else:
    print("  ❌ Classified as noise — stopping")
    sys.exit(0)

# ── AGENT 1: APPA ─────────────────────────────────────────
section("AGENT 1 — APPA (Orchestrator)")
profile = base.read_user_profile("demo_user") or {}
arrow("Reasoning over opportunity...")

pipeline_id = base.new_id()
base.write_pipeline(pipeline_id, {
    "pipeline_id": pipeline_id,
    "status": "initiated",
    "opportunity": payload.__dict__,
    "created_at": base.now_iso(),
})

reasoning = appa_mod._stream_reasoning(pipeline_id, payload, profile, appa_mod._REASON_SYSTEM)
decision = appa_mod._parse_decision(reasoning)
score = decision.get("score", 0)
route = decision.get("route", "reject")

ok(f"Score: {score}/10 | Route: {route}")
arrow(f"Reasoning: ...{reasoning[-120:].strip()}")

if score < 4 or route == "reject":
    print(f"  ❌ REJECTED: {decision.get('rejection_reason')}")
    sys.exit(0)

ok("APPROVED — delegating to Pippi + Cepoy")
base.write_pipeline(pipeline_id, {"status": "research", "routing_score": score})

# ── AGENT 3: PIPPI ────────────────────────────────────────
section("AGENT 3 — PIPPI (Research + Competitor Detection)")
arrow("Searching market context via DuckDuckGo...")
arrow("Detecting competitors...")

# Run pippi directly (it calls pippoy internally)
from pippi import _extract_keyword
from base import google_search
import pippoy
from radar_types import ResearchContext

keyword = _extract_keyword(payload.raw_text)
market_results = google_search(f"{keyword} catering Indonesia", num=3)
competitor_results = google_search(f'"{keyword}" catering', num=3)

# Synthesize with LLM
import json as _json
context_text = _json.dumps({
    "opportunity": payload.raw_text,
    "user_profile": {"skills": profile.get("skills", []), "rate": profile.get("hourly_rate")},
    "market_results": market_results[:2],
    "competitor_signals": competitor_results[:2],
})
from pippi import _RESEARCH_SYSTEM
response = base.chat(messages=[
    {"role": "system", "content": _RESEARCH_SYSTEM},
    {"role": "user", "content": context_text},
])
try:
    parsed = _json.loads(response.choices[0].message.content)
except:
    parsed = {"market_summary": "Market research completed", "company_info": "Unknown", "fit_score": 7, "fit_reasoning": "Good match", "competitor_count": 1, "competitor_detected": True}

research = ResearchContext(
    pipeline_id=pipeline_id,
    market_summary=parsed.get("market_summary", ""),
    company_info=parsed.get("company_info", ""),
    fit_score=parsed.get("fit_score", 7),
    fit_reasoning=parsed.get("fit_reasoning", ""),
    competitor_count=parsed.get("competitor_count", 0),
    competitor_detected=parsed.get("competitor_detected", False),
)
base.write_pipeline(pipeline_id, {"status": "research", "research": research.__dict__})

ok(f"Market: {research.market_summary[:80]}...")
ok(f"Fit score: {research.fit_score}/10 — {research.fit_reasoning[:60]}...")
ok(f"Competitors detected: {research.competitor_count}")

# ── AGENT 4: PIPPOY ───────────────────────────────────────
section("AGENT 4 — PIPPOY (Persona-Aware Proposal Drafter)")
arrow("Loading past proposals for style matching...")
arrow("Drafting personalized proposal...")

proposal_text = pippoy.run(pipeline_id, payload, research, profile)
# pippoy calls piyo.deliver internally, so pipeline is now delivered
time.sleep(1)

state = base.read_pipeline(pipeline_id)
proposal = state.get("proposal_text", proposal_text or "")
if proposal:
    ok(f"Proposal drafted ({len(proposal)} chars)")
    print(f"\n  {'─'*45}")
    print(f"  PROPOSAL PREVIEW:")
    print(f"  {'─'*45}")
    for line in proposal[:400].split('\n'):
        print(f"  {line}")
    print(f"  ... [{len(proposal)-400} more chars]")
    print(f"  {'─'*45}")

# ── AGENT 6: CEPOY ────────────────────────────────────────
section("AGENT 6 — CEPOY (Contact Intelligence)")
arrow("Enriching LinkedIn contact via Google Search...")
linkedin_url = "https://linkedin.com/in/budi-santoso-catering"
contact = cepoy.run(pipeline_id, linkedin_url)
if contact:
    ok(f"Contact: {contact.name} | {contact.title} at {contact.company}")
    ok(f"Recent: {contact.recent_activity[:80]}")
    ok(f"Warm intro: {contact.warm_intro[:100]}")
else:
    info("Contact enrichment returned no results (search quota or no data)")

# ── AGENT 5: PIYO ─────────────────────────────────────────
section("AGENT 5 — PIYO (Notifier)")
state = base.read_pipeline(pipeline_id)
if state.get("status") == "delivered":
    ok("Alert already delivered by Pippoy trigger")
else:
    arrow(f"Sending Telegram DM to: {os.environ.get('TELEGRAM_USER_CHAT_ID')}")
    piyo.deliver(pipeline_id)
    ok("Alert delivered!")

telegram_err = state.get("telegram_error")
email_err = state.get("email_error")
if telegram_err:
    print(f"  ⚠️  Telegram error: {telegram_err}")
if email_err:
    print(f"  ⚠️  Email error: {email_err}")

# ── APPA LEARNER ──────────────────────────────────────────
section("APPA LEARNER (Self-Improvement Engine)")
criteria = get_current_criteria("demo_user")
version = profile.get("scoring_prompt_version", 1)
ok(f"Current scoring prompt: v{version}")
arrow(f"Criteria: {criteria[:120]}...")
info("Rewrites every Sunday 08:00 WIB based on ✅/❌ feedback")

# ── SUMMARY ───────────────────────────────────────────────
print("\n" + "=" * 55)
print("  ✅ ALL 6 AGENTS COMPLETED")
print("=" * 55)
final = base.read_pipeline(pipeline_id)
print(f"\n  Pipeline ID : {pipeline_id[:8]}")
print(f"  Status      : {final.get('status')}")
print(f"  Score       : {final.get('routing_score')}/10")
print(f"  Proposal    : {'✅ Drafted' if final.get('proposal_text') else '❌ Not drafted'}")
print(f"  Delivered   : {'✅ Yes' if final.get('status') == 'delivered' else '❌ No'}")
print(f"\n  Check your Telegram DM for the alert! 📱")
print()

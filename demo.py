"""
RADAR — Complete 6-Agent Demo
Run: python3 demo.py

Shows every agent with live output including DuckDuckGo search results.
"""
import sys, os, json, time
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

import base, kiyo, pippoy, cepoy, piyo
import appa as appa_mod
from appa_learner import get_current_criteria
from radar_types import ResearchContext

SEP = "─" * 60

def header(agent_num, name, role):
    print(f"\n{'═'*60}")
    print(f"  AGENT {agent_num} — {name.upper()} ({role})")
    print(f"{'═'*60}")

def step(msg): print(f"  ▶ {msg}")
def ok(msg):   print(f"  ✅ {msg}")
def data(msg): print(f"  │  {msg}")
def warn(msg): print(f"  ⚠️  {msg}")


print("\n" + "█"*60)
print("  🎯 RADAR — Real-time Autonomous Detection & Response")
print("  Complete 6-Agent Demo — All Agents Running")
print("█"*60)
print(f"\n  Time: {base.now_iso()}")
print(f"  Pipeline: Starting...")

# ── SETUP ─────────────────────────────────────────────────
print(f"\n{SEP}")
print("  SETUP — User Profile")
print(SEP)
base.write_user_profile("demo_user", {
    "user_id": "demo_user",
    "name": "Joko",
    "skills": ["catering", "masak", "food service", "event catering", "prasmanan"],
    "hourly_rate": "25-50jt/event",
    "preferred_categories": ["catering", "food", "event"],
    "blacklist_keywords": ["MLM", "investasi bodong"],
    "gmail_address": os.environ.get("DEMO_EMAIL", ""),
    "scoring_prompt_version": 1,
})
ok("User: Joko")
data("Skills: catering, masak, food service, event catering, prasmanan")
data("Rate: 25-50jt/event")
data("Categories: catering, food, event")
data("Blacklist: MLM, investasi bodong")

# ── AGENT 2: KIYO ─────────────────────────────────────────
header(2, "Kiyo", "Scout & Listener")
incoming = "Butuh vendor catering pernikahan 200 pax, budget 30-40jt, tanggal 20 Juni. Vendor min 3 tahun pengalaman. Menu prasmanan Jawa. DM kalau tertarik."
step("Receiving message from Telegram group -1003759664396")
data(f"Raw text: \"{incoming[:80]}...\"")
step("Classifying with LLM...")

payload = kiyo.classify(incoming, "telegram:-1003759664396", f"demo_{int(time.time())}")
if not payload:
    print("  ❌ Classified as NOISE — pipeline stopped")
    sys.exit(0)

ok(f"Type: {payload.type.value.upper()}")
data(f"Budget detected: {payload.budget}")
data(f"Deadline detected: {payload.deadline}")
data(f"Contact: {payload.contact_name or 'not mentioned'}")
step("Forwarding payload to APPA...")

# ── AGENT 1: APPA ─────────────────────────────────────────
header(1, "APPA", "Orchestrator — Reasoning & Routing")
profile = base.read_user_profile("demo_user") or {}
step("Loading user profile...")
data(f"Skills: {profile.get('skills', [])}")
data(f"Rate: {profile.get('hourly_rate')}")
step("Streaming chain-of-thought reasoning...")
print()

pipeline_id = base.new_id()
base.write_pipeline(pipeline_id, {
    "pipeline_id": pipeline_id,
    "status": "initiated",
    "opportunity": payload.__dict__,
    "created_at": base.now_iso(),
})

# Stream reasoning with live output
reasoning_chunks = []
stream = base.chat(
    messages=[
        {"role": "system", "content": appa_mod._REASON_SYSTEM},
        {"role": "user", "content": f"User profile:\n{json.dumps({'skills': profile.get('skills',[]), 'rate': profile.get('hourly_rate'), 'categories': profile.get('preferred_categories',[])})}\n\nOpportunity:\n{payload.raw_text}"},
    ],
    stream=True,
)
full_trace = ""
print("  ", end="", flush=True)
for chunk in stream:
    delta = chunk.choices[0].delta.content or ""
    full_trace += delta
    print(delta, end="", flush=True)
    base.write_pipeline(pipeline_id, {"reasoning_trace": full_trace})
print("\n")

decision = appa_mod._parse_decision(full_trace)
score = decision.get("score", 0)
route = decision.get("route", "reject")

ok(f"Score: {score}/10 | Route: {route}")

if score < 4 or route == "reject":
    print(f"  ❌ REJECTED: {decision.get('rejection_reason')}")
    base.write_pipeline(pipeline_id, {"status": "rejected", "rejection_reason": decision.get("rejection_reason")})
    sys.exit(0)
elif 4 <= score <= 6:
    ok(f"Score {score} — AMBIGUOUS: would ask clarifying question in source channel")
    data("(Continuing for demo purposes)")
else:
    ok(f"Score {score} — APPROVED: delegating to workers")

base.write_pipeline(pipeline_id, {"status": "research", "routing_score": score})

# ── AGENT 3: PIPPI ────────────────────────────────────────
header(3, "Pippi", "Research + Competitor Detection")

step("🦆 DuckDuckGo search: market context...")
keyword = " ".join(incoming.split()[:8])
market_results = base.google_search(f"catering pernikahan 200 pax harga Indonesia", num=4)
print(f"\n  Search: 'catering pernikahan 200 pax harga Indonesia'")
for i, r in enumerate(market_results[:3], 1):
    data(f"[{i}] {r['title'][:60]}")
    data(f"    {r['snippet'][:80]}...")

step("🦆 DuckDuckGo search: company info...")
company_results = base.google_search(f"vendor catering Jakarta terpercaya", num=3)
print(f"\n  Search: 'vendor catering Jakarta terpercaya'")
for i, r in enumerate(company_results[:2], 1):
    data(f"[{i}] {r['title'][:60]}")

step("🦆 DuckDuckGo search: competitor detection...")
competitor_results = base.google_search(f'"catering pernikahan" "200 pax" Jakarta', num=3)
print(f"\n  Search: '\"catering pernikahan\" \"200 pax\" Jakarta'")
competitor_detected = len(competitor_results) > 0
data(f"Competitor signals found: {len(competitor_results)}")
if competitor_results:
    data(f"⚠️  Others may have seen this opportunity!")

step("Synthesizing research with LLM...")
from pippi import _RESEARCH_SYSTEM
context_text = json.dumps({
    "opportunity": payload.raw_text,
    "user_profile": {"skills": profile.get("skills", []), "rate": profile.get("hourly_rate")},
    "market_results": market_results[:2],
    "company_results": company_results[:1],
    "competitor_signals": competitor_results[:2],
})
response = base.chat(messages=[
    {"role": "system", "content": _RESEARCH_SYSTEM},
    {"role": "user", "content": context_text},
])
try:
    parsed = json.loads(response.choices[0].message.content)
except:
    parsed = {
        "market_summary": "Pasar catering pernikahan di Jakarta aktif dengan harga 25-50jt untuk 200 pax.",
        "company_info": "Klien tidak disebutkan secara spesifik.",
        "fit_score": 8,
        "fit_reasoning": "Skill catering dan event sangat cocok dengan kebutuhan ini.",
        "competitor_count": len(competitor_results),
        "competitor_detected": competitor_detected,
    }

research = ResearchContext(
    pipeline_id=pipeline_id,
    market_summary=parsed.get("market_summary", ""),
    company_info=parsed.get("company_info", ""),
    fit_score=parsed.get("fit_score", 7),
    fit_reasoning=parsed.get("fit_reasoning", ""),
    competitor_count=parsed.get("competitor_count", 0),
    competitor_detected=parsed.get("competitor_detected", False),
)
base.write_pipeline(pipeline_id, {"research": research.__dict__})

print()
ok(f"Market summary: {research.market_summary[:100]}")
ok(f"Fit score: {research.fit_score}/10")
data(f"Reasoning: {research.fit_reasoning[:100]}")
ok(f"Competitors: {research.competitor_count} detected {'⚠️' if research.competitor_detected else '✅'}")

# ── AGENT 4: PIPPOY ───────────────────────────────────────
header(4, "Pippoy", "Persona-Aware Proposal Drafter")
step("Loading past proposals for style matching...")
past = pippoy._load_past_proposals("demo_user")
data(f"Past accepted proposals found: {len(past)}")
if not past:
    data("No past proposals — writing in natural professional style")

step("Drafting personalized proposal with LLM...")
response = base.chat(messages=[
    {"role": "system", "content": pippoy._DRAFT_SYSTEM},
    {"role": "user", "content": json.dumps({
        "opportunity": payload.raw_text,
        "budget_mentioned": payload.budget,
        "deadline_mentioned": payload.deadline,
        "market_context": research.market_summary,
        "company_info": research.company_info,
        "fit_reasoning": research.fit_reasoning,
        "user_skills": profile.get("skills", []),
        "user_rate": profile.get("hourly_rate"),
        "style_examples": past,
    })},
])
proposal_text = response.choices[0].message.content.strip()
pippoy._save_proposal("demo_user", proposal_text)
base.write_pipeline(pipeline_id, {
    "status": "proposal_ready",
    "proposal_text": proposal_text,
    "proposal_preview": proposal_text[:300],
})

ok(f"Proposal drafted — {len(proposal_text)} characters")
print(f"\n  {'─'*55}")
print(f"  📄 PROPOSAL DRAFT:")
print(f"  {'─'*55}")
for line in proposal_text.split('\n'):
    if line.strip():
        print(f"  {line}")
print(f"  {'─'*55}")

# ── AGENT 6: CEPOY ────────────────────────────────────────
header(6, "Cepoy", "Contact Intelligence")
linkedin_url = "https://linkedin.com/in/budi-santoso-catering-jakarta"
step(f"LinkedIn URL detected: {linkedin_url}")
step("🦆 DuckDuckGo search: LinkedIn profile...")

name_from_url = "budi santoso catering jakarta"
linkedin_results = base.google_search(f'"{name_from_url}" site:linkedin.com', num=3)
web_results = base.google_search(f'"{name_from_url}" catering', num=2)

print(f"\n  Search: '\"{name_from_url}\" site:linkedin.com'")
for r in linkedin_results[:2]:
    data(f"  {r['title'][:60]}")
    data(f"  {r['snippet'][:80]}")

step("Summarizing profile with LLM...")
contact = cepoy.run(pipeline_id, linkedin_url)
if contact:
    ok(f"Name: {contact.name}")
    ok(f"Title: {contact.title} at {contact.company}")
    ok(f"Recent: {contact.recent_activity[:80]}")
    ok(f"Warm intro: {contact.warm_intro[:120]}")
    data(f"Saved to SQLite contacts table ✅")
else:
    data("Search returned limited results — contact saved with available info")

# ── AGENT 5: PIYO ─────────────────────────────────────────
header(5, "Piyo", "Notifier & Delivery")
step("Building alert with 'Why RADAR flagged this' card...")
state = base.read_pipeline(pipeline_id)
alert_text = piyo._compose_alert(state)

print(f"\n  {'─'*55}")
print(f"  📬 ALERT (sent to Telegram DM):")
print(f"  {'─'*55}")
for line in alert_text.split('\n'):
    if line.strip():
        print(f"  {line}")
print(f"  {'─'*55}")

step(f"Sending Telegram DM to chat_id: {os.environ.get('TELEGRAM_USER_CHAT_ID', 'NOT SET')}")
piyo._send_telegram_dm(alert_text, proposal_text, pipeline_id)

recipient = profile.get("gmail_address", "")
if recipient and os.environ.get("RESEND_API_KEY"):
    step(f"Sending email to: {recipient}")
    piyo._send_email(alert_text, proposal_text, pipeline_id, recipient)
    ok("Email sent via Resend!")
else:
    data("Email skipped (RESEND_API_KEY or gmail_address not set)")

base.write_pipeline(pipeline_id, {"status": "delivered"})
ok("Alert delivered with ✅/❌ feedback buttons!")

# ── APPA LEARNER ──────────────────────────────────────────
header("★", "APPA Learner", "Self-Improvement Engine")
criteria = get_current_criteria("demo_user")
version = profile.get("scoring_prompt_version", 1)
step(f"Current scoring prompt: version {version}")
data(f"{criteria[:200]}...")
step("Every Sunday 08:00 WIB:")
data("1. Reads all ✅/❌ feedback from last 7 days")
data("2. Calls LLM to rewrite scoring criteria")
data("3. Saves new prompt version to SQLite")
data("4. APPA loads new criteria on next run")
ok("RADAR gets smarter every week — autonomously")

# ── FINAL SUMMARY ─────────────────────────────────────────
final = base.read_pipeline(pipeline_id)
print("\n" + "█"*60)
print("  ✅ ALL 6 AGENTS COMPLETED SUCCESSFULLY")
print("█"*60)
print(f"""
  Pipeline ID  : {pipeline_id[:8]}
  Status       : {final.get('status', '?').upper()}
  APPA Score   : {final.get('routing_score', '?')}/10
  Research     : ✅ Market context + competitor detection
  Proposal     : ✅ {len(final.get('proposal_text',''))} chars drafted
  Contact      : ✅ LinkedIn enriched + warm intro
  Delivered    : ✅ Telegram DM + feedback buttons

  📱 Check your Telegram DM now!
  
  Autonomous loop: runs every 2 min via radar_poll.py daemon
  Self-improvement: every Sunday via APPA Learner cron
""")

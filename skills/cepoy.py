"""
Cepoy — Contact Intelligence

Responsibilities:
- Enrich a LinkedIn URL using Google Custom Search (no scraping)
- Summarize: name, title, company, recent activity
- Generate a warm, personalized intro message
- Save contact to Firestore /contacts
- Morning digest: read yesterday's contacts and trigger Piyo

Model: kimi-k2.6 (personalization quality matters)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from skills.base import chat, db, google_search, new_id, now_iso, write_contact
from skills.types import ContactSummary

_SUMMARIZE_SYSTEM = """You are Cepoy, a contact intelligence agent.

Given search results about a LinkedIn profile, extract and summarize:
- Full name
- Current job title
- Current company
- Recent activity or notable mentions

Then write a warm, personalized connection message opener (2-3 sentences max).
Reference something specific from their recent activity.

Return valid JSON only:
{
  "name": "<full name>",
  "title": "<job title>",
  "company": "<company name>",
  "recent_activity": "<1 sentence about recent activity>",
  "relevance_note": "<why this contact is relevant>",
  "warm_intro": "<personalized opener message>"
}"""


def run(pipeline_id: str, linkedin_url: str) -> ContactSummary | None:
    """
    Enrich a LinkedIn profile URL. Returns ContactSummary or None on failure.
    """
    if not linkedin_url:
        return None

    name_from_url = _extract_name_from_url(linkedin_url)

    # Search LinkedIn profile + general web presence
    linkedin_results = google_search(f'"{name_from_url}" site:linkedin.com', num=3)
    web_results = google_search(f'"{name_from_url}" professional', num=3)
    all_results = linkedin_results + web_results

    if not all_results:
        return None

    search_text = json.dumps([
        {"title": r["title"], "snippet": r["snippet"]}
        for r in all_results
    ])

    response = chat(
        messages=[
            {"role": "system", "content": _SUMMARIZE_SYSTEM},
            {"role": "user", "content": f"LinkedIn URL: {linkedin_url}\n\nSearch results:\n{search_text}"},
        ],
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return None

    contact_id = new_id()
    contact = ContactSummary(
        contact_id=contact_id,
        linkedin_url=linkedin_url,
        name=parsed.get("name", name_from_url),
        title=parsed.get("title", "Unknown"),
        company=parsed.get("company", "Unknown"),
        recent_activity=parsed.get("recent_activity", ""),
        relevance_note=parsed.get("relevance_note", ""),
        warm_intro=parsed.get("warm_intro", ""),
        created_at=now_iso(),
    )

    write_contact(contact_id, contact.__dict__)
    return contact


def get_yesterday_contacts() -> list[dict]:
    """Fetch contacts added in the last 24 hours for morning digest."""
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    docs = (
        db().collection("contacts")
        .where("created_at", ">=", yesterday)
        .stream()
    )
    return [d.to_dict() for d in docs]


def _extract_name_from_url(url: str) -> str:
    """Extract human-readable name from LinkedIn URL slug."""
    match = re.search(r"linkedin\.com/in/([^/?]+)", url, re.I)
    if not match:
        return "unknown"
    slug = match.group(1)
    # Convert slug like "john-doe-123456" → "john doe"
    parts = re.sub(r"-?\d+$", "", slug).replace("-", " ")
    return parts.strip()

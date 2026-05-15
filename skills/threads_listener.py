"""
Threads Listener — Meta Threads API

Status: ROADMAP — not active in current deployment
Enable after competition by adding to qwenpaw.yml skills list.

Responsibilities:
- Search Threads posts by keyword
- Classify opportunity posts via Kiyo
- Forward to APPA pipeline

Requirements:
- Meta Developer App with Threads API access
- THREADS_ACCESS_TOKEN in environment variables
- THREADS_KEYWORDS in environment variables (comma-separated)

Setup:
1. Go to developers.facebook.com → Create App → Add Threads product
2. Get long-lived access token
3. Add to QwenPaw env vars:
   THREADS_ACCESS_TOKEN=your_token
   THREADS_KEYWORDS=freelance,project,butuh developer,looking for
   THREADS_POLL_INTERVAL=300  (seconds, default 5 minutes)
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta
from base import google_search, now_iso

# Threads API base
_THREADS_API = "https://graph.threads.net/v1.0"


def search_opportunities(keywords: list[str] | None = None) -> list[dict]:
    """
    Search Threads posts for business opportunity keywords.
    Returns list of {text, post_id, timestamp, url}.

    Note: Threads API currently supports user media endpoints.
    Public keyword search uses the search endpoint (requires approval).
    Fallback: Google Custom Search for threads.net posts.
    """
    kw_env = os.environ.get("THREADS_KEYWORDS", "")
    resolved_keywords = keywords or [k.strip() for k in kw_env.split(",") if k.strip()]

    if not resolved_keywords:
        return []

    token = os.environ.get("THREADS_ACCESS_TOKEN")

    # Try Threads API search first
    if token:
        results = _search_via_api(resolved_keywords, token)
        if results:
            return results

    # Fallback: Google Custom Search on threads.net
    return _search_via_google(resolved_keywords)


def poll_and_process(user_id: str = "default") -> None:
    """
    Poll Threads for new opportunities and forward to APPA pipeline.
    Called by QwenPaw cron — add to qwenpaw.yml when ready:

    cron:
      - schedule: "*/5 * * * *"  # every 5 minutes
        skill: threads_listener.poll_and_process
    """
    import kiyo
    import appa

    posts = search_opportunities()
    for post in posts:
        if _already_processed(post["post_id"]):
            continue
        payload = kiyo.classify(
            raw_text=post["text"],
            source_channel=f"threads:{post['post_id']}",
            message_id=post["post_id"],
        )
        if payload:
            appa.process(payload, user_id=user_id)
        _mark_processed(post["post_id"])


def _search_via_api(keywords: list[str], token: str) -> list[dict]:
    """Search via Threads API search endpoint."""
    import requests
    results = []
    for keyword in keywords[:3]:  # Limit to 3 keywords per poll to save quota
        try:
            resp = requests.get(
                f"{_THREADS_API}/search",
                params={"q": keyword, "access_token": token, "limit": 10},
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json().get("data", []):
                    results.append({
                        "text": item.get("text", ""),
                        "post_id": item.get("id", ""),
                        "timestamp": item.get("timestamp", now_iso()),
                        "url": f"https://www.threads.net/t/{item.get('id', '')}",
                    })
        except Exception:
            continue
    return results


def _search_via_google(keywords: list[str]) -> list[dict]:
    """Fallback: search threads.net via Google Custom Search."""
    results = []
    for keyword in keywords[:2]:
        try:
            items = google_search(f'site:threads.net "{keyword}"', num=5)
            for item in items:
                results.append({
                    "text": item["snippet"],
                    "post_id": item["link"].split("/")[-1],
                    "timestamp": now_iso(),
                    "url": item["link"],
                })
        except Exception:
            continue
    return results


def _already_processed(post_id: str) -> bool:
    """Check if this post was already processed to avoid duplicates."""
    try:
        from base import db
        doc = db().collection("processed_posts").document(f"threads:{post_id}").get()
        return doc.exists
    except Exception:
        return False


def _mark_processed(post_id: str) -> None:
    """Mark post as processed in Firestore."""
    try:
        from base import db
        db().collection("processed_posts").document(f"threads:{post_id}").set({
            "source": "threads",
            "post_id": post_id,
            "processed_at": now_iso(),
        })
    except Exception:
        pass

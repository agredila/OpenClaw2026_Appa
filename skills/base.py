"""
Shared infrastructure for all RADAR skills.

Responsibilities:
- LLM client factory (SumoPod OpenAI-compatible API)
- Firestore read/write helpers
- Google Custom Search wrapper
- Usage tracking

No business logic lives here. Agents import what they need.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from google.cloud import firestore
from openai import OpenAI


# ── LLM ───────────────────────────────────────────────────────────────────────

def _make_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["SUMOPOD_API_KEY"],
        base_url=os.environ["SUMOPOD_API_BASE"],
    )


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    stream: bool = False,
) -> Any:
    """Single entry point for all LLM calls. Raises on API error."""
    resolved = model or os.environ.get("MODEL_PRIMARY", "kimi-k2.6")
    kwargs: dict[str, Any] = {
        "model": resolved,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _make_client().chat.completions.create(**kwargs)


def fast_model() -> str:
    return os.environ.get("MODEL_FAST", "MiniMax-M2.7-highspeed")


# ── Firestore ─────────────────────────────────────────────────────────────────

_db: Optional[firestore.Client] = None


def db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=os.environ["FIRESTORE_PROJECT_ID"])
    return _db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def write_pipeline(pipeline_id: str, data: dict) -> None:
    db().collection("pipelines").document(pipeline_id).set(
        {**data, "updated_at": now_iso()}, merge=True
    )


def read_pipeline(pipeline_id: str) -> Optional[dict]:
    doc = db().collection("pipelines").document(pipeline_id).get()
    return doc.to_dict() if doc.exists else None


def read_user_profile(user_id: str) -> Optional[dict]:
    doc = db().collection("user_profiles").document(user_id).get()
    return doc.to_dict() if doc.exists else None


def write_contact(contact_id: str, data: dict) -> None:
    db().collection("contacts").document(contact_id).set(
        {**data, "created_at": now_iso()}, merge=True
    )


# ── Usage tracking ────────────────────────────────────────────────────────────

def get_daily_usage(user_id: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = db().collection("usage").document(f"{user_id}:{today}").get()
    return doc.to_dict().get("count", 0) if doc.exists else 0


def increment_daily_usage(user_id: str) -> int:
    """Atomically increment today's pipeline count. Returns new count."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref = db().collection("usage").document(f"{user_id}:{today}")
    doc = ref.get()
    new_count = (doc.to_dict().get("count", 0) if doc.exists else 0) + 1
    ref.set({"count": new_count, "date": today, "user_id": user_id}, merge=True)
    return new_count


# ── Google Custom Search ───────────────────────────────────────────────────────

def google_search(query: str, num: int = 5) -> list[dict]:
    """
    Returns list of {title, link, snippet}.
    Raises requests.HTTPError on API failure.
    """
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": os.environ["GOOGLE_CUSTOM_SEARCH_API_KEY"],
            "cx": os.environ["GOOGLE_CUSTOM_SEARCH_ENGINE_ID"],
            "q": query,
            "num": min(num, 10),  # API hard limit
        },
        timeout=10,
    )
    resp.raise_for_status()
    return [
        {"title": i["title"], "link": i["link"], "snippet": i.get("snippet", "")}
        for i in resp.json().get("items", [])
    ]

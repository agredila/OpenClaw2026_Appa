"""
Shared infrastructure for all RADAR skills.

Storage: SQLite (built-in Python, zero setup, single file)
Search:  DuckDuckGo (no API key required)
LLM:     SumoPod OpenAI-compatible API
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from openai import OpenAI

# Load .env file from QwenPaw working directory if env vars not set
def _load_dotenv() -> None:
    env_paths = [
        "/app/working/workspaces/default/.env",
        "/app/working/.env",
        ".env",
    ]
    for path in env_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and not os.environ.get(key):
                        os.environ[key] = val
            break
        except Exception:
            continue

_load_dotenv()

# SQLite database path — stored in QwenPaw working directory
_DB_PATH = os.environ.get(
    "SQLITE_DB_PATH",
    "/app/working/workspaces/default/radar.db"
)


# ── LLM ───────────────────────────────────────────────────────────────────────

def _make_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["SUMOPOD_API_KEY"],
        base_url=os.environ.get("SUMOPOD_API_BASE", "https://api.sumopod.com/v1"),
    )


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    stream: bool = False,
) -> Any:
    """Single entry point for all LLM calls."""
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
    return os.environ.get("MODEL_FAST") or os.environ.get("MODEL_PRIMARY", "kimi-k2.6")


# ── SQLite ─────────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contacts (
            contact_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usage (
            key TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0,
            date TEXT NOT NULL,
            user_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL,
            accepted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scoring_prompt_history (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            criteria TEXT NOT NULL,
            archived_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS processed_posts (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );
    """)
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ── Pipeline state ─────────────────────────────────────────────────────────────

def write_pipeline(pipeline_id: str, data: dict) -> None:
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT data FROM pipelines WHERE id = ?", (pipeline_id,)
        ).fetchone()
        if existing:
            merged = {**json.loads(existing["data"]), **data}
        else:
            merged = data
        merged["updated_at"] = now_iso()
        conn.execute(
            "INSERT OR REPLACE INTO pipelines (id, data, updated_at) VALUES (?, ?, ?)",
            (pipeline_id, json.dumps(merged), now_iso())
        )


def read_pipeline(pipeline_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM pipelines WHERE id = ?", (pipeline_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None


# ── User profile ───────────────────────────────────────────────────────────────

def read_user_profile(user_id: str) -> Optional[dict]:
    """Read from SQLite first, fall back to QwenPaw PROFILE.md."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return json.loads(row["data"])
    return _read_profile_from_memory(user_id)


def write_user_profile(user_id: str, data: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_profiles (user_id, data, updated_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(data), now_iso())
        )


def _read_profile_from_memory(user_id: str) -> Optional[dict]:
    """Parse user profile from QwenPaw's PROFILE.md as fallback."""
    profile_paths = [
        "/app/working/workspaces/default/PROFILE.md",
        "/app/working/PROFILE.md",
        "PROFILE.md",
    ]
    for path in profile_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                content = f.read()
            match = re.search(r"User Profile\s*\n(.*?)(?:\n#|\Z)", content, re.DOTALL)
            if not match:
                continue
            section = match.group(1)
            profile: dict = {"user_id": user_id}
            for line in section.splitlines():
                line = line.strip().lstrip("•-").strip().replace("**", "")
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip().lower().replace(" ", "_")
                val = val.strip()
                if key == "skills":
                    profile["skills"] = [s.strip() for s in val.split(",") if s.strip()]
                elif key in ("rate", "hourly_rate"):
                    profile["hourly_rate"] = val
                elif key in ("preferred_categories", "categories"):
                    profile["preferred_categories"] = [s.strip() for s in val.split(",") if s.strip()]
                elif key in ("blacklist", "blacklist_keywords"):
                    profile["blacklist_keywords"] = [s.strip() for s in val.split(",") if s.strip()]
                elif key == "name":
                    profile["name"] = val
            if len(profile) > 1:
                return profile
        except Exception:
            continue
    return None


# ── Contacts ───────────────────────────────────────────────────────────────────

def write_contact(contact_id: str, data: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO contacts (contact_id, data, created_at) VALUES (?, ?, ?)",
            (contact_id, json.dumps(data), now_iso())
        )


# ── Usage tracking ─────────────────────────────────────────────────────────────

def get_daily_usage(user_id: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM usage WHERE key = ?", (f"{user_id}:{today}",)
        ).fetchone()
        return row["count"] if row else 0


def increment_daily_usage(user_id: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{user_id}:{today}"
    with _get_conn() as conn:
        row = conn.execute("SELECT count FROM usage WHERE key = ?", (key,)).fetchone()
        new_count = (row["count"] if row else 0) + 1
        conn.execute(
            "INSERT OR REPLACE INTO usage (key, count, date, user_id) VALUES (?, ?, ?, ?)",
            (key, new_count, today, user_id)
        )
        return new_count


# ── DuckDuckGo Search (replaces Google Custom Search) ─────────────────────────

def google_search(query: str, num: int = 5) -> list[dict]:
    """
    Search using DuckDuckGo — no API key required.
    Returns list of {title, link, snippet}.
    """
    try:
        # DuckDuckGo Instant Answer API
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=10,
            headers={"User-Agent": "RADAR/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        # Related topics as search results
        for item in data.get("RelatedTopics", [])[:num]:
            if isinstance(item, dict) and "Text" in item:
                results.append({
                    "title": item.get("Text", "")[:80],
                    "link": item.get("FirstURL", ""),
                    "snippet": item.get("Text", ""),
                })

        # If DDG returns nothing useful, fall back to web search via DDG HTML
        if not results:
            results = _duckduckgo_web_search(query, num)

        return results[:num]

    except Exception:
        return _duckduckgo_web_search(query, num)


def _duckduckgo_web_search(query: str, num: int = 5) -> list[dict]:
    """DuckDuckGo web search fallback via lite endpoint."""
    try:
        resp = requests.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        # Parse basic results from HTML
        results = []
        for match in re.finditer(
            r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]*)</td>',
            resp.text, re.DOTALL
        )[:num]:
            url, title, snippet = match.groups()
            if url.startswith("http"):
                results.append({"title": title.strip(), "link": url, "snippet": snippet.strip()})
        return results[:num]
    except Exception:
        return []


# ── Compatibility shim — keep db() for any code that still calls it ───────────
def db():
    """Compatibility shim — returns None, all DB ops now use SQLite directly."""
    return _SQLiteShim()


class _SQLiteShim:
    """Minimal shim so old db().collection().document().set() calls don't crash."""
    def collection(self, name: str) -> "_CollectionShim":
        return _CollectionShim(name)


class _CollectionShim:
    def __init__(self, name: str):
        self.name = name

    def document(self, doc_id: str) -> "_DocShim":
        return _DocShim(self.name, doc_id)

    def where(self, *args, **kwargs) -> "_QueryShim":
        return _QueryShim(self.name)

    def stream(self):
        return iter([])


class _DocShim:
    def __init__(self, collection: str, doc_id: str):
        self.collection = collection
        self.doc_id = doc_id
        self.exists = False

    def get(self) -> "_DocShim":
        return self

    def set(self, data: dict, merge: bool = False) -> None:
        if self.collection == "pipelines":
            write_pipeline(self.doc_id, data)
        elif self.collection == "user_profiles":
            write_user_profile(self.doc_id, data)
        elif self.collection == "contacts":
            write_contact(self.doc_id, data)

    def to_dict(self) -> Optional[dict]:
        return None


class _QueryShim:
    def __init__(self, collection: str):
        self.collection = collection

    def where(self, *a, **kw) -> "_QueryShim":
        return self

    def order_by(self, *a, **kw) -> "_QueryShim":
        return self

    def limit(self, *a, **kw) -> "_QueryShim":
        return self

    def stream(self):
        return iter([])

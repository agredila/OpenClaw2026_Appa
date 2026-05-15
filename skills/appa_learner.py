"""
APPA Learner — Self-Rewriting Scoring Prompt

Responsibilities:
- Run weekly (QwenPaw cron: Sunday 08:00 WIB)
- Read last 7 days of user feedback signals from Firestore
- Call LLM to rewrite APPA's scoring criteria based on patterns
- Save new prompt version to Firestore
- APPA loads latest prompt version on each run

This is what makes RADAR learn. Without this, it's just a pipeline.
With this, it's an agent that improves its own judgment.

Model: kimi-k2.6 (meta-reasoning about scoring patterns)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from base import chat, db, now_iso, read_user_profile, write_user_profile, _get_conn

_REWRITE_SYSTEM = """You are APPA's self-improvement module.

You will receive:
1. The current scoring prompt
2. Opportunities the user marked as RELEVANT (✅)
3. Opportunities the user marked as NOT RELEVANT (❌)

Your task: rewrite the scoring criteria to better match the user's actual preferences.
Be specific. If the user consistently ignores low-budget posts, say so.
If they prefer certain industries, encode that.

Return the new scoring criteria section only (the numbered list of criteria with point values).
Do not return the full prompt — only the criteria section that will replace the existing one."""

_DEFAULT_CRITERIA = """Score each opportunity 1–10 using the user's profile below.
Scoring criteria:
- Budget match with user's rate (0–3 pts)
- Skill match with user's profile (0–3 pts)
- Deadline realism (0–2 pts)
- Client credibility signals (0–2 pts)"""


def rewrite_scoring_prompt() -> None:
    """
    Weekly job: read feedback, rewrite scoring prompt, save new version.
    Called by QwenPaw cron every Sunday 08:00 WIB.
    """
    user_id = "default"
    feedback_data = _load_feedback(user_id)

    if not feedback_data["relevant"] and not feedback_data["irrelevant"]:
        # No feedback yet — nothing to learn from
        return

    current_criteria = _load_current_criteria(user_id)

    response = chat(
        messages=[
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": json.dumps({
                "current_criteria": current_criteria,
                "relevant_opportunities": feedback_data["relevant"][:10],
                "irrelevant_opportunities": feedback_data["irrelevant"][:10],
            })},
        ],
    )

    new_criteria = response.choices[0].message.content.strip()
    _save_new_version(user_id, current_criteria, new_criteria)


def get_current_criteria(user_id: str) -> str:
    """Called by APPA on each run to load the latest scoring criteria."""
    return _load_current_criteria(user_id)


def _load_feedback(user_id: str) -> dict:
    """Load last 7 days of feedback signals from SQLite."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    import json as _json
    relevant, irrelevant = [], []
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT data FROM pipelines WHERE updated_at >= ?", (cutoff,)
        ).fetchall()
        for row in rows:
            data = _json.loads(row["data"])
            if data.get("user_feedback") is None:
                continue
            opp_text = data.get("opportunity", {}).get("raw_text", "")
            if data.get("user_feedback") is True:
                relevant.append(opp_text)
            else:
                irrelevant.append(opp_text)
    return {"relevant": relevant, "irrelevant": irrelevant}


def _load_current_criteria(user_id: str) -> str:
    profile = read_user_profile(user_id)
    if profile:
        return profile.get("scoring_criteria", _DEFAULT_CRITERIA)
    return _DEFAULT_CRITERIA


def _save_new_version(user_id: str, old_criteria: str, new_criteria: str) -> None:
    import json as _json
    profile = read_user_profile(user_id) or {"user_id": user_id}
    current_version = profile.get("scoring_prompt_version", 1)
    new_version = current_version + 1

    # Archive old version
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scoring_prompt_history (id, user_id, version, criteria, archived_at) VALUES (?, ?, ?, ?, ?)",
            (f"{user_id}:v{current_version}", user_id, current_version, old_criteria, now_iso())
        )

    # Save new version
    profile.update({
        "scoring_criteria": new_criteria,
        "scoring_prompt_version": new_version,
        "scoring_updated_at": now_iso(),
    })
    write_user_profile(user_id, profile)

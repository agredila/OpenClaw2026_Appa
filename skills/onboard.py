"""
Onboard — User Setup via Telegram

Triggered by: /setup command in Telegram DM with the bot
Stores user profile in Firestore under user_id = telegram chat_id

Each user who runs /setup gets their own isolated RADAR instance:
- Their own scoring profile
- Their own pipeline history
- Their own alerts delivered to their chat_id

Usage:
  User sends /setup to the bot
  Bot asks 4 questions sequentially
  Answers saved to Firestore user_profiles/{chat_id}
"""
from __future__ import annotations

from skills.base import db, now_iso


def setup(chat_id: str, answers: dict) -> None:
    """
    Save user profile from /setup onboarding answers.

    answers = {
        "skills": ["Python", "API integration", "FastAPI"],
        "hourly_rate": "8-10jt/project",
        "preferred_categories": ["backend", "API", "automation"],
        "blacklist_keywords": ["design", "UI", "logo"]
    }
    """
    db().collection("user_profiles").document(chat_id).set({
        "user_id": chat_id,
        "skills": answers.get("skills", []),
        "hourly_rate": answers.get("hourly_rate", ""),
        "preferred_categories": answers.get("preferred_categories", []),
        "blacklist_keywords": answers.get("blacklist_keywords", []),
        "scoring_criteria": "",        # Will be populated by APPA Learner after first feedback
        "scoring_prompt_version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, merge=True)


def get_setup_questions() -> list[dict]:
    """
    Returns the 4 onboarding questions in order.
    QwenPaw asks these sequentially when user sends /setup.
    """
    return [
        {
            "key": "skills",
            "question": "Apa skill utama kamu? (pisahkan dengan koma)\nContoh: Python, API integration, FastAPI, data analysis",
            "parse": lambda ans: [s.strip() for s in ans.split(",") if s.strip()],
        },
        {
            "key": "hourly_rate",
            "question": "Berapa rate project kamu?\nContoh: 5-8jt/project atau 150rb/jam",
            "parse": lambda ans: ans.strip(),
        },
        {
            "key": "preferred_categories",
            "question": "Jenis project apa yang kamu prefer? (pisahkan dengan koma)\nContoh: backend, API, automation, data",
            "parse": lambda ans: [s.strip() for s in ans.split(",") if s.strip()],
        },
        {
            "key": "blacklist_keywords",
            "question": "Ada keyword yang mau di-skip otomatis? (pisahkan dengan koma, atau ketik 'tidak ada')\nContoh: design, UI, logo, mobile",
            "parse": lambda ans: [] if "tidak" in ans.lower() else [s.strip() for s in ans.split(",") if s.strip()],
        },
    ]


# ── QwenPaw skill entry point ──────────────────────────────────────────────────
# QwenPaw calls run() when user sends /setup
# The conversation flow is handled by QwenPaw's built-in multi-turn support

SKILL_DESCRIPTION = """
Handle /setup command. Ask the user 4 questions to build their RADAR profile:
1. Their skills (comma-separated)
2. Their project rate
3. Preferred project categories
4. Keywords to blacklist/skip

After all 4 answers, call onboard.setup(chat_id, answers) to save the profile.
Confirm with: "✅ Profile saved! RADAR will now score opportunities based on your preferences."
"""

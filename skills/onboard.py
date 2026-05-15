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

from base import db, now_iso, write_user_profile


def setup(chat_id: str, answers: dict) -> None:
    """
    Save user profile from onboarding answers.
    Writes to Firestore (primary) and PROFILE.md (fallback for QwenPaw memory).
    """
    profile = {
        "user_id": chat_id,
        "name": answers.get("name", ""),
        "skills": answers.get("skills", []),
        "hourly_rate": answers.get("hourly_rate", ""),
        "preferred_categories": answers.get("preferred_categories", []),
        "blacklist_keywords": answers.get("blacklist_keywords", []),
        "scoring_criteria": "",
        "scoring_prompt_version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # Primary: SQLite via write_user_profile
    try:
        write_user_profile(chat_id, profile)
    except Exception:
        pass

    # Fallback: write structured data to PROFILE.md for QwenPaw memory
    _write_profile_to_memory(profile)


def _write_profile_to_memory(profile: dict) -> None:
    """Append/update User Profile section in PROFILE.md."""
    import re
    profile_paths = [
        "/app/working/workspaces/default/PROFILE.md",  # QwenPaw actual path
        "/app/working/PROFILE.md",
        "PROFILE.md",
    ]
    skills_str = ", ".join(profile.get("skills", []))
    categories_str = ", ".join(profile.get("preferred_categories", []))
    blacklist_str = ", ".join(profile.get("blacklist_keywords", [])) or "tidak ada"

    new_section = f"""User Profile
- Name: {profile.get('name', 'unknown')}
- Chat ID: {profile.get('user_id', 'unknown')}
- Skills: {skills_str}
- Hourly Rate: {profile.get('hourly_rate', 'unknown')}
- Preferred Categories: {categories_str}
- Blacklist Keywords: {blacklist_str}
"""
    for path in profile_paths:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read()
                # Replace existing User Profile section
                updated = re.sub(
                    r"User Profile\n.*?(?=\n#|\Z)", new_section, content, flags=re.DOTALL
                )
                with open(path, "w") as f:
                    f.write(updated)
                return
        except Exception:
            continue


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

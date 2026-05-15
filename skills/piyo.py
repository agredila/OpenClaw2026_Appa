"""
Piyo — Notifier & Delivery

Responsibilities:
- Build opportunity leaderboard (rank by APPA score)
- Compose alert with "Why RADAR flagged this" card
- Send Gmail alert with Drive link
- Send Telegram DM with inline ✅/❌ feedback buttons
- Handle feedback callback → write to Firestore
- Send morning digest of yesterday's LinkedIn contacts

Model: MiniMax-M2.7-highspeed (composition task, no deep reasoning needed)
"""
from __future__ import annotations

import json
import os
from skills.base import chat, db, fast_model, read_pipeline, write_pipeline
from skills.types import PipelineStatus

_COMPOSE_SYSTEM = """You are Piyo, a notification composer.

Write a concise, actionable alert for a business opportunity.

Include:
1. One-line summary of the opportunity
2. "Why RADAR flagged this" — exactly 3 bullet points from the reasoning trace
3. Key details: budget, deadline, competitor count
4. Clear next action for the user

Keep it under 200 words. Be direct. No fluff."""

_DIGEST_SYSTEM = """You are Piyo. Write a morning digest of new LinkedIn contacts.

For each contact, write 2 lines:
- Name, title at company
- Warm intro suggestion

Keep the whole digest under 150 words."""


def deliver(pipeline_id: str) -> None:
    """
    Read pipeline state and deliver alert to Gmail + Telegram.
    Called by Pippoy after proposal is ready.
    """
    state = read_pipeline(pipeline_id)
    if not state:
        return

    alert_text = _compose_alert(state)
    drive_link = state.get("drive_link")
    research = state.get("research", {})

    _send_gmail(alert_text, drive_link, pipeline_id)
    _send_telegram_dm(alert_text, drive_link, pipeline_id, research)

    write_pipeline(pipeline_id, {"status": PipelineStatus.DELIVERED.value})


def handle_feedback(pipeline_id: str, relevant: bool) -> None:
    """Called when user taps ✅ or ❌ on Telegram inline button."""
    write_pipeline(pipeline_id, {"user_feedback": relevant})


def send_morning_digest() -> None:
    """Triggered by QwenPaw cron at 07:00 WIB. Reads yesterday's contacts."""
    from skills.cepoy import get_yesterday_contacts
    contacts = get_yesterday_contacts()
    if not contacts:
        return

    response = chat(
        messages=[
            {"role": "system", "content": _DIGEST_SYSTEM},
            {"role": "user", "content": json.dumps(contacts)},
        ],
        model=fast_model(),
    )
    digest_text = response.choices[0].message.content.strip()
    _send_telegram_dm(f"☀️ Morning Digest\n\n{digest_text}", None, "digest", {})


def _compose_alert(state: dict) -> str:
    reasoning = state.get("reasoning_trace", "")
    research = state.get("research", {})
    opportunity = state.get("opportunity", {})

    context = json.dumps({
        "opportunity_text": opportunity.get("raw_text", ""),
        "reasoning_trace": reasoning[-1000:],  # Last 1000 chars — enough for Why card
        "fit_score": research.get("fit_score"),
        "fit_reasoning": research.get("fit_reasoning"),
        "competitor_count": research.get("competitor_count", 0),
        "budget": opportunity.get("budget"),
        "deadline": opportunity.get("deadline"),
    })

    response = chat(
        messages=[
            {"role": "system", "content": _COMPOSE_SYSTEM},
            {"role": "user", "content": context},
        ],
        model=fast_model(),
    )
    return response.choices[0].message.content.strip()


def _send_gmail(alert_text: str, drive_link: str | None, pipeline_id: str) -> None:
    try:
        import base64
        from email.mime.text import MIMEText
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(os.environ["GMAIL_CREDENTIALS_JSON"])
        service = build("gmail", "v1", credentials=creds)

        body = alert_text
        if drive_link:
            body += f"\n\n📄 Proposal: {drive_link}"
        body += f"\n\n🔗 Pipeline: {pipeline_id[:8]}"

        message = MIMEText(body)
        message["to"] = os.environ["GMAIL_SENDER_ADDRESS"]
        message["subject"] = "🎯 RADAR: New Opportunity Detected"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

    except Exception as e:
        db().collection("pipelines").document(pipeline_id).set(
            {"gmail_error": str(e)}, merge=True
        )


def _send_telegram_dm(
    alert_text: str,
    drive_link: str | None,
    pipeline_id: str,
    research: dict,
) -> None:
    try:
        import requests

        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_USER_CHAT_ID"]

        text = alert_text
        if drive_link:
            text += f"\n\n📄 [View Proposal]({drive_link})"

        # Inline keyboard for feedback
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Relevant", "callback_data": f"feedback:relevant:{pipeline_id}"},
                {"text": "❌ Not relevant", "callback_data": f"feedback:irrelevant:{pipeline_id}"},
            ]]
        }

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": reply_markup,
            },
            timeout=10,
        ).raise_for_status()

    except Exception as e:
        db().collection("pipelines").document(pipeline_id).set(
            {"telegram_error": str(e)}, merge=True
        )

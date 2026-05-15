"""
Piyo — Notifier & Delivery

Responsibilities:
- Compose alert with "Why RADAR flagged this" card
- Send email via SMTP (no Google Console needed)
- Send Telegram DM with proposal text inline + ✅/❌ feedback buttons
- Handle feedback callback → write to SQLite
- Send morning digest of yesterday's LinkedIn contacts

Model: kimi-k2.6 (composition task)
"""
from __future__ import annotations

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from base import chat, fast_model, read_pipeline, read_user_profile, write_pipeline
from radar_types import PipelineStatus

_COMPOSE_SYSTEM = """You are Piyo, a notification composer for RADAR.

Write a concise, actionable alert for a business opportunity.

Include:
1. 🎯 One-line summary of the opportunity
2. 💡 "Kenapa RADAR flagged ini" — exactly 3 bullet points from the reasoning trace
3. 📋 Key details: budget, deadline, competitor info
4. ⚡ Clear next action for the user

Keep it under 200 words. Be direct and energetic. No fluff.
Match the user's language (Indonesian/English/Chinese)."""

_DIGEST_SYSTEM = """You are Piyo. Write a morning digest of new LinkedIn contacts.

For each contact write 2 lines:
- Name, title at company
- Warm intro suggestion

Keep the whole digest under 150 words. Be warm and concise."""


def deliver(pipeline_id: str) -> None:
    """Deliver alert to email + Telegram DM. Called by Pippoy."""
    state = read_pipeline(pipeline_id)
    if not state:
        return

    alert_text = _compose_alert(state)
    proposal_text = state.get("proposal_text", "")
    research = state.get("research", {})

    # Get user's contact info
    user_id = state.get("opportunity", {}).get("source_channel", "default").split(":")[-1]
    profile = read_user_profile(user_id) or {}
    recipient_email = profile.get("gmail_address")

    if recipient_email:
        _send_email(alert_text, proposal_text, pipeline_id, recipient_email)

    _send_telegram_dm(alert_text, proposal_text, pipeline_id)
    write_pipeline(pipeline_id, {"status": PipelineStatus.DELIVERED.value})


def handle_feedback(pipeline_id: str, relevant: bool) -> None:
    """Called when user taps ✅ or ❌ on Telegram inline button."""
    write_pipeline(pipeline_id, {"user_feedback": relevant})


def send_morning_digest() -> None:
    """Triggered by QwenPaw cron at 07:00 WIB (00:00 UTC)."""
    from cepoy import get_yesterday_contacts
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
    _send_telegram_dm(f"☀️ *Morning Digest*\n\n{digest_text}", "", "digest")


def _compose_alert(state: dict) -> str:
    reasoning = state.get("reasoning_trace", "")
    research = state.get("research", {})
    opportunity = state.get("opportunity", {})

    response = chat(
        messages=[
            {"role": "system", "content": _COMPOSE_SYSTEM},
            {"role": "user", "content": json.dumps({
                "opportunity_text": opportunity.get("raw_text", ""),
                "reasoning_trace": reasoning[-1000:],
                "fit_score": research.get("fit_score"),
                "fit_reasoning": research.get("fit_reasoning"),
                "competitor_count": research.get("competitor_count", 0),
                "budget": opportunity.get("budget"),
                "deadline": opportunity.get("deadline"),
            })},
        ],
        model=fast_model(),
    )
    return response.choices[0].message.content.strip()


def _send_email(alert_text: str, proposal_text: str, pipeline_id: str, recipient: str) -> None:
    """Send via SMTP — works with Gmail App Password, no Google Console needed."""
    try:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASSWORD", "")

        if not smtp_user or not smtp_pass:
            return  # SMTP not configured — skip silently

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🎯 RADAR: Peluang Bisnis Baru Terdeteksi"
        msg["From"] = smtp_user
        msg["To"] = recipient

        body = alert_text
        if proposal_text:
            body += f"\n\n{'─'*40}\n📝 DRAFT PROPOSAL\n{'─'*40}\n\n{proposal_text}"
        body += f"\n\n{'─'*40}\nPipeline ID: {pipeline_id[:8]}"

        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())

    except Exception as e:
        write_pipeline(pipeline_id, {"email_error": str(e)})


def _send_telegram_dm(alert_text: str, proposal_text: str, pipeline_id: str) -> None:
    """Send Telegram DM with inline feedback buttons."""
    try:
        import requests

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_USER_CHAT_ID", "")
        if not token or not chat_id:
            return

        # Alert message with feedback buttons
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Relevan", "callback_data": f"feedback:relevant:{pipeline_id}"},
                {"text": "❌ Tidak relevan", "callback_data": f"feedback:irrelevant:{pipeline_id}"},
            ]]
        }

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": alert_text,
                "parse_mode": "Markdown",
                "reply_markup": reply_markup,
            },
            timeout=10,
        ).raise_for_status()

        # Send proposal as separate message if exists
        if proposal_text:
            proposal_msg = f"📝 *Draft Proposal*\n\n{proposal_text}\n\n_Copy dan kirim ke klien_ ✉️"
            # Split if too long (Telegram limit 4096 chars)
            for chunk in [proposal_msg[i:i+4000] for i in range(0, len(proposal_msg), 4000)]:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                    timeout=10,
                )

    except Exception as e:
        write_pipeline(pipeline_id, {"telegram_error": str(e)})

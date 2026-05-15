"""
Pippoy — Proposal Drafter

Responsibilities:
- Wait for Pippi's ResearchContext (called sequentially by pippi.run)
- Load user's past proposals to match writing style
- Draft a personalized proposal
- Save to Google Drive
- Return shareable link to APPA via Firestore

Model: kimi-k2.6 (long-form generation, style matching)
"""
from __future__ import annotations

import json
import os
from skills.base import chat, db, write_pipeline
from skills.types import OpportunityPayload, PipelineStatus, ResearchContext

_DRAFT_SYSTEM = """You are Pippoy, a proposal writing agent.

Write a professional, personalized business proposal based on the opportunity and research context.
Match the writing style of the past proposals provided.

Requirements:
- Opening: reference something specific about the client/opportunity
- Body: explain relevant experience and approach (3-4 paragraphs)
- Closing: clear call to action with availability
- Tone: match the style examples exactly
- Language: match the language of the opportunity (Indonesian or English)

Return the proposal as plain text, ready to send."""


def run(
    pipeline_id: str,
    payload: OpportunityPayload,
    research: ResearchContext,
    profile: dict,
) -> str | None:
    """
    Draft proposal and save to Google Drive.
    Returns Drive shareable link, or None if Drive save fails.
    """
    past_proposals = _load_past_proposals(profile.get("user_id", "default"))

    prompt_content = json.dumps({
        "opportunity": payload.raw_text,
        "market_context": research.market_summary,
        "company_info": research.company_info,
        "fit_reasoning": research.fit_reasoning,
        "user_skills": profile.get("skills", []),
        "user_rate": profile.get("hourly_rate"),
        "style_examples": past_proposals,
    })

    response = chat(
        messages=[
            {"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": prompt_content},
        ],
    )

    proposal_text = response.choices[0].message.content.strip()
    drive_link = _save_to_drive(pipeline_id, proposal_text, payload)

    write_pipeline(pipeline_id, {
        "status": PipelineStatus.PROPOSAL_READY.value,
        "drive_link": drive_link,
    })

    # Trigger Piyo as final step
    from skills import piyo
    piyo.deliver(pipeline_id)

    return drive_link


def _load_past_proposals(user_id: str) -> list[str]:
    """Load last 3 accepted proposals from Firestore for style matching."""
    docs = (
        db().collection("proposals")
        .where("user_id", "==", user_id)
        .where("accepted", "==", True)
        .order_by("created_at", direction="DESCENDING")
        .limit(3)
        .stream()
    )
    return [d.to_dict().get("text", "") for d in docs]


def _save_to_drive(pipeline_id: str, text: str, payload: OpportunityPayload) -> str | None:
    """
    Create a Google Doc via Drive API and return shareable link.
    Returns None on failure — pipeline continues with degraded alert.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_DRIVE_CREDENTIALS_JSON"],
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=creds)

        # Create Google Doc
        file_metadata = {
            "name": f"Proposal — {pipeline_id[:8]}",
            "mimeType": "application/vnd.google-apps.document",
        }
        from googleapiclient.http import MediaInMemoryUpload
        media = MediaInMemoryUpload(text.encode("utf-8"), mimetype="text/plain")
        file = service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()

        file_id = file.get("id")

        # Make shareable (anyone with link can view)
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return f"https://docs.google.com/document/d/{file_id}/edit"

    except Exception as e:
        # Log but don't crash — Piyo will note "proposal unavailable"
        db().collection("pipelines").document(pipeline_id).set(
            {"drive_error": str(e)}, merge=True
        )
        return None

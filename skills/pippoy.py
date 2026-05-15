"""
Pippoy — Proposal Drafter

Responsibilities:
- Wait for Pippi's ResearchContext (called sequentially by pippi.run)
- Load user's past proposals to match writing style
- Draft a personalized, context-rich proposal
- Save to Google Drive as a Google Doc
- Return shareable link to pipeline state in Firestore

Model: kimi-k2.6 (long-form generation, style matching)
Runtime: called by pippi.run() — never called directly
"""
from __future__ import annotations

import json
import os
from skills.base import chat, db, write_pipeline
from skills.types import OpportunityPayload, PipelineStatus, ResearchContext

_DRAFT_SYSTEM = """You are Pippoy, a professional proposal writing agent for a freelancer/agency.

Your goal: write a proposal that feels personal, competent, and immediately actionable.
The client should feel like you've done your homework and understand their specific situation.

## Structure (follow this exactly)
1. **Opening** (1 paragraph)
   - Reference something specific about the client, their company, or the opportunity
   - Show you understand their problem, not just the job description
   - Do NOT start with "I am writing to apply..." or generic openers

2. **Relevant Experience** (1-2 paragraphs)
   - Highlight 2-3 specific skills or past experiences directly relevant to this opportunity
   - Be concrete: mention technologies, outcomes, or similar projects
   - Use the research context provided to make connections

3. **Proposed Approach** (1 paragraph)
   - Briefly describe how you would tackle this specific project
   - Show you've thought about their problem, not just your capabilities

4. **Availability & Next Step** (1 paragraph)
   - State availability clearly
   - Propose a specific next action (call, demo, sample work)
   - Keep it confident, not desperate

## Style Rules
- Match the language of the opportunity (Indonesian if they wrote in Indonesian, English if English)
- Match the tone and formality of the style examples provided
- Keep total length 250-400 words
- No bullet points in the final proposal — flowing paragraphs only
- No placeholder text like [Your Name] — write as if from the user directly

## What NOT to do
- Do not mention competitor count or market research explicitly
- Do not reveal that this was AI-generated
- Do not use generic phrases: "I am a passionate developer", "I would love to", "Please consider me"

Return the proposal as plain text only, ready to copy-paste and send."""


def run(
    pipeline_id: str,
    payload: OpportunityPayload,
    research: ResearchContext,
    profile: dict,
) -> str | None:
    """
    Draft proposal and save to Google Drive.
    Returns Drive shareable link, or None if Drive save fails.
    Pipeline continues either way — Piyo notes if proposal is unavailable.
    """
    past_proposals = _load_past_proposals(profile.get("user_id", "default"))

    prompt_content = json.dumps({
        "opportunity": payload.raw_text,
        "budget_mentioned": payload.budget,
        "deadline_mentioned": payload.deadline,
        "market_context": research.market_summary,
        "company_info": research.company_info,
        "fit_reasoning": research.fit_reasoning,
        "competitor_count": research.competitor_count,
        "user_skills": profile.get("skills", []),
        "user_rate": profile.get("hourly_rate"),
        "user_categories": profile.get("preferred_categories", []),
        "style_examples": past_proposals,  # Empty list = no style constraint, write naturally
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
        "proposal_preview": proposal_text[:300],  # First 300 chars for dashboard preview
    })

    # Final step — deliver via Piyo
    from skills import piyo
    piyo.deliver(pipeline_id)

    return drive_link


def _load_past_proposals(user_id: str) -> list[str]:
    """Load last 3 accepted proposals from Firestore for style matching."""
    try:
        docs = (
            db().collection("proposals")
            .where("user_id", "==", user_id)
            .where("accepted", "==", True)
            .order_by("created_at", direction="DESCENDING")
            .limit(3)
            .stream()
        )
        return [d.to_dict().get("text", "") for d in docs if d.to_dict().get("text")]
    except Exception:
        return []  # No past proposals — Pippoy writes naturally without style constraint


def _save_to_drive(pipeline_id: str, text: str, payload: OpportunityPayload) -> str | None:
    """
    Create a Google Doc via Drive API and return shareable link.
    Returns None on failure — pipeline continues with degraded alert.
    """
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_DRIVE_CREDENTIALS_JSON"],
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": f"Proposal — {pipeline_id[:8]}",
            "mimeType": "application/vnd.google-apps.document",
        }
        media = MediaInMemoryUpload(text.encode("utf-8"), mimetype="text/plain")
        file = service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()

        file_id = file.get("id")
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return f"https://docs.google.com/document/d/{file_id}/edit"

    except Exception as e:
        db().collection("pipelines").document(pipeline_id).set(
            {"drive_error": str(e)}, merge=True
        )
        return None

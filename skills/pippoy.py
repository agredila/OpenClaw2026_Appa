"""
Pippoy — Proposal Drafter

Responsibilities:
- Wait for Pippi's ResearchContext (called sequentially by pippi.run)
- Load user's past proposals to match writing style
- Draft a personalized proposal
- Save proposal text to SQLite
- Pass proposal text directly to Piyo (no Drive link needed)

Model: kimi-k2.6 (long-form generation, style matching)
Runtime: called by pippi.run() — never called directly
"""
from __future__ import annotations

import json
from base import chat, write_pipeline, _get_conn, new_id, now_iso
from radar_types import OpportunityPayload, PipelineStatus, ResearchContext

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

3. **Proposed Approach** (1 paragraph)
   - Briefly describe how you would tackle this specific project

4. **Availability & Next Step** (1 paragraph)
   - State availability clearly
   - Propose a specific next action (call, demo, sample work)

## Style Rules
- Match the language of the opportunity (Indonesian if they wrote in Indonesian, English if English)
- Match the tone of the style examples if provided
- Keep total length 250-400 words
- No bullet points — flowing paragraphs only
- No placeholder text like [Your Name]

## What NOT to do
- Do not use generic phrases: "I am a passionate developer", "I would love to"
- Do not reveal that this was AI-generated

Return the proposal as plain text only, ready to copy-paste and send."""


def run(
    pipeline_id: str,
    payload: OpportunityPayload,
    research: ResearchContext,
    profile: dict,
) -> str:
    """
    Draft proposal, save to SQLite, pass text to Piyo.
    Returns proposal text.
    """
    past_proposals = _load_past_proposals(profile.get("user_id", "default"))

    response = chat(
        messages=[
            {"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": json.dumps({
                "opportunity": payload.raw_text,
                "budget_mentioned": payload.budget,
                "deadline_mentioned": payload.deadline,
                "market_context": research.market_summary,
                "company_info": research.company_info,
                "fit_reasoning": research.fit_reasoning,
                "user_skills": profile.get("skills", []),
                "user_rate": profile.get("hourly_rate"),
                "style_examples": past_proposals,
            })},
        ],
    )

    proposal_text = response.choices[0].message.content.strip()

    # Save to SQLite for style learning
    _save_proposal(profile.get("user_id", "default"), proposal_text)

    write_pipeline(pipeline_id, {
        "status": PipelineStatus.PROPOSAL_READY.value,
        "proposal_text": proposal_text,
        "proposal_preview": proposal_text[:300],
    })

    # Trigger Piyo with proposal text inline
    import piyo
    piyo.deliver(pipeline_id)

    return proposal_text


def _load_past_proposals(user_id: str) -> list[str]:
    """Load last 3 accepted proposals for style matching."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT text FROM proposals WHERE user_id = ? AND accepted = 1 ORDER BY created_at DESC LIMIT 3",
                (user_id,)
            ).fetchall()
        return [row["text"] for row in rows if row["text"]]
    except Exception:
        return []


def _save_proposal(user_id: str, text: str) -> None:
    """Save proposal to SQLite for future style matching."""
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO proposals (id, user_id, text, accepted, created_at) VALUES (?, ?, ?, 0, ?)",
                (new_id(), user_id, text, now_iso())
            )
    except Exception:
        pass

"""
Kiyo — Scout & Listener

Responsibilities:
- Receive raw messages from Telegram & Discord via Hermes gateway
- Classify: opportunity | linkedin_url | noise
- Extract structured payload
- Forward to APPA (noise is silently discarded)

Model: MiniMax-M2.7-highspeed (fast, cheap — this runs on every message)
"""
from __future__ import annotations

import json
import re
from skills.base import chat, fast_model, new_id, now_iso
from skills.types import OpportunityPayload, OpportunityType

_LINKEDIN_PATTERN = re.compile(r"https?://(www\.)?linkedin\.com/in/[^\s]+", re.I)

_CLASSIFY_SYSTEM = """You are Kiyo, a message classifier for a business opportunity detection system.

Classify the message into exactly one of:
- "opportunity": freelance job, project tender, collaboration request, or any paid work offer
- "linkedin_url": message contains a LinkedIn profile URL (may also contain other content)
- "noise": everything else (chit-chat, news, memes, questions, spam)

Respond with valid JSON only:
{
  "type": "opportunity" | "linkedin_url" | "noise",
  "budget": "<extracted budget string or null>",
  "deadline": "<extracted deadline string or null>",
  "contact_name": "<extracted person name or null>",
  "linkedin_url": "<extracted LinkedIn URL or null>"
}"""


def classify(raw_text: str, source_channel: str, message_id: str) -> OpportunityPayload | None:
    """
    Classify a raw message. Returns None if noise (caller should discard).
    """
    # Fast path: detect LinkedIn URL without LLM call
    linkedin_match = _LINKEDIN_PATTERN.search(raw_text)

    response = chat(
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": raw_text},
        ],
        model=fast_model(),
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError):
        # Malformed LLM response — treat as noise, do not crash pipeline
        return None

    opp_type = parsed.get("type", "noise")
    if opp_type == "noise":
        return None

    # Prefer regex-extracted URL over LLM-extracted (more reliable)
    linkedin_url = linkedin_match.group(0) if linkedin_match else parsed.get("linkedin_url")

    return OpportunityPayload(
        type=OpportunityType(opp_type),
        raw_text=raw_text,
        source_channel=source_channel,
        message_id=message_id,
        budget=parsed.get("budget"),
        deadline=parsed.get("deadline"),
        contact_name=parsed.get("contact_name"),
        linkedin_url=linkedin_url,
    )

"""
Pippi — Research Agent

Responsibilities:
- Search market context for the opportunity
- Fetch company info
- Score fit against user profile
- Detect if competitors have already responded
- Trigger Pippoy sequentially after completing (Pippoy waits for this output)

Model: kimi-k2.6 (needs to synthesize search results into structured analysis)
"""
from __future__ import annotations

import json
from skills.base import chat, google_search, write_pipeline
from skills.types import OpportunityPayload, PipelineStatus, ResearchContext

_RESEARCH_SYSTEM = """You are Pippi, a research agent. Analyze the opportunity and search results.

Return valid JSON only:
{
  "market_summary": "<2-3 sentence market context>",
  "company_info": "<what is known about the client/company>",
  "fit_score": <int 1-10>,
  "fit_reasoning": "<why this fits or doesn't fit the user's profile>",
  "competitor_count": <estimated int>,
  "competitor_detected": <bool>
}"""


def run(pipeline_id: str, payload: OpportunityPayload, profile: dict) -> ResearchContext:
    """
    Research the opportunity. Updates Firestore. Triggers Pippoy on completion.
    """
    # 1. Search market context
    keyword = _extract_keyword(payload.raw_text)
    market_results = google_search(f"{keyword} freelance rate Indonesia", num=5)

    # 2. Search company info if contact/company name available
    company_results = []
    if payload.contact_name:
        company_results = google_search(payload.contact_name, num=3)

    # 3. Detect competitors — search for the original post
    competitor_results = google_search(f'"{keyword}" site:telegram.me OR site:discord.com', num=3)
    competitor_detected = len(competitor_results) > 0

    # 4. Synthesize with LLM
    context_text = json.dumps({
        "opportunity": payload.raw_text,
        "user_profile": {
            "skills": profile.get("skills", []),
            "rate": profile.get("hourly_rate"),
            "categories": profile.get("preferred_categories", []),
        },
        "market_results": market_results[:3],
        "company_results": company_results[:2],
        "competitor_signals": competitor_results[:2],
    })

    response = chat(
        messages=[
            {"role": "system", "content": _RESEARCH_SYSTEM},
            {"role": "user", "content": context_text},
        ],
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        parsed = {
            "market_summary": "Research unavailable",
            "company_info": "Unknown",
            "fit_score": 5,
            "fit_reasoning": "Could not parse research results",
            "competitor_count": 0,
            "competitor_detected": False,
        }

    research = ResearchContext(
        pipeline_id=pipeline_id,
        market_summary=parsed["market_summary"],
        company_info=parsed["company_info"],
        fit_score=parsed["fit_score"],
        fit_reasoning=parsed["fit_reasoning"],
        competitor_count=parsed.get("competitor_count", len(competitor_results)),
        competitor_detected=parsed.get("competitor_detected", competitor_detected),
    )

    write_pipeline(pipeline_id, {
        "status": PipelineStatus.RESEARCH.value,
        "research": research.__dict__,
    })

    # Sequential: Pippoy runs only after Pippi completes
    from skills import pippoy
    pippoy.run(pipeline_id, payload, research, profile)

    return research


def _extract_keyword(text: str) -> str:
    """Extract a short search keyword from raw opportunity text."""
    # Take first 10 words as keyword — good enough for search
    words = text.split()[:10]
    return " ".join(words)

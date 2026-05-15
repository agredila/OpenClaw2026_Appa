"""
APPA — Orchestrator

Responsibilities:
- Receive OpportunityPayload from Kiyo
- Reason over it with streaming chain-of-thought (written to Firestore)
- Score 1–10 and route:
    < 4  → reject, log reason
    4–6  → ask clarifying question in source channel, wait, re-score
    7+   → delegate to Pippi (then Pippoy), and/or Cepoy
- Maintain PipelineState in Firestore throughout

Model: kimi-k2.6 (reasoning quality required)
Runtime: QwenPaw cron — triggered on every classified message from Kiyo
"""
from __future__ import annotations

import json
import os
from skills.base import chat, db, new_id, now_iso, read_user_profile, write_pipeline
from skills.guard import AgentTimeout, DailyLimitExceeded, check_and_increment, run_with_timeout
from skills.types import OpportunityPayload, OpportunityType, PipelineStatus

_DEFAULT_USER_ID = "default"  # Single-user MVP; extend for multi-tenant

_REASON_SYSTEM = """You are APPA, the orchestrator of RADAR — a business opportunity detection system.

Your job is to reason carefully about whether an incoming opportunity is worth pursuing,
and to coordinate the right agents to handle it.

## User Context
You will receive the user's profile: their skills, hourly rate, preferred project categories,
and blacklist keywords. Use this to score relevance accurately.

## Scoring Criteria (may be updated by APPA Learner weekly)
Score each opportunity 1–10:
- Budget match with user's rate (0–3 pts)
  * 3 pts: budget clearly meets or exceeds user rate
  * 1-2 pts: budget is close or unspecified
  * 0 pts: budget is clearly below user rate
- Skill match with user's profile (0–3 pts)
  * 3 pts: 80%+ skill overlap
  * 1-2 pts: partial match
  * 0 pts: no relevant skills
- Deadline realism (0–2 pts)
  * 2 pts: deadline is realistic for the scope
  * 1 pt: tight but possible
  * 0 pts: unrealistic or already passed
- Client credibility signals (0–2 pts)
  * 2 pts: company name, website, or verifiable identity present
  * 1 pt: partial info
  * 0 pts: anonymous, no verifiable info

## Routing Rules
- score < 4: REJECT — log reason, stop pipeline
- score 4–6: CLARIFY — post ONE question to source channel, wait for reply, re-score
- score 7+: PROCESS — delegate to Pippi for research, Cepoy if LinkedIn URL present
- blacklist keyword match: REJECT immediately regardless of score

## Reasoning Style
Think step by step. Be specific with numbers.
Example: "Budget 8-12jt matches user rate 8-10jt/project (+3). Python+API skills match 90% (+3).
Deadline 3 weeks realistic for API integration (+2). No company name mentioned (+1). Score: 9/10."

## Output Format
End your response with EXACTLY this JSON on the last line (no trailing text after it):
{"score": <int 1-10>, "route": "opportunity" | "linkedin" | "reject", "rejection_reason": "<string or null>"}"""


def process(payload: OpportunityPayload) -> str:
    """
    Main entry point. Returns pipeline_id.
    Raises DailyLimitExceeded or AgentTimeout on guard failures.
    """
    user_id = _DEFAULT_USER_ID
    check_and_increment(user_id)

    pipeline_id = new_id()
    profile = read_user_profile(user_id) or {}

    # Check blacklist before any LLM call
    blacklist = profile.get("blacklist_keywords", [])
    if any(kw.lower() in payload.raw_text.lower() for kw in blacklist):
        write_pipeline(pipeline_id, {
            "pipeline_id": pipeline_id,
            "status": PipelineStatus.REJECTED.value,
            "opportunity": payload.__dict__,
            "rejection_reason": "Blacklist keyword matched",
            "created_at": now_iso(),
        })
        return pipeline_id

    write_pipeline(pipeline_id, {
        "pipeline_id": pipeline_id,
        "status": PipelineStatus.INITIATED.value,
        "opportunity": payload.__dict__,
        "created_at": now_iso(),
    })

    # Load latest scoring criteria (may have been rewritten by APPA Learner)
    from skills.appa_learner import get_current_criteria
    current_criteria = get_current_criteria(user_id)
    system_prompt = _REASON_SYSTEM.replace(
        "## Scoring Criteria (may be updated by APPA Learner weekly)",
        f"## Scoring Criteria (version: {profile.get('scoring_prompt_version', 1)})"
    ) if current_criteria else _REASON_SYSTEM

    reasoning_trace = _stream_reasoning(pipeline_id, payload, profile, system_prompt)
    decision = _parse_decision(reasoning_trace)

    score = decision.get("score", 0)
    route = decision.get("route", "reject")

    if score < 4 or route == "reject":
        _reject(pipeline_id, decision.get("rejection_reason", "Score too low"))
        return pipeline_id

    if 4 <= score <= 6:
        _set_status(pipeline_id, PipelineStatus.AWAITING_CLARIFICATION)
        clarification = _ask_clarification(payload)
        if clarification:
            enriched = OpportunityPayload(
                **{**payload.__dict__, "raw_text": payload.raw_text + f"\n\nClarification: {clarification}"}
            )
            return process(enriched)  # One re-entry only
        else:
            _reject(pipeline_id, "No clarification received within timeout")
            return pipeline_id

    # Score 7+ — delegate
    _set_status(pipeline_id, PipelineStatus.RESEARCH)

    if payload.type == OpportunityType.LINKEDIN_URL or payload.linkedin_url:
        _delegate_cepoy(pipeline_id, payload)

    if payload.type == OpportunityType.OPPORTUNITY:
        _delegate_pippi(pipeline_id, payload, profile)

    return pipeline_id


def _stream_reasoning(
    pipeline_id: str,
    payload: OpportunityPayload,
    profile: dict,
    system_prompt: str,
) -> str:
    """Stream APPA's chain-of-thought to Firestore token by token. Returns full trace."""
    profile_summary = json.dumps({
        "skills": profile.get("skills", []),
        "rate": profile.get("hourly_rate", "unknown"),
        "categories": profile.get("preferred_categories", []),
        "blacklist": profile.get("blacklist_keywords", []),
        "scoring_version": profile.get("scoring_prompt_version", 1),
    })

    stream = chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User profile:\n{profile_summary}\n\nOpportunity:\n{payload.raw_text}"},
        ],
        stream=True,
    )

    trace = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        trace += delta
        write_pipeline(pipeline_id, {"reasoning_trace": trace})

    return trace


def _parse_decision(trace: str) -> dict:
    """Extract the JSON decision from the last line of APPA's reasoning trace."""
    for line in reversed(trace.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"score": 0, "route": "reject", "rejection_reason": "Could not parse APPA decision"}


def _ask_clarification(payload: OpportunityPayload) -> str | None:
    """
    Post a clarifying question to the source channel via QwenPaw gateway.
    Writes question to Firestore — QwenPaw picks it up and sends to channel.
    Returns None (async — reply arrives via separate webhook trigger).
    """
    question = _generate_clarification_question(payload)
    db().collection("clarifications").document(payload.message_id).set({
        "pipeline_id": payload.message_id,
        "source_channel": payload.source_channel,
        "question": question,
        "status": "pending",
        "created_at": now_iso(),
    })
    return None


def _generate_clarification_question(payload: OpportunityPayload) -> str:
    response = chat(
        messages=[
            {"role": "system", "content": "Generate ONE short clarifying question (max 20 words) to ask about this opportunity. Ask the single most important missing detail needed to score it accurately."},
            {"role": "user", "content": payload.raw_text},
        ],
    )
    return response.choices[0].message.content.strip()


def _reject(pipeline_id: str, reason: str) -> None:
    write_pipeline(pipeline_id, {
        "status": PipelineStatus.REJECTED.value,
        "rejection_reason": reason,
    })


def _set_status(pipeline_id: str, status: PipelineStatus) -> None:
    write_pipeline(pipeline_id, {"status": status.value})


def _delegate_pippi(pipeline_id: str, payload: OpportunityPayload, profile: dict) -> None:
    """Run Pippi. Pippoy runs sequentially inside pippi.run() after research completes."""
    from skills import pippi
    try:
        run_with_timeout(lambda: pippi.run(pipeline_id, payload, profile))
    except AgentTimeout:
        write_pipeline(pipeline_id, {"pippi_status": "timeout"})
        # Still deliver a partial alert via Piyo
        from skills import piyo
        piyo.deliver(pipeline_id)


def _delegate_cepoy(pipeline_id: str, payload: OpportunityPayload) -> None:
    from skills import cepoy
    try:
        run_with_timeout(lambda: cepoy.run(pipeline_id, payload.linkedin_url or ""))
    except AgentTimeout:
        write_pipeline(pipeline_id, {"cepoy_status": "timeout"})

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
"""
from __future__ import annotations

import json
import os
from skills.base import chat, db, new_id, now_iso, read_user_profile, write_pipeline
from skills.guard import AgentTimeout, DailyLimitExceeded, check_and_increment, run_with_timeout
from skills.types import OpportunityPayload, OpportunityType, PipelineStatus

_DEFAULT_USER_ID = "default"  # Single-user MVP; extend for multi-tenant

_REASON_SYSTEM = """You are APPA, the orchestrator of RADAR — a business opportunity detection system.

Score this opportunity 1–10 using the user's profile below.
Scoring criteria:
- Budget match with user's rate (0–3 pts)
- Skill match with user's profile (0–3 pts)
- Deadline realism (0–2 pts)
- Client credibility signals (0–2 pts)

Think step by step. Be specific with numbers and reasoning.
End your response with exactly this JSON on the last line:
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

    write_pipeline(pipeline_id, {
        "pipeline_id": pipeline_id,
        "status": PipelineStatus.INITIATED.value,
        "opportunity": payload.__dict__,
        "created_at": now_iso(),
    })

    # Stream reasoning to Firestore token by token
    reasoning_trace = _stream_reasoning(pipeline_id, payload, profile)
    decision = _parse_decision(reasoning_trace)

    score = decision.get("score", 0)
    route = decision.get("route", "reject")

    if score < 4 or route == "reject":
        _reject(pipeline_id, decision.get("rejection_reason", "Score too low"))
        return pipeline_id

    if 4 <= score <= 6:
        # Ambiguous — ask for clarification, then re-score
        _set_status(pipeline_id, PipelineStatus.AWAITING_CLARIFICATION)
        clarification = _ask_clarification(payload)
        if clarification:
            # Append clarification to payload text and re-process
            enriched = OpportunityPayload(
                **{**payload.__dict__, "raw_text": payload.raw_text + f"\n\nClarification: {clarification}"}
            )
            return process(enriched)  # One re-entry only — clarification already appended
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


def _stream_reasoning(pipeline_id: str, payload: OpportunityPayload, profile: dict) -> str:
    """Stream APPA's chain-of-thought to Firestore. Returns full trace."""
    profile_summary = json.dumps({
        "skills": profile.get("skills", []),
        "rate": profile.get("hourly_rate", "unknown"),
        "categories": profile.get("preferred_categories", []),
    })

    stream = chat(
        messages=[
            {"role": "system", "content": _REASON_SYSTEM},
            {"role": "user", "content": f"User profile: {profile_summary}\n\nOpportunity:\n{payload.raw_text}"},
        ],
        stream=True,
    )

    trace = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        trace += delta
        # Write incremental trace to Firestore for live dashboard streaming
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
    Post a clarifying question to the source channel via Telegram/Discord.
    Returns the reply text, or None if no reply within timeout.
    This is a stub — actual channel reply is handled by Hermes gateway.
    """
    # Hermes gateway handles the actual message send via skill return value.
    # APPA signals the question; Hermes delivers it and routes the reply back.
    question = _generate_clarification_question(payload)
    # Write question to Firestore so Hermes gateway can pick it up
    db().collection("clarifications").document(payload.message_id).set({
        "pipeline_id": payload.message_id,
        "source_channel": payload.source_channel,
        "question": question,
        "status": "pending",
        "created_at": now_iso(),
    })
    return None  # Async — reply arrives via separate webhook trigger


def _generate_clarification_question(payload: OpportunityPayload) -> str:
    response = chat(
        messages=[
            {"role": "system", "content": "Generate ONE short clarifying question (max 20 words) to ask about this opportunity. Ask the most important missing detail."},
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
    """Import and run Pippi. Pippoy runs sequentially after Pippi inside pippi.run()."""
    from skills import pippi
    try:
        run_with_timeout(lambda: pippi.run(pipeline_id, payload, profile))
    except AgentTimeout:
        write_pipeline(pipeline_id, {"pippi_status": "timeout"})


def _delegate_cepoy(pipeline_id: str, payload: OpportunityPayload) -> None:
    from skills import cepoy
    try:
        run_with_timeout(lambda: cepoy.run(pipeline_id, payload.linkedin_url or ""))
    except AgentTimeout:
        write_pipeline(pipeline_id, {"cepoy_status": "timeout"})

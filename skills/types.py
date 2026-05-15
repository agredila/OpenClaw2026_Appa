"""
Canonical data models for RADAR.
All agents read and write these types. Change here, change everywhere.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OpportunityType(str, Enum):
    OPPORTUNITY = "opportunity"
    LINKEDIN_URL = "linkedin_url"
    NOISE = "noise"


class PipelineStatus(str, Enum):
    INITIATED = "initiated"
    RESEARCH = "research"
    PROPOSAL_READY = "proposal_ready"
    DELIVERED = "delivered"
    FAILED = "failed"
    REJECTED = "rejected"
    AWAITING_CLARIFICATION = "awaiting_clarification"


@dataclass
class OpportunityPayload:
    """Output of Kiyo. Input to APPA."""
    type: OpportunityType
    raw_text: str
    source_channel: str          # e.g. "telegram:group_id" or "discord:channel_id"
    message_id: str
    budget: Optional[str] = None
    deadline: Optional[str] = None
    contact_name: Optional[str] = None
    linkedin_url: Optional[str] = None


@dataclass
class UserProfile:
    """Stored in Firestore. Read by Pippi and Pippoy."""
    user_id: str
    skills: list[str] = field(default_factory=list)
    hourly_rate: Optional[str] = None
    preferred_categories: list[str] = field(default_factory=list)
    blacklist_keywords: list[str] = field(default_factory=list)
    language: str = "id"
    scoring_prompt_version: int = 1


@dataclass
class ResearchContext:
    """Output of Pippi. Input to Pippoy."""
    pipeline_id: str
    market_summary: str
    company_info: str
    fit_score: int               # 1–10
    fit_reasoning: str
    competitor_count: int        # how many others likely saw this post
    competitor_detected: bool


@dataclass
class PipelineState:
    """Firestore document: pipelines/{pipeline_id}"""
    pipeline_id: str
    status: PipelineStatus
    opportunity: OpportunityPayload
    routing_score: Optional[int] = None
    reasoning_trace: str = ""    # APPA's streamed chain-of-thought
    research: Optional[ResearchContext] = None
    drive_link: Optional[str] = None
    rejection_reason: Optional[str] = None
    user_feedback: Optional[bool] = None   # True=relevant, False=not relevant
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class ContactSummary:
    """Output of Cepoy. Stored in Firestore: contacts/{contact_id}"""
    contact_id: str
    linkedin_url: str
    name: str
    title: str
    company: str
    recent_activity: str
    relevance_note: str
    warm_intro: str
    created_at: Optional[str] = None

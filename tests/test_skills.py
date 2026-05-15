"""
RADAR smoke tests — verifiable by Claude Code / Cursor Agent.

Run: python -m pytest tests/ -v

These tests validate agent logic without real API calls.
All external services (LLM, Firestore, Google APIs, Telegram) are mocked.
"""
import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Ensure skills package is importable from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Types ─────────────────────────────────────────────────────────────────────

def test_opportunity_payload_fields():
    from skills.types import OpportunityPayload, OpportunityType
    p = OpportunityPayload(
        type=OpportunityType.OPPORTUNITY,
        raw_text="Need Python dev, budget 10jt",
        source_channel="telegram:123",
        message_id="msg_1",
        budget="10jt",
    )
    assert p.type == OpportunityType.OPPORTUNITY
    assert p.budget == "10jt"
    assert p.linkedin_url is None


def test_pipeline_status_values():
    from skills.types import PipelineStatus
    assert PipelineStatus.INITIATED.value == "initiated"
    assert PipelineStatus.DELIVERED.value == "delivered"
    assert PipelineStatus.REJECTED.value == "rejected"


# ── Guard ─────────────────────────────────────────────────────────────────────

def test_guard_raises_on_limit(monkeypatch):
    from skills import guard
    monkeypatch.setenv("MAX_OPPORTUNITIES_PER_DAY", "5")
    with patch("skills.guard.get_daily_usage", return_value=5):
        with pytest.raises(guard.DailyLimitExceeded):
            guard.check_and_increment("user_1")


def test_guard_passes_under_limit(monkeypatch):
    from skills import guard
    monkeypatch.setenv("MAX_OPPORTUNITIES_PER_DAY", "20")
    with patch("skills.guard.get_daily_usage", return_value=3):
        with patch("skills.guard.increment_daily_usage", return_value=4):
            count = guard.check_and_increment("user_1")
    assert count == 4


def test_guard_timeout():
    from skills.guard import run_with_timeout, AgentTimeout
    import time
    with pytest.raises(AgentTimeout):
        run_with_timeout(lambda: time.sleep(5), timeout_seconds=1)


def test_guard_timeout_returns_result():
    from skills.guard import run_with_timeout
    result = run_with_timeout(lambda: 42, timeout_seconds=5)
    assert result == 42


# ── Kiyo ──────────────────────────────────────────────────────────────────────

def test_kiyo_classifies_opportunity():
    from skills import kiyo
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "type": "opportunity",
        "budget": "10jt",
        "deadline": "2 weeks",
        "contact_name": None,
        "linkedin_url": None,
    })
    with patch("skills.kiyo.chat", return_value=mock_response):
        result = kiyo.classify("Need Python dev, budget 10jt", "telegram:123", "msg_1")
    assert result is not None
    assert result.type.value == "opportunity"
    assert result.budget == "10jt"


def test_kiyo_returns_none_for_noise():
    from skills import kiyo
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({"type": "noise"})
    with patch("skills.kiyo.chat", return_value=mock_response):
        result = kiyo.classify("Good morning everyone!", "telegram:123", "msg_2")
    assert result is None


def test_kiyo_detects_linkedin_url_via_regex():
    from skills import kiyo
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "type": "linkedin_url",
        "budget": None,
        "deadline": None,
        "contact_name": "John Doe",
        "linkedin_url": None,  # LLM missed it — regex should catch it
    })
    with patch("skills.kiyo.chat", return_value=mock_response):
        result = kiyo.classify(
            "Check out https://linkedin.com/in/johndoe123",
            "telegram:123",
            "msg_3",
        )
    assert result is not None
    assert result.linkedin_url == "https://linkedin.com/in/johndoe123"


def test_kiyo_handles_malformed_llm_response():
    from skills import kiyo
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "not valid json {{{"
    with patch("skills.kiyo.chat", return_value=mock_response):
        result = kiyo.classify("some message", "telegram:123", "msg_4")
    assert result is None  # Malformed response → treated as noise, no crash


# ── APPA ──────────────────────────────────────────────────────────────────────

def test_appa_parse_decision_extracts_json():
    from skills.appa import _parse_decision
    trace = 'Budget matches. Skill match 90%.\n{"score": 8, "route": "opportunity", "rejection_reason": null}'
    decision = _parse_decision(trace)
    assert decision["score"] == 8
    assert decision["route"] == "opportunity"


def test_appa_parse_decision_fallback_on_bad_trace():
    from skills.appa import _parse_decision
    decision = _parse_decision("no json here at all")
    assert decision["score"] == 0
    assert decision["route"] == "reject"


# ── Cepoy ─────────────────────────────────────────────────────────────────────

def test_cepoy_extract_name_from_url():
    from skills.cepoy import _extract_name_from_url
    assert _extract_name_from_url("https://linkedin.com/in/john-doe") == "john doe"
    assert _extract_name_from_url("https://www.linkedin.com/in/jane-smith-123456") == "jane smith"
    assert _extract_name_from_url("https://not-linkedin.com/profile") == "unknown"


# ── APPA Learner ──────────────────────────────────────────────────────────────

def test_appa_learner_skips_when_no_feedback():
    from skills import appa_learner
    with patch("skills.appa_learner._load_feedback", return_value={"relevant": [], "irrelevant": []}):
        with patch("skills.appa_learner._save_new_version") as mock_save:
            appa_learner.rewrite_scoring_prompt()
            mock_save.assert_not_called()  # Nothing to learn from → no rewrite


def test_appa_learner_rewrites_when_feedback_exists():
    from skills import appa_learner
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Updated criteria: prefer 8jt+ projects"
    with patch("skills.appa_learner._load_feedback", return_value={
        "relevant": ["Python dev 10jt"],
        "irrelevant": ["Design work 2jt"],
    }):
        with patch("skills.appa_learner._load_current_criteria", return_value="old criteria"):
            with patch("skills.appa_learner.chat", return_value=mock_response):
                with patch("skills.appa_learner._save_new_version") as mock_save:
                    appa_learner.rewrite_scoring_prompt()
                    mock_save.assert_called_once()
                    args = mock_save.call_args[0]
                    assert "Updated criteria" in args[2]

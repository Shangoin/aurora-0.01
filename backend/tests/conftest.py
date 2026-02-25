"""
Shango Revenue Systems — Test Configuration & Shared Fixtures
"""
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI


# ─── Shared Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _preload_app():
    """Pre-import the FastAPI app once so load_dotenv() fires before any test
    clears environment variables.  Subsequent imports use Python's module cache."""
    from main import app  # noqa: F401 — side-effect: calls load_dotenv()


@pytest.fixture(autouse=True)
def clear_secret_env_vars(monkeypatch, _preload_app):
    """Ensure WEBHOOK_SECRET and ADMIN_SECRET are unset by default so tests
    that don't need auth don't get 401/403 from load_dotenv() side-effects."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_SECRET", raising=False)


@pytest.fixture
def mock_supabase():
    """Fully mocked Supabase client with chainable query builder."""
    mock = MagicMock()
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[], count=0)
    mock.table.return_value.select.return_value = chain
    mock.table.return_value.select.return_value.eq.return_value = chain
    mock.table.return_value.select.return_value.order.return_value = chain
    mock.table.return_value.select.return_value.limit.return_value = chain
    mock.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "test-uuid"}])
    mock.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-uuid"}])
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    return mock


@pytest.fixture
def sample_lead():
    """Valid lead payload for testing."""
    return {
        "name": "Test User",
        "email": "test@example.com",
        "phone": "+1234567890",
        "company": "Acme Corp",
        "lead_volume": "10-50",
        "message": "I need AI to handle my sales pipeline",
    }


@pytest.fixture
def sample_score_response():
    """Mocked AI scoring response."""
    return {
        "score": 82,
        "tier": "high",
        "reasoning": "Strong ICP fit with urgent pain point and clear budget.",
        "icp_fit": True,
        "urgency": "high",
        "budget_signals": ["mentioned budget approval", "Q4 deadline"],
        "recommended_delay_minutes": 5,
    }


@pytest.fixture
def sample_vapi_webhook():
    """Vapi end-of-call webhook payload."""
    return {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi-call-123",
                "type": "outboundPhoneCall",
                "status": "ended",
                "endedReason": "hangup",
                "duration": 185,
                "cost": 0.045,
                "recordingUrl": "https://cdn.vapi.ai/recordings/test.mp3",
                "metadata": {
                    "lead_email": "test@example.com",
                    "lead_name": "Test User",
                    "lead_company": "Acme Corp",
                },
                "transcript": "ARIA: Hi Test, this is ARIA calling from Shango Revenue Systems. Is now a good time?\nTest: Sure, go ahead.\nARIA: Great! I saw you filled out our form about AI sales pipeline. What's your biggest challenge right now?\nTest: We're losing leads because we can't follow up fast enough.\nARIA: That's exactly what we solve. Would Tuesday at 2pm work for a quick demo?",
            },
        }
    }


@pytest.fixture
def sample_critique_response():
    """Mocked critique result."""
    return {
        "call_id": "vapi-call-123",
        "overall_score": 78,
        "category_scores": {
            "opening": 85,
            "discovery": 80,
            "rapport": 75,
            "objection_handling": 70,
            "closing": 82,
            "naturalness": 78,
            "relevance": 79,
        },
        "pain_points": ["slow follow-up", "lead leakage"],
        "meeting_booked": False,
        "should_follow_up": True,
        "follow_up_strategy": "Send case study on lead response time ROI",
        "script_improvements": [
            {
                "improvement_type": "closing",
                "current_behavior": "Asking open-ended 'when works'",
                "suggested_behavior": "Offer two specific times",
                "example_script": "I have Tuesday 2pm or Wednesday 10am — which works better?",
                "impact": "high",
            }
        ],
        "action_items": ["Send follow-up email", "Add to nurture sequence"],
        "one_line_summary": "Good discovery, weak close — prospect showed buying intent",
        "sentiment": "positive",
        "buying_stage": "consideration",
        "deal_probability": 55,
        "coach_verdict": "Strong opener but missed the close. Use assumptive close next time.",
    }

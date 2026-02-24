"""
Tests: Lead ingestion endpoint — POST /api/lead
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestLeadCreation:
    """Tests for the lead ingestion endpoint."""

    def test_create_lead_success(self, sample_lead, sample_score_response):
        """Valid lead gets scored and returns score/tier."""
        mock_score = MagicMock(
            score=sample_score_response["score"],
            tier=sample_score_response["tier"],
            reasoning=sample_score_response["reasoning"],
            icp_fit=True,
            urgency="high",
            budget_signals=["budget approval"],
            recommended_delay_minutes=5,
        )

        with patch("api.leads.score_lead", new_callable=AsyncMock, return_value=mock_score), \
             patch("api.leads.db_upsert_lead", new_callable=AsyncMock, return_value={"id": "test-uuid"}), \
             patch("api.leads.get_lead_by_email", new_callable=AsyncMock, return_value=None), \
             patch("api.leads.log_event", new_callable=AsyncMock), \
             patch("api.leads.BackgroundTasks.add_task"):

            from main import app
            client = TestClient(app)
            resp = client.post("/api/lead", json=sample_lead)

        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "tier" in data
        assert data["tier"] in ("high", "medium", "low", "unscored")

    def test_create_lead_missing_required_fields(self):
        """Lead without name/email returns 422."""
        from main import app
        client = TestClient(app)
        resp = client.post("/api/lead", json={"message": "test"})
        assert resp.status_code == 422

    def test_create_lead_invalid_email(self, sample_lead):
        """Lead with malformed email returns 422."""
        from main import app
        client = TestClient(app)
        bad_lead = {**sample_lead, "email": "not-an-email"}
        resp = client.post("/api/lead", json=bad_lead)
        assert resp.status_code == 422

    def test_lead_tier_high_gets_fast_delay(self, sample_lead, sample_score_response):
        """High-tier lead gets 5-minute call delay."""
        from ai.scoring import get_call_delay_minutes
        assert get_call_delay_minutes("high") == 5

    def test_lead_tier_medium_gets_15min_delay(self):
        """Medium-tier lead gets 15-minute delay."""
        from ai.scoring import get_call_delay_minutes
        assert get_call_delay_minutes("medium") == 15

    def test_lead_tier_low_gets_60min_delay(self):
        """Low-tier lead gets 60-minute delay."""
        from ai.scoring import get_call_delay_minutes
        assert get_call_delay_minutes("low") == 60


class TestLeadModel:
    """Tests for LeadCreate Pydantic model validation."""

    def test_lead_create_valid(self, sample_lead):
        """Valid lead parses without errors."""
        from models import LeadCreate
        lead = LeadCreate(**sample_lead)
        assert lead.email == "test@example.com"
        assert lead.name == "Test User"

    def test_lead_create_optional_fields(self):
        """Lead can be created with only required fields."""
        from models import LeadCreate
        lead = LeadCreate(name="Min User", email="min@example.com")
        assert lead.phone is None
        assert lead.company is None

    def test_lead_tier_enum_values(self):
        """LeadTier enum has expected values."""
        from models import LeadTier
        assert LeadTier.HIGH == "high"
        assert LeadTier.MEDIUM == "medium"
        assert LeadTier.LOW == "low"

    def test_lead_status_enum_values(self):
        """LeadStatus enum has expected values."""
        from models import LeadStatus
        assert LeadStatus.NEW == "new"
        assert LeadStatus.CALL_COMPLETED == "call_completed"
        assert LeadStatus.MEETING_BOOKED == "meeting_booked"

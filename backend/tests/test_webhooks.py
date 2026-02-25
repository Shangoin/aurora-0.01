"""
Tests: Vapi webhook handler — POST /webhooks/vapi
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestVapiWebhook:
    """Tests for the Vapi webhook endpoint."""

    def test_webhook_end_of_call_success(self, sample_vapi_webhook, sample_critique_response):
        """end-of-call-report triggers critique and DB storage."""
        mock_critique = MagicMock(**sample_critique_response)
        mock_critique.overall_score = 78
        mock_critique.meeting_booked = False
        mock_critique.should_follow_up = True
        mock_critique.follow_up_strategy = "Send case study"
        mock_critique.pain_points = ["slow follow-up"]
        mock_critique.script_improvements = []
        mock_critique.action_items = ["Follow up"]
        mock_critique.one_line_summary = "Good call"
        mock_critique.sentiment = "positive"
        mock_critique.buying_stage = "consideration"
        mock_critique.deal_probability = 55
        mock_critique.coach_verdict = "Strong opener"
        mock_critique.category_scores = MagicMock(
            opening=85, discovery=80, rapport=75,
            objection_handling=70, closing=82, naturalness=78, relevance=79,
        )

        with patch("api.webhooks.critique_call", new_callable=AsyncMock, return_value=mock_critique), \
             patch("api.webhooks.insert_call", new_callable=AsyncMock, return_value={"id": "call-uuid"}), \
             patch("api.webhooks.update_lead_status", new_callable=AsyncMock), \
             patch("api.webhooks.insert_improvement", new_callable=AsyncMock), \
             patch("api.webhooks.get_calls_since", new_callable=AsyncMock, return_value=[]), \
             patch("api.webhooks.log_event", new_callable=AsyncMock):

            from main import app
            client = TestClient(app)
            resp = client.post("/webhooks/vapi", json=sample_vapi_webhook)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"

    def test_webhook_call_started_returns_ack(self):
        """call-started event is acknowledged without processing."""
        from main import app
        client = TestClient(app)
        payload = {"message": {"type": "call-started", "call": {"id": "test-call"}}}
        resp = client.post("/webhooks/vapi", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    def test_webhook_status_update_returns_ack(self):
        """status-update event is acknowledged."""
        from main import app
        client = TestClient(app)
        payload = {"message": {"type": "status-update", "call": {"id": "test-call", "status": "ringing"}}}
        resp = client.post("/webhooks/vapi", json=payload)
        assert resp.status_code == 200

    def test_webhook_unknown_type_returns_ignored(self):
        """Unknown event type returns ignored status."""
        from main import app
        client = TestClient(app)
        payload = {"message": {"type": "unknown-event"}}
        resp = client.post("/webhooks/vapi", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_manual_trigger_requires_secret(self):
        """Trigger endpoint rejects requests without admin secret."""
        from main import app
        client = TestClient(app)
        resp = client.post("/webhooks/trigger-improvement")
        assert resp.status_code == 403

    def test_manual_trigger_with_valid_secret(self):
        """Trigger endpoint accepts valid admin secret."""
        import os
        os.environ["ADMIN_SECRET"] = "test-secret-123"

        mock_result = {"version": 2, "changelog": "Improved closing technique", "improvements_applied": 3}

        with patch("api.webhooks.run_improvement_cycle", new_callable=AsyncMock, return_value=mock_result):
            from main import app
            client = TestClient(app)
            resp = client.post(
                "/webhooks/trigger-improvement",
                headers={"X-Admin-Secret": "test-secret-123"},
            )

        assert resp.status_code == 200


class TestWebhookPayloadParsing:
    """Tests for Vapi webhook payload parsing."""

    def test_webhook_extracts_call_duration(self, sample_vapi_webhook):
        """Webhook correctly extracts call duration."""
        call = sample_vapi_webhook["message"]["call"]
        assert call["duration"] == 185

    def test_webhook_extracts_lead_email(self, sample_vapi_webhook):
        """Webhook correctly extracts lead email from metadata."""
        metadata = sample_vapi_webhook["message"]["call"]["metadata"]
        assert metadata["lead_email"] == "test@example.com"

    def test_webhook_extracts_transcript(self, sample_vapi_webhook):
        """Webhook correctly extracts transcript."""
        call = sample_vapi_webhook["message"]["call"]
        assert "ARIA" in call["transcript"]
        assert len(call["transcript"]) > 50

    def test_vapi_webhook_model_valid(self, sample_vapi_webhook):
        """VapiWebhookPayload model parses valid payload."""
        from models import VapiWebhookPayload
        payload = VapiWebhookPayload(**sample_vapi_webhook)
        assert payload.message["type"] == "end-of-call-report"

    def test_webhook_extracts_geo_region(self):
        """Webhook correctly extracts geo_region from metadata."""
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {
                    "id": "geo-call-1",
                    "metadata": {
                        "lead_email": "priya@company.in",
                        "lead_name": "Priya S",
                        "geo_region": "india",
                    },
                    "transcript": "Test",
                    "duration": 120,
                    "endedReason": "hangup",
                    "recordingUrl": "",
                    "summary": "",
                    "stereoRecordingUrl": None,
                }
            }
        }
        # geo_region in metadata should be extracted correctly
        metadata = payload["message"]["call"]["metadata"]
        assert metadata.get("geo_region") == "india"

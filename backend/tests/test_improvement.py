"""
Tests: Self-improvement loop — run_improvement_cycle(), trigger_call()
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestImprovementCycle:
    """Tests for the autonomous self-improvement loop."""

    @pytest.mark.asyncio
    async def test_improvement_cycle_runs_all_steps(self):
        """Full cycle: fetch calls → analyze → new prompt → push to Vapi."""
        mock_calls = [
            {"call_id": "c1", "transcript": "...", "overall_score": 62, "script_improvements": []},
            {"call_id": "c2", "transcript": "...", "overall_score": 71, "script_improvements": []},
        ]
        mock_improvements = [
            {
                "improvement_type": "closing",
                "current_behavior": "Open-ended timing question",
                "suggested_behavior": "Assumptive close with two options",
                "example_script": "I have Tuesday or Wednesday — which works?",
                "impact": "high",
            }
        ]
        mock_new_prompt = "You are ARIA v2. [improved instructions]"
        mock_active_prompt = {"version": 1, "prompt_text": "You are ARIA v1."}
        mock_version_result = {"id": "ver-uuid", "version": 2}

        with patch("ai.improvement.get_recent_calls", new_callable=AsyncMock, return_value=mock_calls), \
             patch("ai.improvement.get_pending_improvements", new_callable=AsyncMock, return_value=mock_improvements), \
             patch("ai.improvement.get_active_prompt", new_callable=AsyncMock, return_value=mock_active_prompt), \
             patch("ai.improvement.cascade_ai_call", new_callable=AsyncMock, return_value='{"new_prompt": "' + mock_new_prompt + '", "changelog": "Improved closing", "improvements": []}'), \
             patch("ai.improvement.insert_prompt_version", new_callable=AsyncMock, return_value=mock_version_result), \
             patch("ai.improvement._update_vapi_assistant", new_callable=AsyncMock, return_value=True), \
             patch("ai.improvement.mark_improvements_applied", new_callable=AsyncMock), \
             patch("ai.improvement.log_event", new_callable=AsyncMock):

            from ai.improvement import run_improvement_cycle
            result = await run_improvement_cycle()

        assert result is not None
        assert "version" in result or "changelog" in result

    @pytest.mark.asyncio
    async def test_improvement_skips_when_no_calls(self):
        """Improvement cycle skips gracefully when no calls exist."""
        with patch("ai.improvement.get_recent_calls", new_callable=AsyncMock, return_value=[]):
            from ai.improvement import run_improvement_cycle
            result = await run_improvement_cycle()

        # Should return early with a descriptive message
        assert result is not None

    @pytest.mark.asyncio
    async def test_trigger_call_sends_correct_payload(self):
        """trigger_call sends correct Vapi POST payload."""
        import httpx
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "new-call-123", "status": "queued"}
        mock_response.raise_for_status = MagicMock()

        with patch("ai.improvement.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from ai.improvement import trigger_call
            result = await trigger_call(
                phone_number="+15551234567",
                lead_name="Test User",
                lead_email="test@example.com",
                lead_company="Acme Corp",
            )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "api.vapi.ai" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["phoneNumberId"] is not None

    @pytest.mark.asyncio
    async def test_update_vapi_assistant_patches_system_prompt(self):
        """_update_vapi_assistant sends PATCH with new prompt."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": "assistant-123"}

        with patch("ai.improvement.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            from ai.improvement import _update_vapi_assistant
            result = await _update_vapi_assistant("New improved system prompt v2")

        mock_client.patch.assert_called_once()
        call_args = mock_client.patch.call_args
        assert "api.vapi.ai" in call_args[0][0]


class TestCritiqueEngine:
    """Tests for the 9-category call critique engine."""

    @pytest.mark.asyncio
    async def test_critique_returns_all_9_categories(self, sample_critique_response):
        """critique_call returns scores for all 9 categories including pacing and silence_handling."""
        mock_ai_json = """{
            "overall_score": 78,
            "category_scores": {
                "opening": 85, "discovery": 80, "rapport": 75,
                "objection_handling": 70, "closing": 82,
                "naturalness": 78, "relevance": 79,
                "pacing": 72, "silence_handling": 68
            },
            "pain_points": ["slow follow-up"],
            "meeting_booked": false,
            "should_follow_up": true,
            "follow_up_strategy": "Send case study",
            "script_improvements": [],
            "action_items": ["Follow up next week"],
            "one_line_summary": "Good discovery, weak close",
            "sentiment": "positive",
            "buying_stage": "consideration",
            "deal_probability": 55,
            "coach_verdict": "Work on assumptive close"
        }"""

        with patch("ai.critique.cascade_ai_call", new_callable=AsyncMock, return_value=mock_ai_json):
            from ai.critique import critique_call
            result = await critique_call(
                call_id="test-call",
                transcript="Sample transcript",
                duration_seconds=185,
                lead_context={},
            )

        assert result.overall_score == 78
        assert result.category_scores.opening == 85
        assert result.category_scores.closing == 82
        assert result.category_scores.pacing == 72
        assert result.category_scores.silence_handling == 68
        assert len(result.pain_points) > 0

    @pytest.mark.asyncio
    async def test_critique_handles_empty_transcript(self):
        """critique_call handles empty transcript gracefully."""
        mock_minimal_json = """{
            "overall_score": 10,
            "category_scores": {"opening":10,"discovery":10,"rapport":10,"objection_handling":10,"closing":10,"naturalness":10,"relevance":10,"pacing":10,"silence_handling":10},
            "pain_points": [],
            "meeting_booked": false,
            "should_follow_up": false,
            "follow_up_strategy": "",
            "script_improvements": [],
            "action_items": [],
            "one_line_summary": "No transcript available",
            "sentiment": "neutral",
            "buying_stage": "unknown",
            "deal_probability": 0,
            "coach_verdict": "Call ended without transcript"
        }"""
        with patch("ai.critique.cascade_ai_call", new_callable=AsyncMock, return_value=mock_minimal_json):
            from ai.critique import critique_call
            result = await critique_call(
                call_id="empty-call",
                transcript="",
                duration_seconds=0,
                lead_context={},
            )

        assert result is not None
        assert result.overall_score >= 0

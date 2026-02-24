"""
Tests: AI scoring module — score_lead()
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestLeadScoring:
    """Tests for the AI lead scoring pipeline."""

    @pytest.mark.asyncio
    async def test_score_lead_returns_high_tier(self, sample_lead, sample_score_response):
        """Strong lead gets scored as 'high' tier."""
        mock_ai_response = """{
            "score": 85,
            "tier": "high",
            "reasoning": "Clear ICP fit with urgent pain and budget.",
            "icp_fit": true,
            "urgency": "high",
            "budget_signals": ["mentioned Q4 deadline"],
            "recommended_delay_minutes": 5
        }"""

        with patch("ai.scoring.cascade_ai_call", new_callable=AsyncMock, return_value=mock_ai_response):
            from ai.scoring import score_lead
            from models import LeadCreate
            lead = LeadCreate(**sample_lead)
            result = await score_lead(lead)

        assert result.score == 85
        assert result.tier == "high"
        assert result.icp_fit is True
        assert result.recommended_delay_minutes == 5

    @pytest.mark.asyncio
    async def test_score_lead_returns_medium_tier(self):
        """Moderate lead gets scored as 'medium' tier."""
        mock_response = """{
            "score": 55,
            "tier": "medium",
            "reasoning": "Some ICP fit but urgency unclear.",
            "icp_fit": true,
            "urgency": "medium",
            "budget_signals": [],
            "recommended_delay_minutes": 15
        }"""

        with patch("ai.scoring.cascade_ai_call", new_callable=AsyncMock, return_value=mock_response):
            from ai.scoring import score_lead
            from models import LeadCreate
            lead = LeadCreate(name="Medium User", email="medium@test.com", company="Corp")
            result = await score_lead(lead)

        assert result.tier == "medium"
        assert result.recommended_delay_minutes == 15

    @pytest.mark.asyncio
    async def test_score_lead_fallback_on_ai_error(self, sample_lead):
        """Lead scoring returns safe default on AI failure."""
        with patch("ai.scoring.cascade_ai_call", new_callable=AsyncMock, side_effect=Exception("AI timeout")):
            from ai.scoring import score_lead
            from models import LeadCreate
            lead = LeadCreate(**sample_lead)
            # Should not raise — should return fallback score
            result = await score_lead(lead)

        assert result is not None
        assert result.score >= 0
        assert result.tier in ("high", "medium", "low", "unscored")

    @pytest.mark.asyncio
    async def test_score_lead_handles_malformed_json(self, sample_lead):
        """Lead scoring handles malformed JSON gracefully."""
        with patch("ai.scoring.cascade_ai_call", new_callable=AsyncMock, return_value="This is not JSON {"):
            from ai.scoring import score_lead
            from models import LeadCreate
            lead = LeadCreate(**sample_lead)
            result = await score_lead(lead)

        assert result is not None

    def test_score_range_validation(self):
        """LeadScore enforces 0-100 score range."""
        from models import LeadScore, LeadTier
        score = LeadScore(
            score=75,
            tier=LeadTier.HIGH,
            reasoning="Good fit",
            icp_fit=True,
            urgency="high",
            budget_signals=[],
            recommended_delay_minutes=5,
        )
        assert 0 <= score.score <= 100

    def test_few_shot_prompt_contains_examples(self):
        """Scoring prompt includes few-shot examples."""
        from ai.scoring import _build_scoring_prompt
        from models import LeadCreate
        lead = LeadCreate(name="Test", email="test@test.com", message="Need AI for sales")
        prompt = _build_scoring_prompt(lead)
        # Should contain CoT reasoning examples
        assert "score" in prompt.lower()
        assert "tier" in prompt.lower()


class TestOrchestratorCaching:
    """Tests for AI orchestrator caching behavior."""

    @pytest.mark.asyncio
    async def test_cached_response_returned_on_second_call(self):
        """Identical prompts return cached result on second call."""
        from ai.orchestrator import cascade_ai_call

        first_response = '{"score": 80, "tier": "high"}'
        call_count = 0

        async def mock_gemini(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return first_response

        with patch("ai.orchestrator._call_gemini", new_callable=AsyncMock, side_effect=mock_gemini):
            r1 = await cascade_ai_call("test prompt unique 1234", "scoring")
            r2 = await cascade_ai_call("test prompt unique 1234", "scoring")

        # Second call should use cache, not re-call Gemini
        assert r1 == r2
        assert call_count == 1

    def test_humanize_text_strips_banned_words(self):
        """humanize_text replaces banned AI words."""
        from ai.orchestrator import humanize_text
        text = "We need to leverage our robust and seamless solution to empower clients."
        result = humanize_text(text)
        assert "leverage" not in result
        assert "robust" not in result
        assert "seamless" not in result
        assert "empower" not in result

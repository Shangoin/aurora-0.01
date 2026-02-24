"""
Shango Revenue Systems — Post-Call Critique Engine
Uses Gemini 2.0 Flash (free) to deeply analyze every sales call.
Score 7 categories, extract pain points, generate script improvements.
"""
import logging
from models import CallCritique, CallScores, ProspectAnalysis, ScriptImprovement, ImprovementImpact
from ai.orchestrator import cascade_ai_call, parse_json_response

logger = logging.getLogger("aurora.critique")

CRITIQUE_SYSTEM = """You are an elite sales call analyst and coach with 20 years of experience training SDR teams at companies like Salesforce, Gong, and Outreach.

Analyze AI SDR call transcripts with surgical precision. Your job is to:
1. Score 7 performance dimensions (0-100 each)
2. Extract actionable pain points from the prospect
3. Identify specific script improvements
4. Determine next best action

Be honest and precise. A score of 70+ means genuinely good performance.
Score below 40 means significant problems need fixing immediately."""

CRITIQUE_PROMPT_TEMPLATE = """Analyze this AI SDR call transcript:

LEAD CONTEXT:
- Name: {lead_name}
- Company: {company}
- Lead Score: {lead_score}/100
- Tier: {tier}
- Original Message: {original_message}

CALL TRANSCRIPT:
{transcript}

CALL DURATION: {duration_seconds} seconds
CALL ID: {call_id}

Score these 7 dimensions (0-100) and return valid JSON only:

{{
  "scores": {{
    "opening": <score>,        // First impression, hook, permission to continue
    "discovery": <score>,      // Pain uncovering, question quality, listening
    "rapport": <score>,        // Conversational, human, not robotic
    "objection_handling": <score>, // Graceful, empathetic, redirects well
    "closing": <score>,        // Clear ask, calendar-focused, specific
    "naturalness": <score>,    // Sounds human, not scripted
    "relevance": <score>,      // Responses tied to what prospect actually said
    "overall": <score>         // Weighted average
  }},
  "meeting_booked": <true|false>,
  "should_follow_up": <true|false>,
  "follow_up_strategy": "<email|call|sms|none>",
  "estimated_deal_probability": <0-100>,
  "one_line_summary": "<what happened in 1 sentence>",
  "coach_verdict": "<what the AI did well and what to fix — 2-3 sentences>",
  "prospect_analysis": {{
    "pain_points": ["<pain1>", "<pain2>"],
    "buying_stage": "<awareness|consideration|decision|unknown>",
    "sentiment_overall": "<positive|neutral|negative|hostile>",
    "budget_signals": "<what was said about budget/cost>",
    "objections_raised": ["<objection1>", "<objection2>"]
  }},
  "action_items": [
    "<specific next action 1>",
    "<specific next action 2>"
  ],
  "script_improvements": [
    {{
      "category": "<opening|discovery|objection|closing|naturalness>",
      "current_behavior": "<what the AI said that didn't work>",
      "suggested_behavior": "<what it should have said instead>",
      "example_script": "<exact words to use next time>",
      "impact": "<high|medium|low>"
    }}
  ]
}}"""


async def critique_call(
    transcript: str,
    call_id: str,
    lead_name: str = "Unknown",
    company: str = "Unknown",
    lead_score: int = 0,
    tier: str = "unknown",
    original_message: str = "",
    duration_seconds: int = 0,
) -> CallCritique:
    """
    Run deep critique on a completed call.
    Uses Claude Sonnet for quality (force_openai=True uses best available).
    Cost: ~$0.01-0.03 per call.
    """
    if len(transcript) < 50:
        logger.warning(f"Transcript too short for call {call_id}, skipping critique")
        return _empty_critique(call_id, "Transcript too short for analysis")

    prompt = CRITIQUE_PROMPT_TEMPLATE.format(
        lead_name=lead_name,
        company=company,
        lead_score=lead_score,
        tier=tier,
        original_message=original_message or "N/A",
        transcript=transcript[:6000],  # Limit to avoid token overflow
        duration_seconds=duration_seconds,
        call_id=call_id,
    )

    try:
        raw = await cascade_ai_call(
            prompt=prompt,
            system_prompt=CRITIQUE_SYSTEM,
            task_type="call_critique",
            max_tokens=2500,
            use_cache=False,
        )
        data = parse_json_response(raw)
        return _build_critique(call_id, data)

    except Exception as e:
        logger.error(f"Critique failed for call {call_id}: {e}")
        return _empty_critique(call_id, f"Critique error: {str(e)[:100]}")


def _build_critique(call_id: str, data: dict) -> CallCritique:
    scores_raw = data.get("scores", {})
    scores = CallScores(
        opening=_clamp(scores_raw.get("opening", 50)),
        discovery=_clamp(scores_raw.get("discovery", 50)),
        rapport=_clamp(scores_raw.get("rapport", 50)),
        objection_handling=_clamp(scores_raw.get("objection_handling", 50)),
        closing=_clamp(scores_raw.get("closing", 50)),
        naturalness=_clamp(scores_raw.get("naturalness", 50)),
        relevance=_clamp(scores_raw.get("relevance", 50)),
        overall=_clamp(scores_raw.get("overall", 50)),
    )

    pa = data.get("prospect_analysis", {})
    prospect = ProspectAnalysis(
        pain_points=pa.get("pain_points", []),
        buying_stage=pa.get("buying_stage", "unknown"),
        sentiment_overall=pa.get("sentiment_overall", "neutral"),
        budget_signals=pa.get("budget_signals", ""),
        objections_raised=pa.get("objections_raised", []),
    )

    improvements = []
    for imp in data.get("script_improvements", []):
        try:
            impact_str = imp.get("impact", "medium").lower()
            impact = ImprovementImpact(impact_str) if impact_str in ("high", "medium", "low") else ImprovementImpact.MEDIUM
            improvements.append(ScriptImprovement(
                category=imp.get("category", "general"),
                current_behavior=imp.get("current_behavior", ""),
                suggested_behavior=imp.get("suggested_behavior", ""),
                example_script=imp.get("example_script", ""),
                impact=impact,
            ))
        except Exception:
            pass

    return CallCritique(
        call_id=call_id,
        scores=scores,
        overall_score=scores.overall,
        one_line_summary=data.get("one_line_summary", ""),
        meeting_booked=bool(data.get("meeting_booked", False)),
        should_follow_up=bool(data.get("should_follow_up", True)),
        follow_up_strategy=data.get("follow_up_strategy", "email"),
        estimated_deal_probability=_clamp(data.get("estimated_deal_probability", 0)),
        prospect_analysis=prospect,
        action_items=data.get("action_items", []),
        script_improvements=improvements,
        coach_verdict=data.get("coach_verdict", ""),
    )


def _empty_critique(call_id: str, reason: str) -> CallCritique:
    return CallCritique(
        call_id=call_id,
        scores=CallScores(),
        overall_score=0,
        one_line_summary=reason,
        coach_verdict=reason,
    )


def _clamp(v, lo=0, hi=100) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return 0

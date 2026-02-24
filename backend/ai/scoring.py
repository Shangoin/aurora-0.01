"""
AURORA — AI Lead Scoring Engine
Uses few-shot CoT prompting → score 0-100, tier, reasoning
Cost: Gemini Flash (cheap) — ~$0.001 per lead
"""
import json
import logging
from models import LeadCreate, LeadScore, LeadTier
from ai.orchestrator import cascade_ai_call, parse_json_response

logger = logging.getLogger("aurora.scoring")

SCORING_SYSTEM = """You are an elite sales qualification expert. You score B2B leads for an AI automation company.

IDEAL CUSTOMER PROFILE (ICP):
- Title: Founder, CEO, Head of Sales, VP Sales, CRO
- Company size: 2-200 employees
- Lead volume: 50+ leads/month
- Pain: Manual outreach, low conversion, no follow-up system
- Budget signals: Paid tools, mentions scale challenges

SCORING RUBRIC (0-100):
- 80-100: Perfect ICP fit, clear pain, decision-maker, ready to buy  → tier: high
- 50-79:  Partial fit, some pain, possible decision-maker             → tier: medium
- 0-49:   Poor fit, no pain, not a decision-maker, bad signals        → tier: low

THINK STEP-BY-STEP before giving the final score."""

SCORING_FEW_SHOTS = """
Examples:

Lead 1: name=Sarah Chen, company=TechStartup Inc, title=CEO, volume=200+/month, message="We're burning 40 hours/week on manual outreach and our team hates it"
→ {"score": 88, "tier": "high", "reasoning": "CEO of growing company, 200+ leads, explicit pain point about manual work, high urgency language", "icp_fit": "Strong — decision maker, right volume, clear pain", "urgency": "High — 'burning' language, resource waste", "budget_signals": "Company already doing outreach, willing to invest"}

Lead 2: name=John Student, company=None, email=john@gmail.com, volume=1-10/month, message="just curious"
→ {"score": 12, "tier": "low", "reasoning": "No company, personal email, tiny volume, zero urgency", "icp_fit": "None — not a business", "urgency": "None", "budget_signals": "None"}

Lead 3: name=Maria Garcia, company=GrowthAgency, title=Head of Sales, volume=50-200/month, message="Looking for something to help with follow-ups"
→ {"score": 63, "tier": "medium", "reasoning": "Sales leader at agency, moderate volume, vague pain point, no specific urgency", "icp_fit": "Partial — right role, borderline volume", "urgency": "Medium", "budget_signals": "Process-oriented, likely has budget"}
"""


async def score_lead(lead: LeadCreate) -> LeadScore:
    """
    Score a lead using AI. Returns structured LeadScore.
    ~$0.001 per call via Gemini Flash.
    """
    user_prompt = f"""
{SCORING_FEW_SHOTS}

Now score this lead:
- Name: {lead.name}
- Email: {lead.email}
- Company: {lead.company or 'Not provided'}
- Phone: {'Provided' if lead.phone else 'Not provided'}
- Lead Volume: {lead.lead_volume or 'Not specified'}
- Message: {lead.message or 'No message'}

Think step by step, then return ONLY valid JSON:
{{
  "score": <0-100>,
  "tier": "<high|medium|low>",
  "reasoning": "<2-3 sentences>",
  "icp_fit": "<strong|partial|weak|none>",
  "urgency": "<high|medium|low|none>",
  "budget_signals": "<observed signals or 'None'>"
}}
"""

    try:
        raw = await cascade_ai_call(
            prompt=user_prompt,
            system_prompt=SCORING_SYSTEM,
            task_type="lead_scoring",
            max_tokens=500,
            use_cache=False,  # Never cache scoring — each lead is unique
        )
        data = parse_json_response(raw)

        score = max(0, min(100, int(data.get("score", 0))))
        tier_str = data.get("tier", "low").lower()
        tier = LeadTier(tier_str) if tier_str in LeadTier._value2member_map_ else LeadTier.LOW

        return LeadScore(
            score=score,
            tier=tier,
            reasoning=data.get("reasoning", ""),
            icp_fit=data.get("icp_fit", ""),
            urgency=data.get("urgency", ""),
            budget_signals=data.get("budget_signals", ""),
        )
    except Exception as e:
        logger.error(f"Lead scoring failed for {lead.email}: {e}")
        # Fail open — give a default low score rather than crashing
        return LeadScore(
            score=30,
            tier=LeadTier.LOW,
            reasoning=f"Scoring failed: {str(e)[:100]}",
            icp_fit="unknown",
            urgency="unknown",
            budget_signals="unknown",
        )


def should_call_immediately(score: LeadScore) -> bool:
    """High-tier leads get called within 5 minutes"""
    return score.tier == LeadTier.HIGH


def get_call_delay_minutes(score: LeadScore) -> int:
    """
    All leads get called immediately — no delay.
    Render free tier kills background tasks, so we call synchronously.
    """
    return 0

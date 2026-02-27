"""
AURORA 1.0 — AI Lead Scoring Engine
Few-shot Chain-of-Thought prompting → score 0-100, tier, ICP analysis.
Fail-open: returns score=30/LOW on any failure.
"""
import logging
from models import LeadCreate, LeadScore, LeadTier
from ai.orchestrator import cascade_ai_call, parse_json_response

logger = logging.getLogger("aurora.scoring")

# ─── Tier → call delay mapping ────────────────────────────────────────────────

_DELAY_MAP: dict[LeadTier, int] = {
    LeadTier.HIGH:   0,   # Speed-to-lead: immediate
    LeadTier.MEDIUM: 1,   # Follow up within 1 min
    LeadTier.LOW:    5,   # Low priority: 5 min
}

# ─── System prompt ────────────────────────────────────────────────────────────

SCORING_SYSTEM = """You are an elite sales qualification expert. You score B2B leads for an AI automation company.

IDEAL CUSTOMER PROFILE (ICP):
- Title: Founder, CEO, Head of Sales, VP Sales, CRO
- Company size: 2-200 employees
- Lead volume: 50+ leads/month
- Pain: Manual outreach, low conversion, no follow-up system
- Budget signals: Paid tools, mentions scale challenges

SCORING RUBRIC (0-100):
- 80-100: Perfect ICP fit, clear pain, decision-maker, ready to buy  → tier: high,   recommended_delay_minutes: 0
- 50-79:  Partial fit, some pain, possible decision-maker            → tier: medium, recommended_delay_minutes: 1
- 0-49:   Poor fit, no pain, not a decision-maker, bad signals       → tier: low,    recommended_delay_minutes: 5

THINK STEP-BY-STEP before giving the final score.
Return ONLY valid JSON — no prose, no markdown fences."""

# ─── Few-shot examples ────────────────────────────────────────────────────────

_FEW_SHOTS = """\
EXAMPLE 1:
Lead: name=Sarah Chen, company=TechStartup Inc, title=CEO, volume=200+/month, message="We're burning 40 hours/week on manual outreach and our team hates it"
Reasoning: CEO of fast-growing company, 200+ leads/mo exceeds ICP threshold, explicit time-waste pain, high urgency language ("burning"), clear decision-maker.
Answer: {"score": 88, "tier": "high", "reasoning": "CEO of growing company, 200+ leads, explicit pain about manual work, high urgency language", "icp_fit": true, "urgency": "high", "budget_signals": ["manual outreach investment", "company scaling fast"], "recommended_delay_minutes": 0}

EXAMPLE 2:
Lead: name=John Student, company=None, email=john@gmail.com, volume=1-10/month, message="just curious"
Reasoning: No company, personal email, trivial volume, zero urgency. Not a business contact.
Answer: {"score": 12, "tier": "low", "reasoning": "No company, personal email, tiny volume, zero urgency", "icp_fit": false, "urgency": "none", "budget_signals": [], "recommended_delay_minutes": 5}

EXAMPLE 3:
Lead: name=Maria Garcia, company=GrowthAgency, title=Head of Sales, volume=50-200/month, message="Looking for something to help with follow-ups"
Reasoning: Sales leader at agency, borderline volume, vague pain point, no specific urgency. Partial ICP fit.
Answer: {"score": 63, "tier": "medium", "reasoning": "Sales leader at agency, moderate volume, vague pain point, no specific urgency", "icp_fit": true, "urgency": "medium", "budget_signals": ["process-oriented, likely has budget"], "recommended_delay_minutes": 1}
"""

# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_scoring_prompt(lead: LeadCreate) -> str:
    """Build the few-shot CoT user prompt for a given lead."""
    return (
        f"{_FEW_SHOTS}\n"
        f"Now score this lead:\n"
        f"- Name: {lead.name}\n"
        f"- Email: {lead.email}\n"
        f"- Company: {lead.company or 'Not provided'}\n"
        f"- Phone: {'Provided' if lead.phone else 'Not provided'}\n"
        f"- Lead Volume: {lead.lead_volume or 'Not specified'}\n"
        f"- Message: {lead.message or 'No message'}\n\n"
        "Think step by step, then return ONLY valid JSON:\n"
        "{\n"
        '  "score": <0-100>,\n'
        '  "tier": "<high|medium|low>",\n'
        '  "reasoning": "<2-3 sentences>",\n'
        '  "icp_fit": <true|false>,\n'
        '  "urgency": "<high|medium|low|none>",\n'
        '  "budget_signals": ["<signal1>", ...],\n'
        '  "recommended_delay_minutes": <0|1|5>\n'
        "}"
    )

# ─── Main scoring function ────────────────────────────────────────────────────

async def score_lead(lead: LeadCreate) -> LeadScore:
    """
    Score a lead using the 6-LLM cascade.
    ~$0.001 per call via Gemini Flash (primary).
    Fail-open: returns score=30 / LOW on any exception.
    """
    try:
        raw = await cascade_ai_call(
            prompt=_build_scoring_prompt(lead),
            system_prompt=SCORING_SYSTEM,
            task_type="lead_scoring",
            max_tokens=500,
            use_cache=False,  # Every lead is unique — never cache
        )
        data = parse_json_response(raw)

        # Score: clamp 0-100
        score = max(0, min(100, int(data.get("score", 30))))

        # Tier: map string → enum, default LOW
        tier_str = str(data.get("tier", "low")).lower()
        try:
            tier = LeadTier(tier_str)
        except ValueError:
            tier = LeadTier.LOW

        # icp_fit: AI returns JSON bool; guard against string values too
        raw_icp = data.get("icp_fit", False)
        if isinstance(raw_icp, bool):
            icp_fit = raw_icp
        else:
            icp_fit = str(raw_icp).lower() not in ("false", "none", "0", "", "weak", "no")

        # budget_signals: expect list, tolerate string
        raw_bs = data.get("budget_signals", [])
        if isinstance(raw_bs, list):
            budget_signals: list[str] = [str(s) for s in raw_bs]
        else:
            budget_signals = [str(raw_bs)] if raw_bs else []

        # Delay is always controlled by tier — never trust AI's suggestion
        delay = _DELAY_MAP[tier]

        return LeadScore(
            score=score,
            tier=tier,
            reasoning=str(data.get("reasoning", "")),
            icp_fit=icp_fit,
            urgency=str(data.get("urgency", "")),
            budget_signals=budget_signals,
            recommended_delay_minutes=delay,
        )

    except Exception as e:
        logger.error(f"Lead scoring failed for {lead.email}: {e}")
        # Fail-open: store lead and flag for manual review rather than crashing
        return LeadScore(
            score=30,
            tier=LeadTier.LOW,
            reasoning=f"Scoring unavailable: {str(e)[:100]}",
            icp_fit=False,
            urgency="unknown",
            budget_signals=[],
            recommended_delay_minutes=5,
        )

# ─── Utility helpers ──────────────────────────────────────────────────────────

def should_call_immediately(score: LeadScore) -> bool:
    """True for high-tier leads — call immediately (0 min delay)."""
    return score.tier == LeadTier.HIGH


def get_call_delay_minutes(score: LeadScore) -> int:
    """Return recommended call delay in minutes based on tier."""
    return _DELAY_MAP.get(score.tier, 5)

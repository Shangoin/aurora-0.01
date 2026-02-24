"""
AURORA 0.01% — Pydantic Models
All request/response shapes and DB models
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Any
from enum import Enum
from datetime import datetime


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class LeadTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNSCORED = "unscored"


class LeadStatus(str, Enum):
    NEW = "new"
    CALL_INITIATED = "call_initiated"
    CALL_COMPLETED = "call_completed"
    MEETING_BOOKED = "meeting_booked"
    FOLLOW_UP_NEEDED = "follow_up_needed"
    NURTURE_QUEUE = "nurture_queue"
    CLOSED_LOST = "closed_lost"
    NOT_ACTIVE = "not_active"


class ImprovementImpact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ImprovementStatus(str, Enum):
    PENDING = "pending_review"
    APPLIED = "applied"
    REJECTED = "rejected"


# ─────────────────────────────────────────────
# LEAD MODELS
# ─────────────────────────────────────────────

class LeadCreate(BaseModel):
    """Inbound form submission from landing page"""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    lead_volume: Optional[str] = None
    message: Optional[str] = None

    @validator("phone")
    def validate_phone(cls, v):
        if v:
            # Remove spaces/dashes and check basic format
            cleaned = v.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            if len(cleaned) < 7:
                raise ValueError("Phone number too short")
        return v


class LeadScore(BaseModel):
    """AI scoring result"""
    score: int = Field(..., ge=0, le=100)
    tier: LeadTier
    reasoning: str
    icp_fit: str
    urgency: str
    budget_signals: str


class LeadResponse(BaseModel):
    """API response for lead creation"""
    id: str
    status: str
    score: int
    tier: str
    message: str


# ─────────────────────────────────────────────
# CALL / CRITIQUE MODELS
# ─────────────────────────────────────────────

class CallScores(BaseModel):
    opening: int = Field(0, ge=0, le=100)
    discovery: int = Field(0, ge=0, le=100)
    rapport: int = Field(0, ge=0, le=100)
    objection_handling: int = Field(0, ge=0, le=100)
    closing: int = Field(0, ge=0, le=100)
    naturalness: int = Field(0, ge=0, le=100)
    relevance: int = Field(0, ge=0, le=100)
    overall: int = Field(0, ge=0, le=100)


class ScriptImprovement(BaseModel):
    category: str
    current_behavior: str
    suggested_behavior: str
    example_script: str
    impact: ImprovementImpact


class ProspectAnalysis(BaseModel):
    pain_points: List[str] = []
    buying_stage: str = "unknown"
    sentiment_overall: str = "neutral"
    budget_signals: str = ""
    objections_raised: List[str] = []


class CallCritique(BaseModel):
    """Full critique from Claude"""
    call_id: str
    scores: CallScores
    overall_score: int
    one_line_summary: str
    meeting_booked: bool = False
    should_follow_up: bool = True
    follow_up_strategy: str = ""
    estimated_deal_probability: int = 0
    prospect_analysis: ProspectAnalysis
    action_items: List[str] = []
    script_improvements: List[ScriptImprovement] = []
    coach_verdict: str = ""


class VapiWebhookPayload(BaseModel):
    """Inbound Vapi webhook event"""
    message: Optional[dict] = None
    call: Optional[dict] = None

    class Config:
        extra = "allow"


# ─────────────────────────────────────────────
# SELF-IMPROVEMENT MODELS
# ─────────────────────────────────────────────

class PatternAnalysis(BaseModel):
    issue: str
    frequency: int
    impact: str
    example_from_calls: str


class PromptUpdate(BaseModel):
    patterns: List[PatternAnalysis]
    updated_system_prompt: str
    changelog: str
    expected_improvement_areas: List[str]


# ─────────────────────────────────────────────
# DASHBOARD / STATS MODELS
# ─────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_leads: int = 0
    calls_made: int = 0
    meetings_booked: int = 0
    avg_call_score: float = 0.0
    conversion_rate: float = 0.0
    total_cost_usd: float = 0.0
    pending_improvements: int = 0
    active_prompt_version: int = 1

"""
AURORA — Lead Ingestion API
POST /api/lead  — Receive lead, score it, trigger Vapi call
"""
import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from models import LeadCreate, LeadResponse
from ai.scoring import score_lead, get_call_delay_minutes
from ai.improvement import trigger_call
from db.supabase import upsert_lead, update_lead_status, log_event

router = APIRouter(prefix="/api", tags=["leads"])
logger = logging.getLogger("aurora.leads")


@router.post("/lead", response_model=LeadResponse)
async def create_lead(lead: LeadCreate, background_tasks: BackgroundTasks):
    """
    Main inbound endpoint. Called by Next.js landing page.
    
    Flow:
    1. Validate & deduplicate lead
    2. Store in Supabase
    3. Score with AI (Gemini Flash — cheap)
    4. Trigger Vapi call based on tier delay
    """
    logger.info(f"Lead received: {lead.email}")

    # 1. Score the lead with AI
    score = await score_lead(lead)

    # 2. Upsert to Supabase
    lead_data = {
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company,
        "lead_volume": lead.lead_volume,
        "message": lead.message,
        "score": score.score,
        "tier": score.tier.value,
        "score_reasoning": score.reasoning,
        "status": "new",
    }

    stored = await upsert_lead(lead_data)
    lead_id = stored.get("id", "unknown")

    # 3. Audit log
    await log_event(
        event_type="lead_scored",
        entity_id=lead.email,
        entity_type="lead",
        payload={"score": score.score, "tier": score.tier.value, "reasoning": score.reasoning},
    )

    # 4. Queue call in background (delayed by tier)
    delay_minutes = get_call_delay_minutes(score)
    background_tasks.add_task(
        _delayed_call,
        lead=lead,
        lead_score_data=score,
        delay_minutes=delay_minutes,
    )

    return LeadResponse(
        id=lead_id,
        status="received",
        score=score.score,
        tier=score.tier.value,
        message=f"Thanks {lead.name}! We'll be in touch shortly.",
    )


async def _delayed_call(lead: LeadCreate, lead_score_data, delay_minutes: int):
    """Background task: wait N minutes then trigger Vapi call"""
    if delay_minutes > 0:
        await asyncio.sleep(delay_minutes * 60)

    if not lead.phone:
        logger.info(f"No phone for {lead.email} — skipping call, queuing email follow-up")
        await update_lead_status(lead.email, {"status": "follow_up_needed"})
        return

    # Update status to call_initiated
    await update_lead_status(lead.email, {"status": "call_initiated"})

    call_id = await trigger_call(
        lead_email=lead.email,
        lead_name=lead.name,
        phone=lead.phone,
        lead_context={
            "company": lead.company,
            "lead_volume": lead.lead_volume,
            "message": lead.message,
            "score": lead_score_data.score,
            "tier": lead_score_data.tier.value,
        },
    )

    if call_id:
        await log_event(
            event_type="call_initiated",
            entity_id=lead.email,
            entity_type="lead",
            payload={"call_id": call_id, "delay_minutes": delay_minutes},
        )
    else:
        # Vapi not configured — fall back to follow-up status
        await update_lead_status(lead.email, {"status": "follow_up_needed"})

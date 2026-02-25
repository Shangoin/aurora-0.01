"""
AURORA 1.0 - Lead Ingestion API
POST /api/lead - Receive lead, score with AI, enrich via Serper, persist, trigger Vapi call.

Flow (synchronous, before response is sent):
  1. score_lead()         - 6-LLM cascade; fail-open to score=30/LOW
  1b. enrich_lead_score() - Serper company lookup; adjusts score + ICP signals; fail-open
  2. upsert_lead()        - idempotent upsert into Supabase leads table
  3. log_event()          - audit trail entry (includes enrichment delta)

Flow (background, after response is returned to client):
  4. trigger_call() - Vapi outbound call, delayed by recommended_delay_minutes
                      HIGH->5 min  MEDIUM->15 min  LOW->60 min
                      No-phone leads: status set to follow_up_needed + log_event
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks
from models import LeadCreate, LeadResponse, LeadScore
from ai.scoring import score_lead
from ai.enrichment import enrich_lead_score
from ai.improvement import trigger_call
from db.supabase import upsert_lead, update_lead_status, log_event

router = APIRouter(prefix="/api", tags=["leads"])
logger = logging.getLogger("aurora.leads")


@router.post("/lead", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate, background_tasks: BackgroundTasks):
    """
    Main inbound endpoint — called by the Next.js landing page.

    Returns immediately after scoring + persisting.
    The Vapi call fires in the background after the tier-appropriate delay.
    """
    logger.info("Lead received: %s", lead.email)

    # -- 1. Score (AI cascade) ------------------------------------------------
    initial_score = await score_lead(lead)
    logger.info(
        "Lead %s initial score: %d (%s)",
        lead.email, initial_score.score, initial_score.tier.value,
    )

    # -- 1b. Enrich score with Serper company signals (fail-open) ------------
    score, enrichment = await enrich_lead_score(lead, initial_score)
    if enrichment.found:
        logger.info(
            "Lead %s enriched score: %d (%s) | linkedin=%s funding=%s employees=%s",
            lead.email, score.score, score.tier.value,
            enrichment.has_linkedin, enrichment.has_funding, enrichment.employee_range,
        )

    # -- 2. Upsert to Supabase -----------------------------------------------
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
        "icp_fit": score.icp_fit,
        "budget_signals": score.budget_signals,
        "status": "new",
        "enrichment_signals": enrichment.to_dict(),
    }
    stored = await upsert_lead(lead_data)
    lead_id = (stored or {}).get("id", "unknown")

    # -- 3. Audit log --------------------------------------------------------
    await log_event(
        event_type="lead_scored",
        entity_id=lead.email,
        entity_type="lead",
        payload={
            "initial_score": initial_score.score,
            "initial_tier": initial_score.tier.value,
            "enriched_score": score.score,
            "enriched_tier": score.tier.value,
            "score_delta": score.score - initial_score.score,
            "reasoning": score.reasoning,
            "icp_fit": score.icp_fit,
            "recommended_delay_minutes": score.recommended_delay_minutes,
            "serper_signals": enrichment.to_dict(),
        },
    )

    # ── 4. Schedule call / no-phone fallback (background) ─────────────────────
    if lead.phone:
        background_tasks.add_task(_fire_call, lead=lead, score=score)
    else:
        logger.info("No phone for %s — queuing nurture follow-up", lead.email)
        background_tasks.add_task(_mark_no_phone, lead_email=lead.email)

    return LeadResponse(
        id=lead_id,
        status="received",
        score=score.score,
        tier=score.tier,
        message=f"Thanks {lead.name}! Our team will reach out shortly.",
    )


# ── Background helpers ────────────────────────────────────────────────────────

async def _fire_call(lead: LeadCreate, score: LeadScore) -> None:
    """Wait recommended_delay_minutes then trigger the Vapi outbound call."""
    delay = score.recommended_delay_minutes
    if delay > 0:
        logger.info(
            "Delaying call for %s by %d min (tier=%s)",
            lead.email, delay, score.tier.value,
        )
        await asyncio.sleep(delay * 60)

    await update_lead_status(lead.email, {"status": "call_initiated"})

    call_id = await trigger_call(
        lead_email=lead.email,
        lead_name=lead.name,
        phone=lead.phone,
        lead_context={
            "company": lead.company,
            "lead_volume": lead.lead_volume,
            "message": lead.message,
            "score": score.score,
            "tier": score.tier.value,
            "icp_fit": score.icp_fit,
            "budget_signals": score.budget_signals,
        },
    )

    if call_id:
        logger.info("Call initiated for %s (call_id=%s)", lead.email, call_id)
        await log_event(
            event_type="call_initiated",
            entity_id=lead.email,
            entity_type="lead",
            payload={
                "call_id": call_id,
                "delay_minutes": delay,
                "tier": score.tier.value,
            },
        )
    else:
        # Vapi not configured or number routing failed → fall back
        logger.warning("trigger_call returned None for %s — falling back to follow_up", lead.email)
        await update_lead_status(lead.email, {"status": "follow_up_needed"})
        await log_event(
            event_type="call_failed",
            entity_id=lead.email,
            entity_type="lead",
            payload={"reason": "trigger_call returned None", "tier": score.tier.value},
        )


async def _mark_no_phone(lead_email: str) -> None:
    """Flag leads that submitted without a phone number for nurture follow-up."""
    await update_lead_status(lead_email, {"status": "follow_up_needed"})
    await log_event(
        event_type="no_phone_lead",
        entity_id=lead_email,
        entity_type="lead",
        payload={"reason": "lead submitted without phone number"},
    )

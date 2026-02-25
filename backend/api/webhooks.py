"""
AURORA — Vapi Webhook Receiver
POST /webhooks/vapi  — Receives call events from Vapi
Handles: call.ended → deep critique → store → self-improvement queue
"""
import os
import logging
from fastapi import APIRouter, Request, HTTPException
from ai.critique import critique_call
from ai.improvement import run_improvement_cycle
from ai.mars import MARS_CYCLE_THRESHOLD
from db.supabase import (
    insert_call, update_lead_status, insert_improvement,
    get_calls_since, log_event
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("aurora.webhooks")


@router.post("/vapi")
async def vapi_webhook(request: Request):
    """
    Vapi posts call events here.
    We handle:
    - call.ended (with transcript) → run critique, store results
    - call.started → update lead status
    """
    # Optional webhook secret verification
    secret = os.environ.get("WEBHOOK_SECRET")
    if secret:
        incoming = request.headers.get("X-Vapi-Secret") or request.headers.get("X-Aurora-Secret")
        if incoming != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    event_type = payload.get("message", {}).get("type") or payload.get("type", "unknown")
    logger.info(f"Vapi event: {event_type}")

    if event_type == "end-of-call-report" or event_type == "call.ended":
        await _handle_call_ended(payload)
        return {"status": "processed"}
    elif event_type == "call-started":
        await _handle_call_started(payload)
        return {"status": "acknowledged"}
    elif event_type == "status-update":
        return {"status": "acknowledged"}
    else:
        logger.debug(f"Unhandled Vapi event: {event_type}")
        return {"status": "ignored"}


async def _handle_call_started(payload: dict):
    msg = payload.get("message", payload)
    lead_email = msg.get("metadata", {}).get("lead_email")
    if lead_email:
        await update_lead_status(lead_email, {"status": "call_initiated"})


async def _handle_call_ended(payload: dict):
    msg = payload.get("message", payload)

    # Extract call data
    call_id = msg.get("callId") or msg.get("id") or "unknown"
    transcript = msg.get("transcript") or ""
    recording_url = msg.get("recordingUrl") or ""
    duration = int(msg.get("durationSeconds") or msg.get("duration") or 0)
    cost = float(msg.get("cost") or 0)
    ended_reason = msg.get("endedReason") or "unknown"
    metadata = msg.get("metadata") or {}
    summary = msg.get("summary") or ""

    lead_email = metadata.get("lead_email") or ""
    lead_score = int(metadata.get("lead_score") or 0)
    lead_tier = metadata.get("lead_tier") or "unknown"
    geo_region = metadata.get("geo_region") or "global"

    logger.info(f"Call ended: {call_id}, duration={duration}s, lead={lead_email}, geo={geo_region}")

    # ── Run critique ──────────────────────────────────────────────────────────
    critique = await critique_call(
        transcript=transcript,
        call_id=call_id,
        lead_name=metadata.get("lead_name", "Unknown"),
        company=metadata.get("company", "Unknown"),
        lead_score=lead_score,
        tier=lead_tier,
        original_message=metadata.get("pain_hint", ""),
        duration_seconds=duration,
    )

    # ── Store call record in Supabase ─────────────────────────────────────────
    call_record = {
        "call_id": call_id,
        "lead_email": lead_email or None,
        "transcript": transcript,
        "recording_url": recording_url,
        "duration_seconds": duration,
        "cost_usd": cost,
        "ended_reason": ended_reason,
        "overall_score": critique.overall_score,
        "opening_score": critique.scores.opening,
        "discovery_score": critique.scores.discovery,
        "rapport_score": critique.scores.rapport,
        "objection_score": critique.scores.objection_handling,
        "closing_score": critique.scores.closing,
        "naturalness_score": critique.scores.naturalness,
        "relevance_score": critique.scores.relevance,
        "pacing_score": critique.scores.pacing,
        "silence_score": critique.scores.silence_handling,
        "meeting_booked": critique.meeting_booked,
        "should_follow_up": critique.should_follow_up,
        "follow_up_strategy": critique.follow_up_strategy,
        "pain_points": [p for p in critique.prospect_analysis.pain_points],
        "action_items": critique.action_items,
        "script_improvements": [i.model_dump() for i in critique.script_improvements],
        "full_critique": critique.model_dump(),
        "one_line_summary": critique.one_line_summary,
        "sentiment": critique.prospect_analysis.sentiment_overall,
        "buying_stage": critique.prospect_analysis.buying_stage,
        "deal_probability": critique.estimated_deal_probability,
        "geo_region": geo_region,
    }
    await insert_call(call_record)

    # ── Update lead status based on outcome ───────────────────────────────────
    if lead_email:
        new_status = (
            "meeting_booked" if critique.meeting_booked
            else "follow_up_needed" if critique.should_follow_up
            else "closed_lost"
        )
        await update_lead_status(lead_email, {
            "status": new_status,
            "last_call_score": critique.overall_score,
            "deal_probability": critique.estimated_deal_probability,
            "pain_points": critique.prospect_analysis.pain_points,
            "buying_stage": critique.prospect_analysis.buying_stage,
        })

    # ── Trigger nurture sequence if no meeting booked ──────────────────────────
    if lead_email and not critique.meeting_booked:
        try:
            from nurture.agent import get_nurture_agent
            await get_nurture_agent().create_sequence(
                lead_email=lead_email,
                lead_name=metadata.get("lead_name", ""),
                lead_company=metadata.get("company", ""),
                lead_score=lead_score,
                phone=metadata.get("phone", ""),
                pain_points=critique.prospect_analysis.pain_points,
                call_summary=critique.one_line_summary,
                geo_region=geo_region,
                should_follow_up=critique.should_follow_up,
            )
            logger.info(f"Nurture sequence created for {lead_email}")
        except Exception as e:
            logger.error(f"Failed to create nurture sequence for {lead_email}: {e}")

    # ── Queue high-impact script improvements ────────────────────────────────
    for improvement in critique.script_improvements:
        if improvement.impact.value == "high":
            await insert_improvement({
                "improvement_type": improvement.category,
                "source_call_id": call_id,
                "current_behavior": improvement.current_behavior,
                "suggested_behavior": improvement.suggested_behavior,
                "example_script": improvement.example_script,
                "impact": improvement.impact.value,
                "status": "pending_review",
            })

    # ── Log audit event ───────────────────────────────────────────────────────
    await log_event(
        event_type="critique_completed",
        entity_id=call_id,
        entity_type="call",
        payload={
            "overall_score": critique.overall_score,
            "meeting_booked": critique.meeting_booked,
            "lead_email": lead_email,
        },
    )

    # ── Check if improvement cycle should run (every MARS_CYCLE_THRESHOLD calls) ──
    try:
        recent_calls = await get_calls_since(days=90)
        if len(recent_calls) >= MARS_CYCLE_THRESHOLD and len(recent_calls) % MARS_CYCLE_THRESHOLD == 0:
            logger.info(f"MARS trigger: {len(recent_calls)} calls — running improvement cycle")
            result = await run_improvement_cycle(n_calls=MARS_CYCLE_THRESHOLD)
            logger.info(f"Improvement cycle complete: {result}")
    except Exception as e:
        logger.error(f"Improvement cycle failed: {e}")

    logger.info(f"Call {call_id} processed: score={critique.overall_score}, meeting={critique.meeting_booked}")


# ─── Admin: Manual improvement trigger ────────────────────────────────────────

@router.post("/trigger-improvement")
async def manual_improvement(request: Request):
    """Admin endpoint to manually trigger an improvement cycle.
    Requires: X-Admin-Secret: <ADMIN_SECRET>
    """
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    incoming = request.headers.get("X-Admin-Secret", "")
    if not incoming or incoming != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await run_improvement_cycle()
    return result

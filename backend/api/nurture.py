"""
Aurora 1.0 — Nurture Sequence API Routes
Provides management endpoints for the lead nurture system.
"""
import logging
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from models import NurtureSequenceCreate, NurtureSequenceResponse
from db.supabase import (
    get_nurture_sequences_paginated,
    get_nurture_sequence_by_email,
    deactivate_nurture_sequences,
    get_supabase,
)

router = APIRouter(prefix="/api/nurture", tags=["nurture"])
logger = logging.getLogger("aurora.nurture")


# ─── List all sequences ────────────────────────────────────────────────────────

@router.get("/sequences")
async def list_sequences(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """List all nurture sequences with pagination."""
    sequences = await get_nurture_sequences_paginated(offset=offset, limit=limit)
    return {"sequences": sequences, "count": len(sequences), "offset": offset}


# ─── Get sequence for a lead ──────────────────────────────────────────────────

@router.get("/sequences/{email}")
async def get_sequence_by_email(email: str):
    """Get the most recent nurture sequence for a given lead email."""
    seq = await get_nurture_sequence_by_email(email)
    if not seq:
        raise HTTPException(status_code=404, detail=f"No nurture sequence found for {email}")
    return seq


# ─── Manually create a sequence ──────────────────────────────────────────────

@router.post("/sequences", status_code=201)
async def create_sequence(body: NurtureSequenceCreate, background_tasks: BackgroundTasks):
    """
    Manually trigger a nurture sequence for a lead.
    Useful for testing or re-enrolling a lead.
    """
    from nurture.agent import get_nurture_agent
    agent = get_nurture_agent()

    async def run():
        await agent.create_sequence(
            lead_email=body.lead_email,
            lead_name=body.lead_name or "",
            lead_company=body.lead_company or "",
            lead_score=body.lead_score,
            phone=body.phone or "",
            pain_points=body.pain_points,
            call_summary=body.call_summary or "",
            geo_region=body.geo_region,
            should_follow_up=body.should_follow_up,
        )

    background_tasks.add_task(run)
    return {"status": "queued", "lead_email": body.lead_email}


# ─── Pause a sequence ─────────────────────────────────────────────────────────

@router.post("/sequences/{sequence_id}/pause")
async def pause_sequence(sequence_id: str):
    """Pause an active nurture sequence by ID (sets is_active=False)."""
    sb = get_supabase()
    res = sb.table("nurture_sequences").update({"is_active": False}).eq("id", sequence_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Sequence {sequence_id} not found")
    return {"status": "paused", "id": sequence_id}


@router.post("/sequences/{sequence_id}/resume")
async def resume_sequence(sequence_id: str):
    """Resume a paused nurture sequence."""
    sb = get_supabase()
    res = sb.table("nurture_sequences").update({"is_active": True, "completed": False}).eq("id", sequence_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Sequence {sequence_id} not found")
    return {"status": "resumed", "id": sequence_id}


# ─── Delete / deactivate a sequence ──────────────────────────────────────────

@router.delete("/sequences/{sequence_id}")
async def delete_sequence(sequence_id: str):
    """Deactivate a nurture sequence (soft delete)."""
    sb = get_supabase()
    sb.table("nurture_sequences").update({"is_active": False, "completed": True}).eq("id", sequence_id).execute()
    return {"status": "deactivated", "id": sequence_id}


# ─── Stats endpoint ───────────────────────────────────────────────────────────

@router.get("/stats")
async def nurture_stats():
    """Summary statistics for the nurture pipeline."""
    sb = get_supabase()

    all_seqs = sb.table("nurture_sequences").select("sequence_type, is_active, completed").execute().data or []
    total = len(all_seqs)
    active = sum(1 for s in all_seqs if s.get("is_active") and not s.get("completed"))
    completed = sum(1 for s in all_seqs if s.get("completed"))
    by_type = {}
    for s in all_seqs:
        t = s.get("sequence_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total_sequences": total,
        "active": active,
        "completed": completed,
        "paused": total - active - completed,
        "by_type": by_type,
    }

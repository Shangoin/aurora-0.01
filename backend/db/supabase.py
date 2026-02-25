"""
AURORA 1.0 — Supabase database client and all DB operations.

All database access is centralised here. No direct Supabase client calls anywhere
else in the codebase — route everything through these helpers.

Client uses SUPABASE_SERVICE_KEY (service role) which bypasses Row Level Security
for backend writes. The anon key (SUPABASE_KEY) is reserved for the landing page.
"""
import os
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from supabase import create_client, Client

logger = logging.getLogger("aurora.db")


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """
    Return the cached Supabase client, creating it on first call.
    Uses SUPABASE_SERVICE_KEY to bypass RLS for all backend writes.
    The anon key (SUPABASE_KEY) is reserved for the landing page frontend.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]   # service role bypasses RLS
    return create_client(url, key)


# Alias used by tests that patch `db.supabase.get_supabase_client`
get_supabase_client = get_supabase


# ─── Leads ────────────────────────────────────────────────────────────────────

async def upsert_lead(data: dict) -> dict:
    sb = get_supabase()
    res = sb.table("leads").upsert(data, on_conflict="email").execute()
    return res.data[0] if res.data else {}


async def get_lead_by_email(email: str) -> dict | None:
    sb = get_supabase()
    res = sb.table("leads").select("*").eq("email", email).limit(1).execute()
    return res.data[0] if res.data else None


async def update_lead_status(email: str, updates: dict) -> dict:
    sb = get_supabase()
    res = sb.table("leads").update(updates).eq("email", email).execute()
    return res.data[0] if res.data else {}


# ─── Calls ────────────────────────────────────────────────────────────────────

async def insert_call(data: dict) -> dict:
    """
    Store a complete call record including all 10 critique scores:
    overall, opening, discovery, rapport, objection, closing,
    naturalness, relevance, pacing, silence_handling.
    """
    sb = get_supabase()
    res = sb.table("calls").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_recent_calls(limit: int = 25) -> list:
    """
    Return the most recent calls ordered by created_at DESC.
    Default limit matches the MARS improvement cycle threshold (25 calls).
    Pass a higher limit for dashboard or analytics queries.
    """
    sb = get_supabase()
    res = (
        sb.table("calls")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def get_calls_since(days: int = 7) -> list:
    """Return all calls from the last N days, ordered newest-first."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    sb = get_supabase()
    res = (
        sb.table("calls")
        .select("*")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

async def get_call_count() -> int:
    """
    Return the total number of call records.
    Used by the webhook handler for the MARS trigger condition:
        call_count % MARS_CYCLE_THRESHOLD == 0
    """
    sb = get_supabase()
    res = sb.table("calls").select("id", count="exact").execute()
    return res.count or 0

# ─── Improvements ─────────────────────────────────────────────────────────────

async def insert_improvement(data: dict) -> dict:
    sb = get_supabase()
    res = sb.table("agent_improvements").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_pending_improvements() -> list:
    sb = get_supabase()
    res = (
        sb.table("agent_improvements")
        .select("*")
        .eq("status", "pending_review")
        .order("impact", desc=False)   # high first
        .execute()
    )
    return res.data or []


async def mark_improvements_applied(ids: list[str]) -> None:
    """Bulk-mark a list of improvement IDs as applied after a MARS cycle completes."""
    if not ids:
        return
    sb = get_supabase()
    sb.table("agent_improvements").update({"status": "applied"}).in_("id", ids).execute()


# ─── Prompt Versions ──────────────────────────────────────────────────────────

async def get_active_prompt() -> dict | None:
    sb = get_supabase()
    res = (
        sb.table("prompt_versions")
        .select("*")
        .eq("is_active", True)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def insert_prompt_version(data: dict) -> dict:
    """
    Deactivate all current active prompt versions, then insert a new active one.
    Auto-increments the version number based on the current max.
    Only one prompt version should be active at any time.
    """
    sb = get_supabase()
    # Deactivate all currently-active versions
    sb.table("prompt_versions").update({"is_active": False}).eq("is_active", True).execute()
    # Determine next version number
    res = sb.table("prompt_versions").select("version").order("version", desc=True).limit(1).execute()
    next_v = (res.data[0]["version"] + 1) if res.data else 2
    data["version"] = next_v
    data["is_active"] = True
    res2 = sb.table("prompt_versions").insert(data).execute()
    return res2.data[0] if res2.data else {}


# ─── Audit Log ────────────────────────────────────────────────────────────────

async def log_event(event_type: str, entity_id: str, entity_type: str, payload: dict) -> None:
    """
    Append an immutable audit event. Insert-only — never updated or deleted.
    event_type: 'lead_scored' | 'call_initiated' | 'critique_run' | 'prompt_updated'
    entity_type: 'lead' | 'call' | 'prompt'
    """
    sb = get_supabase()
    sb.table("audit_log").insert({
        "event_type": event_type,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "payload": payload,
    }).execute()


# ─── MARS Lessons ─────────────────────────────────────────────────────────────────

async def insert_mars_lesson(data: dict) -> dict:
    """
    Store a MARS improvement cycle result.
    Schema: id, created_at, call_batch_start, call_batch_end, patterns_found,
            prompt_diff, avg_score_before, avg_score_after, mcts_nodes, was_applied.
    avg_score_after is backfilled later via backfill_mars_score_after().
    """
    sb = get_supabase()
    res = sb.table("mars_lessons").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_mars_lessons(limit: int = 20) -> list:
    """
    Fetch recent MARS lessons ordered newest-first (applied and unapplied).
    Used by the dashboard MARS viewer and the improvement cycle for context.
    """
    sb = get_supabase()
    res = (
        sb.table("mars_lessons")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def backfill_mars_score_after(lesson_id: str, avg_score_after: float) -> None:
    """
    Backfill avg_score_after on a completed MARS lesson once the next call batch
    finishes. Called at the start of each new improvement cycle to close out the
    previous lesson's measured-improvement field.
    """
    sb = get_supabase()
    sb.table("mars_lessons").update(
        {"avg_score_after": avg_score_after}
    ).eq("id", lesson_id).execute()


# ─── Nurture Sequences ────────────────────────────────────────────────────────

async def insert_nurture_sequence(data: dict) -> dict:
    """Create a new nurture sequence row. Caller should call deactivate_nurture_sequences() first."""
    sb = get_supabase()
    res = sb.table("nurture_sequences").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_active_nurture_sequences() -> list:
    """
    Return all non-completed, active nurture sequences.
    Called every 15 minutes by the APScheduler tick to advance pending steps.
    """
    sb = get_supabase()
    res = (
        sb.table("nurture_sequences")
        .select("*")
        .eq("is_active", True)
        .eq("completed", False)
        .execute()
    )
    return res.data or []


async def get_nurture_sequences_paginated(offset: int = 0, limit: int = 50) -> list:
    """Return nurture sequences with offset pagination for the API listing endpoint."""
    sb = get_supabase()
    res = (
        sb.table("nurture_sequences")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return res.data or []


async def get_nurture_sequence_by_email(email: str) -> dict | None:
    """Get the most recent nurture sequence for an email address."""
    sb = get_supabase()
    res = (
        sb.table("nurture_sequences")
        .select("*")
        .eq("lead_email", email)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def update_nurture_step(
    sequence_id: str,
    step_idx: int,
    status: str,
    result: str = "",
) -> dict:
    """
    Update the status/result of a specific step in a nurture sequence's JSONB
    steps array. Also advances current_step and records last_action_at.

    status: 'pending' | 'sent' | 'skipped' | 'failed'
    """
    sb = get_supabase()
    # Fetch current sequence
    seq_res = sb.table("nurture_sequences").select("steps").eq("id", sequence_id).limit(1).execute()
    if not seq_res.data:
        return {}
    steps = seq_res.data[0]["steps"]
    if 0 <= step_idx < len(steps):
        steps[step_idx]["status"] = status
        steps[step_idx]["result"] = result
    res = sb.table("nurture_sequences").update({
        "steps": steps,
        "current_step": step_idx,
        "last_action_at": datetime.utcnow().isoformat(),   # ISO string, not SQL "now()"
    }).eq("id", sequence_id).execute()
    return res.data[0] if res.data else {}


async def deactivate_nurture_sequences(email: str) -> None:
    """Cancel all active sequences for a lead before enrolling a new one."""
    sb = get_supabase()
    sb.table("nurture_sequences").update({"is_active": False}).eq("lead_email", email).execute()


async def mark_nurture_completed(sequence_id: str) -> None:
    """Mark a nurture sequence as fully completed (all steps sent or exhausted)."""
    sb = get_supabase()
    sb.table("nurture_sequences").update({
        "completed": True,
        "is_active": False,
    }).eq("id", sequence_id).execute()

"""
AURORA — Supabase DB client & helpers
"""
import os
from functools import lru_cache
from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]   # service role bypasses RLS
    return create_client(url, key)


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
    sb = get_supabase()
    res = sb.table("calls").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_recent_calls(limit: int = 50) -> list:
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
    from datetime import datetime, timedelta
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
    sb = get_supabase()
    # Deactivate all previous
    sb.table("prompt_versions").update({"is_active": False}).neq("version", 0).execute()
    # Get next version number
    res = sb.table("prompt_versions").select("version").order("version", desc=True).limit(1).execute()
    next_v = (res.data[0]["version"] + 1) if res.data else 2
    data["version"] = next_v
    data["is_active"] = True
    res2 = sb.table("prompt_versions").insert(data).execute()
    return res2.data[0] if res2.data else {}


# ─── Audit Log ────────────────────────────────────────────────────────────────

async def log_event(event_type: str, entity_id: str, entity_type: str, payload: dict) -> None:
    sb = get_supabase()
    sb.table("audit_log").insert({
        "event_type": event_type,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "payload": payload,
    }).execute()

"""
Aurora 1.0 - Model Context Protocol (MCP) Server
=================================================
Exposes Aurora's full pipeline as MCP tools so any MCP-compatible AI assistant
(Claude Desktop, Cursor, Copilot, custom agents) can drive the SDR system.

Transport: stdio (default) or SSE via --sse flag
Run:
    # stdio (for Claude Desktop / Cursor)
    python mcp_server.py

    # SSE (for browser-based clients or remote agents)
    python mcp_server.py --sse --port 8001

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "aurora-sdr": {
          "command": "python",
          "args": ["d:/AI Projects/Projects/Projects/aurora-0.01/backend/mcp_server.py"],
          "env": { "PYTHONPATH": "d:/AI Projects/Projects/Projects/aurora-0.01/backend" }
        }
      }
    }

Cursor MCP config (.cursor/mcp.json):
    {
      "mcpServers": {
        "aurora-sdr": {
          "command": "python",
          "args": ["backend/mcp_server.py"],
          "cwd": "d:/AI Projects/Projects/Projects/aurora-0.01"
        }
      }
    }

Available tools:
    score_and_enrich_lead       Score + Serper-enrich a prospect
    get_lead                    Fetch full lead record by email
    search_leads                Filter leads by tier / status / score range
    get_pipeline_stats          Current KPI summary (leads, calls, meetings, cost)
    list_recent_calls           Recent calls with scores and critique summaries
    get_call_detail             Full critique for a specific call_id
    get_nurture_sequence        Nurture sequence status for a lead
    enrol_lead_in_nurture       Manually start a nurture sequence for a lead
    pause_nurture_sequence      Pause an active sequence
    list_mars_lessons           Recent MARS improvement cycles
    get_active_prompt           Current live ARIA system prompt
    trigger_improvement_cycle   Manually fire the MARS improvement cycle
    health_check                System health + connectivity status

Available resources:
    aurora://stats              Live pipeline KPIs
    aurora://leads/recent       50 most recent leads
    aurora://prompt/active      Current ARIA prompt version
    aurora://health             System health check payload
"""
import os
import sys
import json
import logging
import asyncio
import argparse
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logger = logging.getLogger("aurora.mcp")

# ---------------------------------------------------------------------------
# Backend base URL - MCP server talks to the running Aurora FastAPI backend
# ---------------------------------------------------------------------------
BACKEND_URL = os.environ.get("AURORA_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")
_HTTP_TIMEOUT = 15

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="Aurora SDR",
    version="1.0.0",
    description=(
        "Shango Revenue Systems — Aurora 1.0 autonomous AI SDR. "
        "Score leads, retrieve pipeline analytics, manage nurture sequences, "
        "inspect call critiques, and trigger MARS self-improvement cycles."
    ),
)


# ---------------------------------------------------------------------------
# HTTP helpers (talks to the Aurora FastAPI backend)
# ---------------------------------------------------------------------------

async def _get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(f"{BACKEND_URL}{path}", params=params or {})
    r.raise_for_status()
    return r.json()


async def _post(path: str, body: dict, headers: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            f"{BACKEND_URL}{path}",
            json=body,
            headers=headers or {},
        )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Supabase direct helpers (for reads that have no REST endpoint)
# ---------------------------------------------------------------------------

def _get_supabase():
    """Return a Supabase client (lazy import so the module loads without the venv)."""
    from db.supabase import get_supabase
    return get_supabase()


# ---------------------------------------------------------------------------
# TOOLS - Lead management
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Score and Serper-enrich a prospect using Aurora's 6-LLM cascade + company lookup. "
        "Returns score (0-100), tier (high/medium/low), ICP fit, urgency, budget signals, "
        "and Serper company signals (employees, funding, LinkedIn). "
        "Does NOT trigger a Vapi call — use this for pre-qualification only."
    ),
)
async def score_and_enrich_lead(
    name: str,
    email: str,
    company: str = "",
    phone: str = "",
    lead_volume: str = "",
    message: str = "",
) -> dict:
    """
    Score and enrich a lead without triggering a call.

    Args:
        name: Prospect full name
        email: Prospect email address (used as unique key)
        company: Company name (improves scoring + enables Serper enrichment)
        phone: Phone number in E.164 format (optional for scoring)
        lead_volume: Monthly lead volume bracket, e.g. "50-200" or "200+"
        message: Prospect's message or pain description
    """
    from ai.scoring import score_lead
    from ai.enrichment import enrich_lead_score
    from models import LeadCreate

    lead = LeadCreate(
        name=name,
        email=email,
        phone=phone or None,
        company=company or None,
        lead_volume=lead_volume or None,
        message=message or None,
    )

    initial = await score_lead(lead)
    enriched, signals = await enrich_lead_score(lead, initial)

    return {
        "score": enriched.score,
        "tier": enriched.tier.value,
        "reasoning": enriched.reasoning,
        "icp_fit": enriched.icp_fit,
        "urgency": enriched.urgency,
        "budget_signals": enriched.budget_signals,
        "recommended_delay_minutes": enriched.recommended_delay_minutes,
        "initial_score": initial.score,
        "score_delta": enriched.score - initial.score,
        "enrichment": signals.to_dict(),
    }


@mcp.tool(
    description="Fetch a complete lead record from Supabase by email address.",
)
async def get_lead(email: str) -> dict:
    """
    Args:
        email: Lead email address (exact match)
    """
    from db.supabase import get_lead_by_email
    lead = await get_lead_by_email(email)
    if not lead:
        return {"error": f"Lead not found: {email}"}
    return lead


@mcp.tool(
    description=(
        "Search leads with optional filters. Returns list of matching leads "
        "ordered by score descending. "
        "All filters are optional — call with no args to get the 50 most recent leads."
    ),
)
async def search_leads(
    tier: str = "",
    status: str = "",
    min_score: int = 0,
    max_score: int = 100,
    limit: int = 20,
) -> list[dict]:
    """
    Args:
        tier: Filter by tier - "high", "medium", "low", or "unscored" (empty = all)
        status: Filter by status - "new", "call_initiated", "meeting_booked", etc (empty = all)
        min_score: Minimum score (0-100)
        max_score: Maximum score (0-100)
        limit: Max results to return (default 20, max 100)
    """
    sb = _get_supabase()
    query = sb.table("leads").select("*")

    if tier:
        query = query.eq("tier", tier.lower())
    if status:
        query = query.eq("status", status.lower())
    if min_score > 0:
        query = query.gte("score", min_score)
    if max_score < 100:
        query = query.lte("score", max_score)

    result = (
        query
        .order("score", desc=True)
        .limit(min(limit, 100))
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# TOOLS - Pipeline analytics
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Get current Aurora pipeline KPIs: total leads, calls made, meetings booked, "
        "average call score, conversion rate, total cost, and active prompt version."
    ),
)
async def get_pipeline_stats() -> dict:
    return await _get("/api/stats")


@mcp.tool(
    description="List recent Vapi calls with critique summary and scores.",
)
async def list_recent_calls(limit: int = 10) -> list[dict]:
    """
    Args:
        limit: Number of calls to return (default 10, max 50)
    """
    sb = _get_supabase()
    result = (
        sb.table("calls")
        .select(
            "call_id, lead_email, created_at, duration_seconds, overall_score, "
            "opening_score, discovery_score, rapport_score, objection_score, "
            "closing_score, naturalness_score, relevance_score, pacing_score, "
            "silence_handling_score, meeting_booked, follow_up_strategy, "
            "one_line_summary, sentiment, deal_probability, geo_region"
        )
        .order("created_at", desc=True)
        .limit(min(limit, 50))
        .execute()
    )
    return result.data or []


@mcp.tool(
    description=(
        "Get the full critique detail for a specific call, including all 9 scores, "
        "prospect analysis (pain points, buying stage, objections), "
        "action items, and script improvement suggestions."
    ),
)
async def get_call_detail(call_id: str) -> dict:
    """
    Args:
        call_id: Vapi call ID (e.g. "call_01abc...") or Aurora internal UUID
    """
    sb = _get_supabase()
    result = (
        sb.table("calls")
        .select("*")
        .eq("call_id", call_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        # Try by UUID
        result = (
            sb.table("calls")
            .select("*")
            .eq("id", call_id)
            .limit(1)
            .execute()
        )
    if not result.data:
        return {"error": f"Call not found: {call_id}"}
    return result.data[0]


# ---------------------------------------------------------------------------
# TOOLS - Nurture sequences
# ---------------------------------------------------------------------------

@mcp.tool(
    description="Get the nurture sequence status for a lead, including all steps and their execution state.",
)
async def get_nurture_sequence(email: str) -> dict:
    """
    Args:
        email: Lead email address
    """
    sb = _get_supabase()
    result = (
        sb.table("nurture_sequences")
        .select("*")
        .eq("lead_email", email)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"error": f"No nurture sequence found for: {email}"}
    return result.data[0]


@mcp.tool(
    description=(
        "Manually enrol a lead in a nurture sequence. "
        "Sequence type is auto-selected based on score unless overridden: "
        "score>=60 -> hot_nurture, 40-59 -> warm_nurture, <40 -> cold_nurture."
    ),
)
async def enrol_lead_in_nurture(
    email: str,
    sequence_type: str = "",
    call_summary: str = "",
) -> dict:
    """
    Args:
        email: Lead email address (must exist in leads table)
        sequence_type: Override sequence - "hot_nurture", "warm_nurture", "cold_nurture"
                       (empty = auto-select from lead score)
        call_summary: Optional one-line call summary to include in nurture context
    """
    body: dict = {"lead_email": email}
    if sequence_type:
        body["sequence_type"] = sequence_type
    if call_summary:
        body["call_summary"] = call_summary
    return await _post("/api/nurture/sequences", body)


@mcp.tool(
    description="Pause an active nurture sequence so no further steps fire.",
)
async def pause_nurture_sequence(sequence_id: str) -> dict:
    """
    Args:
        sequence_id: UUID of the nurture_sequences row
    """
    return await _post(f"/api/nurture/sequences/{sequence_id}/pause", {})


# ---------------------------------------------------------------------------
# TOOLS - MARS / self-improvement
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List recent MARS self-improvement cycles. Each cycle shows patterns found, "
        "prompt changelog, average score before/after, and whether the patch was deployed."
    ),
)
async def list_mars_lessons(limit: int = 5) -> list[dict]:
    """
    Args:
        limit: Number of lessons to return (default 5, max 25)
    """
    sb = _get_supabase()
    result = (
        sb.table("mars_lessons")
        .select("*")
        .order("created_at", desc=True)
        .limit(min(limit, 25))
        .execute()
    )
    return result.data or []


@mcp.tool(
    description="Get the currently active ARIA system prompt — the live version deployed to Vapi.",
)
async def get_active_prompt() -> dict:
    """Returns version number, prompt text, changelog, and performance stats."""
    sb = _get_supabase()
    result = (
        sb.table("prompt_versions")
        .select("*")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"error": "No active prompt found in prompt_versions table"}
    return result.data[0]


@mcp.tool(
    description=(
        "Manually trigger the MARS self-improvement cycle. "
        "Analyzes last 25 calls, runs MCTS planner, generates new prompt, "
        "patches Vapi assistant, and stores the new prompt version in Supabase. "
        "Requires ADMIN_SECRET to be set in the server's env."
    ),
)
async def trigger_improvement_cycle() -> dict:
    """
    Fires POST /webhooks/trigger-improvement with X-Admin-Secret header.
    Returns the improvement result including new_version, patterns_found, changelog.
    """
    if not ADMIN_SECRET:
        return {
            "error": "ADMIN_SECRET not set in MCP server environment. "
                     "Set ADMIN_SECRET= in backend/.env and restart the MCP server."
        }
    return await _post(
        "/webhooks/trigger-improvement",
        {},
        headers={"X-Admin-Secret": ADMIN_SECRET},
    )


# ---------------------------------------------------------------------------
# TOOLS - System
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Check Aurora system health: database connectivity, AI cascade provider status, "
        "Vapi geo-number availability, and nurture scheduler state."
    ),
)
async def health_check() -> dict:
    """Returns the full /health response with status 'ok' or 'degraded'."""
    return await _get("/health")


# ---------------------------------------------------------------------------
# RESOURCES
# ---------------------------------------------------------------------------

@mcp.resource("aurora://stats")
async def resource_stats() -> str:
    """Live Aurora pipeline KPIs as formatted JSON."""
    data = await _get("/api/stats")
    return json.dumps(data, indent=2)


@mcp.resource("aurora://leads/recent")
async def resource_recent_leads() -> str:
    """The 50 most recent leads ordered by creation date, formatted as JSON."""
    sb = _get_supabase()
    result = (
        sb.table("leads")
        .select("name, email, company, score, tier, status, created_at, enrichment_signals")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return json.dumps(result.data or [], indent=2)


@mcp.resource("aurora://prompt/active")
async def resource_active_prompt() -> str:
    """The currently active ARIA system prompt deployed to Vapi."""
    sb = _get_supabase()
    result = (
        sb.table("prompt_versions")
        .select("version, prompt_text, changelog, based_on_calls, avg_score_before, avg_score_after, created_at")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return "No active prompt found."
    row = result.data[0]
    return (
        f"# ARIA Prompt — Version {row['version']}\n"
        f"# Based on {row.get('based_on_calls', 0)} calls\n"
        f"# Avg score before: {row.get('avg_score_before', 'N/A')} | after: {row.get('avg_score_after', 'N/A')}\n"
        f"# Changelog: {row.get('changelog', 'N/A')}\n"
        f"# Created: {row.get('created_at', 'N/A')}\n"
        f"\n{row['prompt_text']}"
    )


@mcp.resource("aurora://health")
async def resource_health() -> str:
    """Aurora system health payload."""
    data = await _get("/health")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aurora MCP Server")
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Run with SSE transport instead of stdio (for browser/remote clients)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for SSE transport (default: 8001)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE transport (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    if args.sse:
        print(f"[Aurora MCP] Starting SSE server on http://{args.host}:{args.port}", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        # stdio transport — default for Claude Desktop / Cursor
        mcp.run(transport="stdio")

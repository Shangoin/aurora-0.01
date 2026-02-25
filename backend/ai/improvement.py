"""
AURORA 1.0 — MARS Reflective Self-Improvement Loop
Every 25 calls: MCTS plans improvements → diff-based prompt edits → lessons stored in memory DB.
Budget-aware reward function: Reward = score_improvement / compute_cost
Geo-routing: 4 Vapi phone numbers (IN/US/UK/Global) based on lead country code.
"""
import os
import logging
import httpx
import time
from datetime import datetime
from models import PromptUpdate, PatternAnalysis, MARSLesson
from ai.orchestrator import cascade_ai_call, parse_json_response
from ai.mars import (
    MCTSNode as _MCTSTreeNode,  # dataclass — internal planning
    run_mcts_planner as _run_mcts_planner,
    MARS_CYCLE_THRESHOLD,
    MARS_BUDGET_MINUTES,
)
from db.supabase import (
    get_recent_calls, get_pending_improvements, get_active_prompt,
    insert_prompt_version, mark_improvements_applied,
    insert_mars_lesson, get_mars_lessons,
)

logger = logging.getLogger("aurora.improvement")

# MARS_CYCLE_THRESHOLD imported from ai.mars (canonical source)

# ─── Geo-routing phone map ────────────────────────────────────────────────────
# Maps country code prefix → Vapi phone number ID env var
# Import 4 Twilio numbers into Vapi and set these env vars

GEO_PHONE_MAP = {
    "+91": "VAPI_PHONE_NUMBER_ID_IN",    # India  — Mumbai local CID
    "+1":  "VAPI_PHONE_NUMBER_ID_US",    # US/CA  — SF/NY local CID
    "+44": "VAPI_PHONE_NUMBER_ID_UK",    # UK     — London local CID
}
# All other country codes fall through to _GLOBAL then to bare ID as final safety net
_GEO_DEFAULT_ENV = "VAPI_PHONE_NUMBER_ID_GLOBAL"  # Fallback for all other regions
_GEO_BARE_FALLBACK = "VAPI_PHONE_NUMBER_ID"       # Legacy absolute last resort


def _get_phone_number_id(phone: str) -> str | None:
    """
    Return the correct Vapi phone number ID based on the lead's country code.
    Priority: IN (+91) → US (+1) → UK (+44) → GLOBAL (all others) → bare ID.
    Local caller ID → 40%+ answer rate vs generic number.
    """
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    for prefix, env_key in GEO_PHONE_MAP.items():
        if phone_clean.startswith(prefix):
            val = os.environ.get(env_key)
            if val:
                logger.info(f"Geo-routing: {prefix} → {env_key}")
                return val
    # All unrecognised country codes route to GLOBAL, then bare fallback
    return os.environ.get(_GEO_DEFAULT_ENV) or os.environ.get(_GEO_BARE_FALLBACK)


def _detect_geo_region(phone: str) -> str:
    """Return human-readable geo region for analytics."""
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("+91"):
        return "india"
    if phone_clean.startswith("+1"):
        return "us"
    if phone_clean.startswith("+44"):
        return "uk"
    return "global"


# ─── MCTS Budget Planner — delegated to ai.mars ──────────────────────────────
# run_mcts_planner() imported from ai.mars; use it directly in the cycle below.

# ─── Prompts ──────────────────────────────────────────────────────────────────

MARS_SYSTEM = """You are a VP of Sales Operations specializing in AI SDR optimization.
You use MCTS-style analysis: evaluate improvement candidates by expected impact vs compute cost.

Rules:
1. Only fix patterns appearing in 3+ calls — prevent overfitting  
2. Produce MODULAR edits: specify which section of the prompt changed (opening/discovery/objection/closing/persona)
3. Each module change must include: before/after text + reason + expected score delta
4. The updated_system_prompt must be COMPLETE and deployable (not a diff)
5. Extract LESSONS for future iterations — these become long-term memory
6. Changelog must be specific: "opening score 58→72: Added permission micro-yes before pitch"
"""

MARS_PROMPT = """Analyze {n_calls} call critiques for MARS reflective improvement.

== CURRENT AGENT PROMPT ==
{current_prompt}

== PERFORMANCE STATS ==
Average overall score: {avg_score}/100
Previous cycle score: {prev_score}/100
Score distribution: {score_distribution}
Worst scoring dimensions: {worst_dimensions}

== CALL CRITIQUES (last {n_calls} calls) ==
{critique_summaries}

== MCTS RANKED IMPROVEMENTS (by reward efficiency) ==
{mcts_improvements}

== PENDING SCRIPT IMPROVEMENTS ==
{improvements_text}

== EXISTING MARS LESSONS (long-term memory) ==
{existing_lessons}

Your task:
1. Identify TOP 3 patterns (must appear in 3+ calls)
2. For each pattern, specify which prompt MODULE to edit
3. Write COMPLETE updated system prompt (minimum 600 words)
4. Extract 2-3 new LESSONS for the memory database
5. MCTS reward: estimate score delta for each module change

Return ONLY valid JSON:
{{
  "patterns": [
    {{
      "issue": "<specific problem>",
      "frequency": <call count>,
      "impact": "<high|medium|low>",
      "module": "<opening|discovery|objection|closing|naturalness|pacing|persona>",
      "example_from_calls": "<actual quote>",
      "expected_score_delta": <float>
    }}
  ],
  "module_changes": [
    {{
      "module": "<module_name>",
      "before": "<original section text>",
      "after": "<improved section text>",
      "reason": "<why this change>",
      "expected_delta": <score points expected>
    }}
  ],
  "updated_system_prompt": "<COMPLETE new prompt — must be >600 words>",
  "changelog": "<bullet list of specific changes with expected impact>",
  "expected_improvement_areas": ["<metric will improve from X to Y>"],
  "mars_lessons": [
    {{
      "lesson_type": "<pattern|objection|opening|insight|geo>",
      "content": "<actionable lesson for future iterations>",
      "source_calls": <int>,
      "avg_score_delta": <expected improvement>
    }}
  ]
}}"""


async def run_improvement_cycle(n_calls: int = MARS_CYCLE_THRESHOLD) -> dict:
    """
    MARS Reflective Improvement Cycle:
    1. Fetch recent calls + pending improvements
    2. Run MCTS budget planner — rank candidates by reward
    3. AI meta-analysis with MARS prompt
    4. Extract + store lessons to mars_lessons table (long-term memory)
    5. Push diff-based prompt to Vapi
    6. Store versioned prompt + mark improvements applied
    """
    logger.info(f"[MARS] Starting improvement cycle (last {n_calls} calls)...")
    t_start = time.monotonic()

    # 1. Gather data
    calls = await get_recent_calls(n_calls)
    improvements = await get_pending_improvements()
    current_prompt_row = await get_active_prompt()
    existing_lessons = await get_mars_lessons(limit=20)
    current_prompt = current_prompt_row["prompt_text"] if current_prompt_row else ""
    current_version = current_prompt_row["version"] if current_prompt_row else 1
    prev_score = current_prompt_row.get("avg_score_after") or 0 if current_prompt_row else 0

    if len(calls) < 5:
        logger.info("[MARS] Not enough calls (need 5+), skipping")
        return {"status": "skipped", "reason": "Insufficient call data"}

    # 2. Build performance stats
    scores = [c.get("overall_score", 0) for c in calls if c.get("overall_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    score_dist = {
        "excellent (85+)": sum(1 for s in scores if s >= 85),
        "good (70-84)":    sum(1 for s in scores if 70 <= s < 85),
        "needs work (50-69)": sum(1 for s in scores if 50 <= s < 70),
        "poor (<50)":      sum(1 for s in scores if s < 50),
    }

    # Find worst dimensions across all calls
    dim_totals: dict[str, list] = {}
    for call in calls:
        for dim in ("opening", "discovery", "rapport", "objection_handling",
                    "closing", "naturalness", "relevance", "pacing", "silence_handling"):
            col_name = f"{dim}_score" if dim != "objection_handling" else "objection_score"
            val = call.get(col_name, 0)
            if val:
                dim_totals.setdefault(dim, []).append(val)
    dim_avgs = {d: round(sum(v) / len(v), 1) for d, v in dim_totals.items() if v}
    worst_dims = sorted(dim_avgs.items(), key=lambda x: x[1])[:4]

    critique_summaries = "\n".join([
        f"- Call {i+1}: Score={c.get('overall_score',0)}/100 | "
        f"Geo={c.get('geo_region','unknown')} | "
        f"Summary={c.get('one_line_summary','N/A')} | "
        f"Verdict={str(c.get('coach_verdict',''))[:100]}"
        for i, c in enumerate(calls[:30])
    ])

    # 3. MCTS budget planner — delegate to ai.mars (canonical implementation)
    mcts_nodes = _run_mcts_planner(improvements, avg_score=avg_score)
    mcts_text = "\n".join([
        f"- [{n.module}] Score={n.score:.2f} | "
        f"Expected +{n.reward:.1f}pts | "
        f"~{n.compute_cost:.1f}min cost | {n.action[:80]}"
        for n in mcts_nodes[:8]
    ]) or "No ranked improvements available"

    improvements_text = "\n".join([
        f"- [{i.get('impact','?')} impact | {i.get('improvement_type','?')}] "
        f"{i.get('current_behavior','N/A')} → {i.get('suggested_behavior','N/A')}"
        for i in improvements[:25]
    ]) or "No pending improvements"

    lessons_text = "\n".join([
        f"- [{l.get('lesson_type','?')}] {l.get('content','')}"
        for l in existing_lessons[:10]
    ]) or "No existing lessons (first cycle)"

    # 4. Run MARS meta-analysis
    prompt = MARS_PROMPT.format(
        n_calls=len(calls),
        current_prompt=current_prompt[:2000],
        avg_score=f"{avg_score:.1f}",
        prev_score=f"{prev_score:.1f}",
        score_distribution=str(score_dist),
        worst_dimensions=str(worst_dims),
        critique_summaries=critique_summaries,
        mcts_improvements=mcts_text,
        improvements_text=improvements_text,
        existing_lessons=lessons_text,
    )

    try:
        raw = await cascade_ai_call(
            prompt=prompt,
            system_prompt=MARS_SYSTEM,
            task_type="mars_improvement",
            max_tokens=3500,
            use_cache=False,
        )
        result = parse_json_response(raw)
    except Exception as e:
        logger.error(f"[MARS] Meta-analysis failed: {e}")
        return {"status": "error", "reason": str(e)}

    new_prompt_text = result.get("updated_system_prompt", "")
    if not new_prompt_text or len(new_prompt_text) < 300:
        return {"status": "error", "reason": "Generated prompt too short, aborting"}

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    # 5. Store MARS lessons (long-term memory)
    cycle_minutes = max(elapsed_ms / 60_000, 0.1)
    for lesson_data in result.get("mars_lessons", []):
        try:
            delta = float(lesson_data.get("avg_score_delta", 0))
            await insert_mars_lesson({
                "lesson_type": lesson_data.get("lesson_type", "insight"),
                "content": lesson_data.get("content", ""),
                "source_calls": lesson_data.get("source_calls", len(calls)),
                "avg_score_delta": delta,
                # reward efficiency: score points gained per minute of compute
                "mcts_reward": round(delta / cycle_minutes, 4),
            })
        except Exception as e:
            logger.warning(f"[MARS] Failed to store lesson: {e}")

    # 6. Store new prompt version
    new_version_row = await insert_prompt_version({
        "prompt_text": new_prompt_text,
        "changelog": result.get("changelog", ""),
        "based_on_calls": len(calls),
        "avg_score_before": avg_score,
        "module_changes": result.get("module_changes", []),
    })
    new_version = new_version_row.get("version", current_version + 1)

    # 7. Push to Vapi
    vapi_updated = await _update_vapi_assistant(new_prompt_text)

    # 8. Mark improvements applied
    imp_ids = [i.get("id") for i in improvements if i.get("id")]
    if imp_ids:
        await mark_improvements_applied(imp_ids)

    summary = {
        "status": "success",
        "version": new_version,
        "calls_analyzed": len(calls),
        "improvements_applied": len(imp_ids),
        "avg_score_before": round(avg_score, 1),
        "patterns_found": len(result.get("patterns", [])),
        "mcts_nodes_evaluated": len(mcts_nodes),
        "lessons_stored": len(result.get("mars_lessons", [])),
        "vapi_updated": vapi_updated,
        "module_changes": [m.get("module") for m in result.get("module_changes", [])],
        "changelog": result.get("changelog", ""),
        "expected_improvements": result.get("expected_improvement_areas", []),
        "cycle_ms": elapsed_ms,
    }
    logger.info(f"[MARS] Cycle complete: v{current_version} → v{new_version} ({elapsed_ms}ms)")
    return summary


async def _update_vapi_assistant(new_prompt: str) -> bool:
    """Push updated system prompt to Vapi assistant via PATCH API."""
    vapi_key = os.environ.get("VAPI_API_KEY")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")

    if not vapi_key or not assistant_id:
        logger.warning("[MARS] VAPI_API_KEY or VAPI_ASSISTANT_ID not set — skipping Vapi update")
        return False

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(
                f"https://api.vapi.ai/assistant/{assistant_id}",
                json={"model": {"systemPrompt": new_prompt}},
                headers={
                    "Authorization": f"Bearer {vapi_key}",
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            logger.info("[MARS] Vapi assistant updated successfully")
            return True
    except Exception as e:
        logger.error(f"[MARS] Failed to update Vapi assistant: {e}")
        return False


async def trigger_call(lead_email: str, lead_name: str, phone: str, lead_context: dict) -> str | None:
    """
    Trigger an outbound Vapi call with geo-routing.
    Selects phone number based on lead's country code for local caller ID.
    Returns Vapi call ID or None if not configured.
    """
    vapi_key = os.environ.get("VAPI_API_KEY")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")

    if not all([vapi_key, assistant_id]):
        logger.warning("Vapi not fully configured — call not initiated")
        return None

    if not phone or len(phone.replace(" ", "").replace("-", "")) < 7:
        logger.warning(f"Invalid phone for {lead_email}: {phone}")
        return None

    # Geo-route: select local phone number ID
    phone_number_id = _get_phone_number_id(phone)
    if not phone_number_id:
        logger.warning(f"No Vapi phone number configured — call not initiated for {lead_email}")
        return None

    geo_region = _detect_geo_region(phone)

    # Get active prompt version for audit trail
    prompt_row = await get_active_prompt()
    current_version = prompt_row.get("version", 1) if prompt_row else 1

    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": phone,
            "name": lead_name,
        },
        "assistantOverrides": {
            "variableValues": {
                "lead_name": lead_name,
                "company": lead_context.get("company", "your company"),
                "lead_volume": lead_context.get("lead_volume", ""),
                "lead_score": str(lead_context.get("score", 0)),
                "tier": lead_context.get("tier", "medium"),
                "pain_hint": lead_context.get("message", ""),
                "geo_region": geo_region,
            },
        },
        "metadata": {
            "lead_email": lead_email,
            "lead_name": lead_name,
            "lead_score": lead_context.get("score", 0),
            "lead_tier": lead_context.get("tier", "unknown"),
            "company": lead_context.get("company", ""),
            "pain_hint": lead_context.get("message", ""),
            "geo_region": geo_region,
            "prompt_version": current_version,
        },
        "serverUrl": os.environ.get("WEBHOOK_BASE_URL", "") + "/webhooks/vapi",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.vapi.ai/call/phone",
                json=payload,
                headers={
                    "Authorization": f"Bearer {vapi_key}",
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            call_id = r.json().get("id")
            logger.info(f"Vapi call initiated: {call_id} for {lead_email} (geo={geo_region})")
            return call_id
    except Exception as e:
        logger.error(f"Failed to trigger Vapi call for {lead_email}: {e}")
        return None


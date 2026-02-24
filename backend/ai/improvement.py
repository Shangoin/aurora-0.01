"""
AURORA — Self-Improvement Loop
Every 50 calls (or weekly), Claude analyzes patterns and rewrites the Vapi agent prompt.
This is the "0.01% flywheel" — the system gets better every week automatically.
"""
import os
import logging
import httpx
from datetime import datetime
from models import PromptUpdate, PatternAnalysis
from ai.orchestrator import cascade_ai_call, parse_json_response
from db.supabase import (
    get_recent_calls, get_pending_improvements, get_active_prompt,
    insert_prompt_version, mark_improvements_applied
)

logger = logging.getLogger("aurora.improvement")

META_ANALYSIS_SYSTEM = """You are a VP of Sales Operations with deep expertise in AI SDR optimization.

Your job: Analyze call critique data, find repeating failure patterns, and write an improved AI agent prompt.

Rules:
1. Only fix patterns that appear in 3+ calls — don't over-fit to one-off events
2. The new prompt must be complete and deployable (not a diff — the full prompt)
3. Be specific in the changelog: "Improved objection handling for price objections by adding cost-of-inaction reframe"
4. Expected improvements must be measurable: "Opening score should increase from 58 to 70+"
"""

IMPROVEMENT_PROMPT = """Analyze these {n_calls} call critiques and {n_improvements} pending improvements.

== CURRENT AGENT PROMPT ==
{current_prompt}

== LAST {n_calls} CALL CRITIQUES (summaries) ==
{critique_summaries}

== PENDING SCRIPT IMPROVEMENTS ==
{improvements_text}

== PERFORMANCE STATS ==
Average overall score: {avg_score}/100
Score distribution: {score_distribution}
Most common issues: {common_issues}

Your task:
1. Identify the TOP 3 patterns causing low scores
2. Write a COMPLETE improved system prompt for the Vapi agent
3. Document specific changes in the changelog

Return ONLY valid JSON:
{{
  "patterns": [
    {{
      "issue": "<specific problem>",
      "frequency": <how many calls showed this>,
      "impact": "<high|medium|low>",
      "example_from_calls": "<actual quote showing the problem>"
    }}
  ],
  "updated_system_prompt": "<COMPLETE new prompt — minimum 500 words>",
  "changelog": "<bullet list of specific changes made>",
  "expected_improvement_areas": ["<metric1 will improve from X to Y>", "..."]
}}"""


async def run_improvement_cycle(n_calls: int = 50) -> dict:
    """
    Runs the full self-improvement cycle:
    1. Fetch recent calls + pending improvements
    2. Claude meta-analysis
    3. Update Vapi assistant prompt
    4. Store new prompt version
    5. Mark improvements as applied
    
    Returns summary of what changed.
    """
    logger.info(f"Starting improvement cycle (last {n_calls} calls)...")

    # 1. Gather data
    calls = await get_recent_calls(n_calls)
    improvements = await get_pending_improvements()
    current_prompt_row = await get_active_prompt()
    current_prompt = current_prompt_row["prompt_text"] if current_prompt_row else ""
    current_version = current_prompt_row["version"] if current_prompt_row else 1

    if len(calls) < 5:
        logger.info("Not enough calls for improvement cycle (need 5+)")
        return {"status": "skipped", "reason": "Not enough call data"}

    # 2. Summarize calls for the prompt
    scores = [c.get("overall_score", 0) for c in calls if c.get("overall_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    score_dist = {
        "excellent (80+)": sum(1 for s in scores if s >= 80),
        "good (60-79)": sum(1 for s in scores if 60 <= s < 80),
        "needs work (40-59)": sum(1 for s in scores if 40 <= s < 60),
        "poor (<40)": sum(1 for s in scores if s < 40),
    }

    critique_summaries = "\n".join([
        f"- Call {i+1}: Score={c.get('overall_score', 0)}/100 | "
        f"Summary={c.get('one_line_summary', 'N/A')} | "
        f"Verdict={c.get('coach_verdict', 'N/A')[:100]}"
        for i, c in enumerate(calls[:30])  # Top 30 for prompt size
    ])

    # Find common issues from script_improvements across all calls
    all_issues: dict[str, int] = {}
    for call in calls:
        imps = call.get("script_improvements", [])
        if isinstance(imps, list):
            for imp in imps:
                if isinstance(imp, dict):
                    cat = imp.get("category", "unknown")
                    all_issues[cat] = all_issues.get(cat, 0) + 1
    common_issues = sorted(all_issues.items(), key=lambda x: -x[1])[:5]

    improvements_text = "\n".join([
        f"- [{imp.get('impact', '?')} impact] {imp.get('current_behavior', 'N/A')} → {imp.get('suggested_behavior', 'N/A')}"
        for imp in improvements[:20]
    ]) or "No pending improvements"

    # 3. Run Claude meta-analysis
    prompt = IMPROVEMENT_PROMPT.format(
        n_calls=len(calls),
        n_improvements=len(improvements),
        current_prompt=current_prompt[:2000],  # Truncate to avoid huge tokens
        critique_summaries=critique_summaries,
        improvements_text=improvements_text,
        avg_score=f"{avg_score:.1f}",
        score_distribution=str(score_dist),
        common_issues=str(common_issues),
    )

    try:
        raw = await cascade_ai_call(
            prompt=prompt,
            system_prompt=META_ANALYSIS_SYSTEM,
            task_type="self_improvement",
            max_tokens=3000,
            use_cache=False,
            force_openai=True,
        )
        result = parse_json_response(raw)
    except Exception as e:
        logger.error(f"Meta-analysis failed: {e}")
        return {"status": "error", "reason": str(e)}

    new_prompt_text = result.get("updated_system_prompt", "")
    if not new_prompt_text or len(new_prompt_text) < 200:
        return {"status": "error", "reason": "Generated prompt too short, aborting"}

    # 4. Store new prompt version in Supabase
    new_version_row = await insert_prompt_version({
        "prompt_text": new_prompt_text,
        "changelog": result.get("changelog", ""),
        "based_on_calls": len(calls),
        "avg_score_before": avg_score,
    })
    new_version = new_version_row.get("version", current_version + 1)

    # 5. Push updated prompt to Vapi
    vapi_updated = await _update_vapi_assistant(new_prompt_text)

    # 6. Mark improvements as applied
    imp_ids = [imp.get("id") for imp in improvements if imp.get("id")]
    if imp_ids:
        await mark_improvements_applied(imp_ids)

    summary = {
        "status": "success",
        "version": new_version,
        "calls_analyzed": len(calls),
        "improvements_applied": len(imp_ids),
        "avg_score_before": round(avg_score, 1),
        "changelog": result.get("changelog", ""),
        "patterns_found": len(result.get("patterns", [])),
        "vapi_updated": vapi_updated,
        "expected_improvements": result.get("expected_improvement_areas", []),
    }
    logger.info(f"Improvement cycle complete: v{current_version} → v{new_version}")
    return summary


async def _update_vapi_assistant(new_prompt: str) -> bool:
    """Push updated system prompt to Vapi assistant via API"""
    vapi_key = os.environ.get("VAPI_API_KEY")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")

    if not vapi_key or not assistant_id:
        logger.warning("VAPI_API_KEY or VAPI_ASSISTANT_ID not set — skipping Vapi update")
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
            logger.info(f"Vapi assistant updated successfully")
            return True
    except Exception as e:
        logger.error(f"Failed to update Vapi assistant: {e}")
        return False


async def trigger_call(lead_email: str, lead_name: str, phone: str, lead_context: dict) -> str | None:
    """
    Trigger an outbound Vapi call to a lead. Returns Vapi call ID.
    """
    vapi_key = os.environ.get("VAPI_API_KEY")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")
    phone_number_id = os.environ.get("VAPI_PHONE_NUMBER_ID")

    if not all([vapi_key, assistant_id, phone_number_id]):
        logger.warning("Vapi not fully configured — call not initiated")
        return None

    if not phone or len(phone.replace(" ", "").replace("-", "")) < 7:
        logger.warning(f"Invalid phone for {lead_email}: {phone}")
        return None

    # Get active prompt for context injection
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
                "pain_hint": lead_context.get("message", ""),
            },
        },
        "metadata": {
            "lead_email": lead_email,
            "lead_score": lead_context.get("score", 0),
            "lead_tier": lead_context.get("tier", "unknown"),
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
            data = r.json()
            call_id = data.get("id")
            logger.info(f"Vapi call initiated: {call_id} for {lead_email}")
            return call_id
    except Exception as e:
        logger.error(f"Failed to trigger Vapi call for {lead_email}: {e}")
        return None

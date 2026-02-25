"""
Aurora 1.0 — NurtureAgent
Orchestrates personalized lead nurturing via OpenClaw (CMDOP) agent framework.

OpenClaw (pip install openclaw) is the CMDOP agent orchestration SDK.
The NurtureAgent uses AsyncCMDOPClient to run orchestration tasks if a local
CMDOP daemon is available, falling back gracefully to cascade_ai_call.

Sequence Types:
  hot_nurture   (score ≥ 60): 0h email → +24h WhatsApp → +24h Exotel call → +72h email → +168h email
  warm_nurture  (40-59):      0h email → +24h WhatsApp → +96h email → +168h Exotel call → +336h email
  cold_nurture  (<40):        +48h email → +96h WhatsApp → +168h email → +336h WhatsApp reactivation
"""
import os
import logging
import httpx
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("aurora.nurture.agent")

# ── OpenClaw (CMDOP) async client ─────────────────────────────────────────────
try:
    from openclaw import AsyncCMDOPClient, AgentRunOptions, AgentRunRequest, ConnectionError as ClawConnError
    _OPENCLAW_AVAILABLE = True
except ImportError:
    _OPENCLAW_AVAILABLE = False
    logger.warning("openclaw not installed — nurture agent will use cascade_ai_call fallback")


# ── Nurture sequence definitions ──────────────────────────────────────────────
# Each step: { "type": "email"|"call"|"whatsapp", "delay_hours": int,
#              "template": str | None, "provider": str | None }

SEQUENCES = {
    "hot_nurture": [
        {"type": "email",    "delay_hours": 0,    "template": "hot_immediate",     "step": 0},
        {"type": "whatsapp", "delay_hours": 24,   "template": "hot_day1",          "step": 1},
        {"type": "call",     "delay_hours": 24,   "provider":  "exotel",           "step": 2},
        {"type": "email",    "delay_hours": 72,   "template": "hot_day3",          "step": 3},
        {"type": "email",    "delay_hours": 168,  "template": "hot_final",         "step": 4},
    ],
    "warm_nurture": [
        {"type": "email",    "delay_hours": 0,    "template": "warm_intro",         "step": 0},
        {"type": "whatsapp", "delay_hours": 24,   "template": "warm_day1",          "step": 1},
        {"type": "email",    "delay_hours": 96,   "template": "warm_value_add",     "step": 2},
        {"type": "call",     "delay_hours": 168,  "provider":  "exotel",            "step": 3},
        {"type": "email",    "delay_hours": 336,  "template": "warm_final",         "step": 4},
    ],
    "cold_nurture": [
        {"type": "email",    "delay_hours": 48,   "template": "cold_intro",         "step": 0},
        {"type": "whatsapp", "delay_hours": 96,   "template": "cold_day4",          "step": 1},
        {"type": "email",    "delay_hours": 168,  "template": "cold_content",       "step": 2},
        {"type": "whatsapp", "delay_hours": 336,  "template": "cold_reactivation",  "step": 3},
    ],
}


def pick_sequence(lead_score: int, should_follow_up: bool) -> str:
    """Select nurture sequence type based on lead score and call outcome."""
    if not should_follow_up:
        return "cold_nurture"
    if lead_score >= 60:
        return "hot_nurture"
    if lead_score >= 40:
        return "warm_nurture"
    return "cold_nurture"


def build_sequence_steps(sequence_type: str, base_time: datetime) -> list[dict]:
    """
    Expand sequence definition into concrete scheduled steps with ISO timestamps.
    """
    steps = []
    for s in SEQUENCES[sequence_type]:
        scheduled_at = base_time + timedelta(hours=s["delay_hours"])
        steps.append({
            **s,
            "scheduled_at": scheduled_at.isoformat(),
            "status": "pending",
            "result": None,
        })
    return steps


# ── OpenClaw orchestration ─────────────────────────────────────────────────────

async def _openclaw_personalize(
    template_type: str,
    lead_name: str,
    lead_company: str,
    pain_points: list[str],
    call_summary: str,
    geo_region: str,
) -> dict:
    """
    Use OpenClaw (CMDOP) agent to generate fully personalized email content.
    Returns {"subject": str, "body": str}.
    Falls back to cascade_ai_call if CMDOP daemon not running.
    """
    if _OPENCLAW_AVAILABLE:
        try:
            async with await AsyncCMDOPClient.local() as client:
                prompt = (
                    f"Generate a personalized sales follow-up email.\n"
                    f"Template: {template_type}\n"
                    f"Lead name: {lead_name} at {lead_company}\n"
                    f"Pain points: {', '.join(pain_points) or 'not specified'}\n"
                    f"Call summary: {call_summary or 'No call yet'}\n"
                    f"Geo region: {geo_region}\n"
                    f"Return JSON: {{ \"subject\": \"...\", \"body\": \"...\" }}\n"
                    f"Keep the email concise (<150 words), conversational, and focused on ONE pain point."
                )
                options = AgentRunOptions(temperature=0.4, output_format="json")
                result = await client.run(AgentRunRequest(message=prompt, options=options))
                raw = result.output or "{}"
                return json.loads(raw) if raw.startswith("{") else {"subject": "", "body": raw}
        except Exception as exc:
            logger.warning(f"OpenClaw unavailable ({exc}), falling back to cascade_ai_call")

    # Fallback: use cascade_ai_call from the Aurora AI orchestrator
    from ai.orchestrator import cascade_ai_call
    prompt = (
        f"Write a personalized sales nurture email.\n"
        f"Template type: {template_type}. Lead: {lead_name} at {lead_company}.\n"
        f"Their pain points: {', '.join(pain_points) or 'efficiency, growth'}.\n"
        f"Call notes: {call_summary or 'First contact via form'}.\n"
        f"Return JSON only: {{\"subject\": \"...\", \"body\": \"...\"}}\n"
        f"Max 130 words, professional-warm tone."
    )
    raw = await cascade_ai_call(prompt, task_type="nurture_email")
    try:
        # Strip markdown fences if any
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
    except Exception:
        return {
            "subject": f"Following up, {lead_name.split()[0]}",
            "body": f"Hi {lead_name.split()[0]},\n\nJust wanted to follow up on our recent conversation. Would love to explore how Shango Revenue Systems can help {lead_company} address {pain_points[0] if pain_points else 'your sales challenges'}.\n\nWorth a quick 15-min chat?\n\nBest,\nARIA @ Shango Revenue Systems",
        }


# ── Email sending via Brevo ────────────────────────────────────────────────────

async def send_nurture_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send a nurture email via Brevo (formerly Sendinblue) REST API."""
    api_key = os.environ.get("BREVO_API_KEY") or os.environ.get("SENDINBLUE_API_KEY")
    from_email = os.environ.get("FROM_EMAIL", "aria@shango.ai")
    from_name = os.environ.get("FROM_NAME", "ARIA — Shango Revenue Systems")

    if not api_key:
        logger.warning("BREVO_API_KEY not set — skipping email send (log only)")
        logger.info(f"[DRY RUN] Email to {to_email}: {subject}")
        return True  # Return True in dev so nurture state advances

    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_body,
        "tags": ["aurora-nurture", "srs"],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
        if r.status_code in (200, 201, 202):
            logger.info(f"Nurture email sent to {to_email}: {subject}")
            return True
        logger.error(f"Brevo error {r.status_code}: {r.text[:200]}")
        return False


# ── Follow-up call via Vapi ────────────────────────────────────────────────────

async def schedule_followup_call(
    phone: str,
    lead_name: str,
    lead_email: str,
    lead_company: str,
    context: str,
) -> bool:
    """Trigger a Vapi follow-up call for a hot/warm lead."""
    from ai.improvement import trigger_call
    try:
        await trigger_call(
            lead_email=lead_email,
            lead_name=lead_name,
            phone=phone,
            lead_context={
                "company": lead_company,
                "nurture_note": context,
                "is_followup": True,
            },
        )
        return True
    except Exception as exc:
        logger.error(f"Follow-up call failed for {lead_email}: {exc}")
        return False


# ── WhatsApp messaging (Meta Business API) ──────────────────────────────────────

async def send_whatsapp_message(phone: str, template: str, personalization_data: dict) -> bool:
    """
    Send a WhatsApp template message via the Meta WhatsApp Business API.

    Template names are prefixed with "shango_" (e.g. shango_hot_day1).
    ``personalization_data`` values are passed as ordered body parameters so the
    approved template can interpolate {{1}}, {{2}}, etc.

    Required env vars:
        WHATSAPP_PHONE_ID   — Meta phone number ID (numeric string)
        WHATSAPP_TOKEN      — System user access token (permanent)
    """
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    token = os.environ.get("WHATSAPP_TOKEN")

    if not phone_id or not token:
        logger.warning("WHATSAPP_PHONE_ID / WHATSAPP_TOKEN not set — dry-run")
        logger.info(f"[DRY RUN] WhatsApp template shango_{template} to {phone}: {personalization_data}")
        return True

    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"

    # Build optional body parameters from personalization_data values (ordered)
    components = []
    if personalization_data:
        params = [
            {"type": "text", "text": str(v)}
            for v in personalization_data.values()
            if v is not None
        ]
        if params:
            components = [{"type": "body", "parameters": params}]

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": f"shango_{template}",
            "language": {"code": "en_US"},
            **(  {"components": components} if components else {}  ),
        },
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url, json=payload, headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code in (200, 201):
        logger.info(f"WhatsApp template shango_{template} sent to {phone}")
        return True

    logger.error(f"Meta WhatsApp API error {resp.status_code}: {resp.text[:300]}")
    return False


# ── Exotel outbound call ───────────────────────────────────────────────────────

async def trigger_exotel_call(
    phone: str,
    script: str,
    lead_email: str = "",
    lead_name: str = "",
    lead_company: str = "",
) -> bool:
    """
    Trigger an outbound call via Exotel's Call API.

    Auth is sent as basic-auth embedded in the URL:
        https://<api_key>:<api_token>@<subdomain>.exotel.com/v1/Accounts/<sid>/Calls/connect.json

    Required env vars:
        EXOTEL_SID           — Account SID
        EXOTEL_API_KEY       — API key (basic-auth username)
        EXOTEL_API_TOKEN     — API token (basic-auth password)
        EXOTEL_SUBDOMAIN     — e.g. "my-company.api.exotel.com"
        EXOTEL_FROM_NUMBER   — Exotel virtual number / ExoPhone
    """
    sid = os.environ.get("EXOTEL_SID")
    api_key = os.environ.get("EXOTEL_API_KEY")
    api_token = os.environ.get("EXOTEL_API_TOKEN")
    subdomain = os.environ.get("EXOTEL_SUBDOMAIN")
    from_number = os.environ.get("EXOTEL_FROM_NUMBER")
    webhook_base = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")

    if not all([sid, api_key, api_token, subdomain, from_number]):
        logger.warning("Exotel env vars not fully set — dry-run call")
        logger.info(f"[DRY RUN] Exotel call to {phone} for {lead_email}: {script[:80]}...")
        return True

    url = f"https://{api_key}:{api_token}@{subdomain}/v1/Accounts/{sid}/Calls/connect.json"
    payload = {
        "From": from_number,
        "To": phone,
        "Url": f"{webhook_base}/webhooks/exotel",
        "Method": "POST",
        "CustomField": json.dumps({
            "lead_email": lead_email,
            "lead_company": lead_company,
            "script": script[:200],
        }),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, data=payload)
    if r.status_code in (200, 201):
        logger.info(f"Exotel call initiated to {phone} for {lead_email}")
        return True
    logger.error(f"Exotel call error {r.status_code}: {r.text[:300]}")
    return False


# ── NurtureAgent ──────────────────────────────────────────────────────────────

class NurtureAgent:
    """
    OpenClaw-powered lead nurture orchestrator.

    On call end (no meeting booked):
    1. Picks sequence type based on lead score
    2. Builds scheduled steps
    3. Persists to nurture_sequences table
    4. Immediately executes step 0 if delay_hours == 0

    Scheduler then drives subsequent steps.
    """

    async def create_sequence(
        self,
        lead_email: str,
        lead_name: str,
        lead_company: str,
        lead_score: int,
        phone: str,
        pain_points: list[str],
        call_summary: str,
        geo_region: str = "global",
        should_follow_up: bool = True,
    ) -> dict:
        """
        Create and persist a nurture sequence for a lead.
        Returns the created nurture_sequence record.
        """
        from db.supabase import insert_nurture_sequence, get_nurture_sequence_by_email, deactivate_nurture_sequences

        # Cancel any existing active sequences for this lead
        await deactivate_nurture_sequences(lead_email)

        seq_type = pick_sequence(lead_score, should_follow_up)
        now = datetime.now(timezone.utc)
        steps = build_sequence_steps(seq_type, now)

        record = {
            "lead_email": lead_email,
            "lead_name": lead_name,
            "lead_company": lead_company,
            "lead_score": lead_score,
            "phone": phone,
            "pain_points": pain_points,
            "call_summary": call_summary,
            "geo_region": geo_region,
            "sequence_type": seq_type,
            "current_step": 0,
            "steps": steps,
            "is_active": True,
            "completed": False,
        }

        saved = await insert_nurture_sequence(record)
        logger.info(f"Nurture sequence created: {lead_email} → {seq_type} ({len(steps)} steps)")

        # Execute step 0 immediately if it has no delay
        if steps and steps[0]["delay_hours"] == 0:
            await self.execute_step(saved["id"], steps[0], record)

        return saved

    async def execute_step(
        self,
        sequence_id: str,
        step: dict,
        sequence: dict,
    ) -> bool:
        """Execute a single nurture step (email or call)."""
        from db.supabase import update_nurture_step
        from nurture.templates import render_email_html

        lead_email = sequence["lead_email"]
        lead_name = sequence.get("lead_name", "there")
        lead_company = sequence.get("lead_company", "your company")
        pain_points = sequence.get("pain_points", [])
        call_summary = sequence.get("call_summary", "")
        geo_region = sequence.get("geo_region", "global")
        phone = sequence.get("phone", "")

        step_idx = step["step"]
        step_type = step["type"]
        template = step.get("template") or ""
        provider = step.get("provider", "vapi")

        logger.info(f"Executing nurture step {step_idx} ({step_type}/{template or provider}) for {lead_email}")

        success = False
        try:
            if step_type == "email":
                # Use OpenClaw to personalize
                content = await _openclaw_personalize(
                    template_type=template,
                    lead_name=lead_name,
                    lead_company=lead_company,
                    pain_points=pain_points,
                    call_summary=call_summary,
                    geo_region=geo_region,
                )
                subject = content.get("subject") or f"Following up, {lead_name.split()[0]}"
                body_text = content.get("body") or ""
                html_body = render_email_html(subject, body_text, lead_name, template)
                success = await send_nurture_email(lead_email, lead_name, subject, html_body)

            elif step_type == "whatsapp":
                if phone:
                    personalization_data = {
                        "name": lead_name.split()[0],
                        "company": lead_company,
                        "pain_point": pain_points[0] if pain_points else "",
                    }
                    success = await send_whatsapp_message(phone, template, personalization_data)
                else:
                    logger.info(f"No phone for {lead_email} — skipping WhatsApp step")
                    success = True

            elif step_type == "call":
                if phone:
                    context = f"This is a follow-up call. {call_summary or ''} Pain points: {', '.join(pain_points)}."
                    if provider == "exotel":
                        script = f"{call_summary or ''} Pain points: {', '.join(pain_points)}.".strip()
                        success = await trigger_exotel_call(
                            phone=phone,
                            script=script,
                            lead_email=lead_email,
                            lead_name=lead_name,
                            lead_company=lead_company,
                        )
                    else:
                        success = await schedule_followup_call(
                            phone, lead_name, lead_email, lead_company, context
                        )
                else:
                    # No phone — fallback to email
                    logger.info(f"No phone for {lead_email} — sending follow-up email instead of call")
                    content = await _openclaw_personalize(
                        template_type=f"{template}_email_fallback",
                        lead_name=lead_name,
                        lead_company=lead_company,
                        pain_points=pain_points,
                        call_summary=call_summary,
                        geo_region=geo_region,
                    )
                    subject = content.get("subject", f"Quick thought for {lead_name.split()[0]}")
                    body_text = content.get("body", "")
                    html_body = render_email_html(subject, body_text, lead_name, "followup")
                    success = await send_nurture_email(lead_email, lead_name, subject, html_body)

        except Exception as exc:
            logger.error(f"Nurture step {step_idx} failed for {lead_email}: {exc}")
            success = False

        await update_nurture_step(sequence_id, step_idx, "done" if success else "failed")
        return success

    async def advance_sequence(self, sequence: dict) -> bool:
        """
        Check if the next step is due and execute it.
        Returns True if a step was executed.
        """
        from db.supabase import mark_nurture_completed

        steps = sequence.get("steps", [])
        current_step = sequence.get("current_step", 0)

        # Find next pending step
        for step in steps:
            if step.get("status") != "pending":
                continue
            scheduled_at = datetime.fromisoformat(step["scheduled_at"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now >= scheduled_at:
                ok = await self.execute_step(sequence["id"], step, sequence)
                if ok:
                    # If last step, mark completed
                    if step["step"] == len(steps) - 1:
                        await mark_nurture_completed(sequence["id"])
                        logger.info(f"Nurture sequence completed for {sequence['lead_email']}")
                return ok

        # No pending steps left → mark complete
        all_done = all(s.get("status") != "pending" for s in steps)
        if all_done and not sequence.get("completed"):
            await mark_nurture_completed(sequence["id"])

        return False


# Module-level singleton
_agent: NurtureAgent | None = None


def get_nurture_agent() -> NurtureAgent:
    global _agent
    if _agent is None:
        _agent = NurtureAgent()
    return _agent

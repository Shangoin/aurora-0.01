"""
Aurora 1.0 - Production Setup CLI
===================================
Automates every manual deployment step from the Design Document ~16.

Usage:
    python setup.py init                  # Full setup (all steps)
    python setup.py check                 # Validate env vars + connectivity
    python setup.py supabase-migrate      # Supabase DDL migrations only
    python setup.py whatsapp-templates    # Submit WhatsApp templates to Meta
    python setup.py exotel-webhook        # Register Exotel callback URL
    python setup.py seed-prompt           # Seed initial ARIA prompt v1

Requirements (all already in requirements.txt):
    click  httpx  python-dotenv  supabase
"""
import os
import re
import sys
import json
import asyncio
import textwrap
from typing import Optional

import click
import httpx
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Console helpers (pure-ASCII labels for Windows terminal compatibility)
# ---------------------------------------------------------------------------

def ok(msg: str) -> None:
    click.echo(click.style("  [OK]   ", fg="green", bold=True) + msg)


def fail(msg: str) -> None:
    click.echo(click.style("  [FAIL] ", fg="red", bold=True) + msg)


def warn(msg: str) -> None:
    click.echo(click.style("  [WARN] ", fg="yellow", bold=True) + msg)


def info(msg: str) -> None:
    click.echo(click.style("  [INFO] ", fg="cyan") + msg)


def section(title: str) -> None:
    click.echo()
    pad = max(0, 60 - len(title))
    click.echo(
        click.style(f"-- {title} ", fg="bright_white", bold=True)
        + click.style("-" * pad, fg="bright_black")
    )


def abort(msg: str) -> None:
    fail(msg)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------

def _env(key: str, required: bool = True) -> Optional[str]:
    val = os.environ.get(key, "").strip()
    return val if val else None


def _project_ref_from_url(supabase_url: str) -> Optional[str]:
    """Extract project ref from https://<ref>.supabase.co"""
    m = re.match(r"https://([a-z0-9]+)\.supabase\.co", supabase_url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# ENV groups (for the `check` command)
# ---------------------------------------------------------------------------

REQUIRED_VARS = {
    "Core": ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "WEBHOOK_BASE_URL"],
    "AI Cascade": ["GEMINI_API_KEY"],
    "Vapi": ["VAPI_API_KEY", "VAPI_ASSISTANT_ID"],
    "Brevo": ["BREVO_API_KEY", "FROM_EMAIL"],
}

RECOMMENDED_VARS = {
    "AI Cascade (fallbacks)": [
        "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY",
    ],
    "Vapi Geo-routing": [
        "VAPI_PHONE_NUMBER_ID_IN", "VAPI_PHONE_NUMBER_ID_US",
        "VAPI_PHONE_NUMBER_ID_UK", "VAPI_PHONE_NUMBER_ID_GLOBAL",
    ],
    "WhatsApp (Meta)": ["WHATSAPP_PHONE_ID", "WHATSAPP_TOKEN", "WHATSAPP_WABA_ID"],
    "Serper (Enrichment)": ["SERPER_API_KEY"],
    "Exotel": [
        "EXOTEL_SID", "EXOTEL_API_KEY", "EXOTEL_API_TOKEN",
        "EXOTEL_SUBDOMAIN", "EXOTEL_FROM_NUMBER",
    ],
    "Security": ["WEBHOOK_SECRET", "ADMIN_SECRET", "ALLOWED_ORIGINS"],
    "Supabase Migrations": ["SUPABASE_ACCESS_TOKEN"],
}

# ---------------------------------------------------------------------------
# ARIA prompt v1 (plain ASCII quotes so it survives any encoding)
# ---------------------------------------------------------------------------

ARIA_PROMPT_V1 = (
    "You are ARIA, an elite AI sales development representative from Shango Revenue Systems. "
    "Your only goal is to book a discovery call with qualified prospects.\n\n"
    "PERSONA: You are warm, confident, and genuinely curious. You have done your homework on the "
    "prospect's business. You are NOT pushy or salesy.\n\n"
    "OPENING (always start here):\n"
    '"Hi [name], this is ARIA calling from Shango Revenue Systems. I saw you filled out our form '
    'about [their use case]. Is now a good time for 2 minutes?"\n\n'
    "DISCOVERY QUESTIONS (ask max 3, listen intently):\n"
    '1. "What made you reach out today - what\'s the biggest challenge you\'re trying to solve?"\n'
    '2. "How are you handling that right now, and what\'s not working?"\n'
    '3. "If you could solve this perfectly, what would that look like 90 days from now?"\n\n'
    "VALUE POSITIONING (only after discovery):\n"
    "Tie your solution directly to their specific pain point. Use their exact words.\n\n"
    "OBJECTION HANDLING:\n"
    '- "Not interested": "Totally understand. Just out of curiosity, what would need to be different?"\n'
    '- "Too expensive": "Makes sense to ask. What\'s the cost each month of NOT solving [their pain]?"\n'
    '- "Send me info": "Happy to. Let me ask one quick thing first - [discovery question]"\n'
    '- "Talk to my boss": "Would it help if I walked through the key points with both of you?"\n\n'
    "CLOSING:\n"
    '"Based on what you\'ve shared, I think a 20-minute demo would be worth your time. '
    'I have [time slot] or [time slot] - which works better?"\n\n'
    "RULES:\n"
    "- Never lie or exaggerate\n"
    "- Never mention competitors by name\n"
    "- Keep responses under 3 sentences unless explaining value\n"
    '- If asked if you are AI: "I am an AI assistant from Shango Revenue Systems, and I\'m here '
    'to make sure your time is respected. Can I ask you one thing?"\n'
    "- End every call gracefully, even if rejected\n"
)


# ---------------------------------------------------------------------------
# Supabase migrations (idempotent DDL)
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[str, str]] = [
    (
        "Add follow_up_strategy CHECK constraint",
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'follow_up_strategy_check'
              AND table_name = 'calls'
          ) THEN
            ALTER TABLE calls
              ADD CONSTRAINT follow_up_strategy_check
              CHECK (follow_up_strategy IN ('email','call','whatsapp','sms','none'));
          END IF;
        END $$;
        """,
    ),
    (
        "Add pacing_score column to calls",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS pacing_score INTEGER DEFAULT 0;",
    ),
    (
        "Add silence_score column to calls",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS silence_score INTEGER DEFAULT 0;",
    ),
    (
        "Add geo_region column to calls",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS geo_region TEXT DEFAULT 'global';",
    ),
    (
        "Add geo_region index to calls",
        "CREATE INDEX IF NOT EXISTS idx_calls_geo ON calls(geo_region);",
    ),
    (
        "Add module_changes column to prompt_versions",
        "ALTER TABLE prompt_versions ADD COLUMN IF NOT EXISTS module_changes JSONB DEFAULT '[]';",
    ),
    (
        "Add enrichment_signals column to leads",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS enrichment_signals JSONB DEFAULT '{}';",
    ),
    (
        "Create nurture_sequences table",
        """
        CREATE TABLE IF NOT EXISTS nurture_sequences (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lead_email      TEXT NOT NULL,
            lead_name       TEXT,
            lead_company    TEXT,
            lead_score      INTEGER DEFAULT 50,
            phone           TEXT,
            pain_points     JSONB DEFAULT '[]',
            call_summary    TEXT,
            geo_region      TEXT DEFAULT 'global',
            sequence_type   TEXT NOT NULL CHECK (
                                sequence_type IN ('hot_nurture','warm_nurture','cold_nurture')),
            current_step    INTEGER DEFAULT 0,
            steps           JSONB NOT NULL DEFAULT '[]',
            is_active       BOOLEAN DEFAULT TRUE,
            completed       BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            last_action_at  TIMESTAMPTZ
        );
        """,
    ),
    (
        "Enable RLS on nurture_sequences",
        """
        DO $$ BEGIN
          ALTER TABLE nurture_sequences ENABLE ROW LEVEL SECURITY;
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """,
    ),
    (
        "Create service_all policy on nurture_sequences",
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'nurture_sequences' AND policyname = 'service_all'
          ) THEN
            EXECUTE 'CREATE POLICY service_all ON nurture_sequences FOR ALL USING (true)';
          END IF;
        END $$;
        """,
    ),
    (
        "Create nurture_sequences indexes",
        """
        CREATE INDEX IF NOT EXISTS idx_nurture_email  ON nurture_sequences(lead_email);
        CREATE INDEX IF NOT EXISTS idx_nurture_active ON nurture_sequences(is_active, completed);
        CREATE INDEX IF NOT EXISTS idx_nurture_type   ON nurture_sequences(sequence_type);
        """,
    ),
    (
        "Create mars_lessons table",
        """
        CREATE TABLE IF NOT EXISTS mars_lessons (
            id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
            lesson_type     TEXT NOT NULL CHECK (lesson_type IN (
                                'pattern','objection','opening',
                                'insight','geo','closing','discovery')),
            content         TEXT NOT NULL,
            source_calls    INTEGER DEFAULT 1,
            avg_score_delta NUMERIC(5,2) DEFAULT 0,
            mcts_reward     NUMERIC(8,4) DEFAULT 0,
            geo_region      TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        """,
    ),
    (
        "Enable RLS on mars_lessons",
        """
        DO $$ BEGIN
          ALTER TABLE mars_lessons ENABLE ROW LEVEL SECURITY;
        EXCEPTION WHEN others THEN NULL;
        END $$;
        """,
    ),
    (
        "Create service_all policy on mars_lessons",
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename = 'mars_lessons' AND policyname = 'service_all'
          ) THEN
            EXECUTE 'CREATE POLICY service_all ON mars_lessons FOR ALL USING (true)';
          END IF;
        END $$;
        """,
    ),
]

PROMPT_SEED_SQL = (
    "INSERT INTO prompt_versions (version, prompt_text, changelog, is_active, based_on_calls)\n"
    "VALUES (\n"
    "  1,\n"
    "  $ARIA_PROMPT$\n"
    + ARIA_PROMPT_V1 +
    "\n  $ARIA_PROMPT$,\n"
    "  'Initial prompt - v1 (ARIA / Shango Revenue Systems)',\n"
    "  TRUE,\n"
    "  0\n"
    ")\n"
    "ON CONFLICT (version) DO NOTHING;"
)


async def _run_sql_via_management_api(
    project_ref: str,
    access_token: str,
    sql: str,
) -> tuple[bool, str]:
    """Execute raw SQL against a Supabase project via the Management API."""
    url = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json={"query": sql.strip()})
    if resp.status_code in (200, 201):
        return True, ""
    return False, f"HTTP {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------------------
# WhatsApp template payloads (Meta Graph API)
# ---------------------------------------------------------------------------

WHATSAPP_TEMPLATES = [
    {
        "name": "shango_hot_day1",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {
                "type": "HEADER",
                "format": "TEXT",
                "text": "Quick follow-up from Shango Revenue Systems",
            },
            {
                "type": "BODY",
                "text": (
                    "Hi {{1}}, following up on Shango Revenue Systems reaching out to {{2}}. "
                    "We'd love to address {{3}} - worth a 15-min chat?"
                ),
                "example": {
                    "body_text": [["Sarah", "TechStartup Inc", "manual outreach bottlenecks"]]
                },
            },
            {"type": "FOOTER", "text": "Reply STOP to unsubscribe"},
        ],
    },
    {
        "name": "shango_warm_day1",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {
                "type": "HEADER",
                "format": "TEXT",
                "text": "A note from ARIA at Shango Revenue Systems",
            },
            {
                "type": "BODY",
                "text": (
                    "Hi {{1}}, quick note from Shango Revenue Systems re: {{2}}. "
                    "We help teams tackle {{3}} - can we find 15 mins?"
                ),
                "example": {
                    "body_text": [["Alex", "GrowthCo", "low sales conversion"]]
                },
            },
            {"type": "FOOTER", "text": "Reply STOP to unsubscribe"},
        ],
    },
    {
        "name": "shango_cold_day4",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Hi {{1}} - Shango Revenue Systems here. "
                    "We specialize in helping {{2}} solve {{3}}. Open to a brief call?"
                ),
                "example": {
                    "body_text": [["Jordan", "ScaleUp Ltd", "lead response time"]]
                },
            },
            {"type": "FOOTER", "text": "Reply STOP to unsubscribe"},
        ],
    },
    {
        "name": "shango_cold_reactivation",
        "language": "en_US",
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Hi {{1}}, it's been a while! Shango Revenue Systems is back with new "
                    "solutions for {{2}} around {{3}}. Interested in a quick chat?"
                ),
                "example": {
                    "body_text": [["Taylor", "RevCo", "pipeline visibility"]]
                },
            },
            {"type": "FOOTER", "text": "Reply STOP to unsubscribe"},
        ],
    },
]


async def _submit_whatsapp_template(
    waba_id: str,
    token: str,
    template: dict,
    client: httpx.AsyncClient,
) -> tuple[bool, str, str]:
    """Submit a single WhatsApp template to Meta. Returns (success, name, status/error)."""
    url = f"https://graph.facebook.com/v20.0/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(url, headers=headers, json=template)
    name = template["name"]
    if resp.status_code in (200, 201):
        data = resp.json()
        return True, name, data.get("status", "PENDING")
    body = resp.json()
    err_msg = body.get("error", {}).get("message", resp.text[:200])
    if "already exists" in err_msg.lower() or body.get("error", {}).get("code") == 100:
        return True, name, "ALREADY_EXISTS"
    return False, name, err_msg


# ---------------------------------------------------------------------------
# Exotel webhook configuration
# ---------------------------------------------------------------------------

async def _configure_exotel_webhook(
    sid: str,
    api_key: str,
    api_token: str,
    subdomain: str,
    from_number: str,
    webhook_url: str,
) -> tuple[bool, str]:
    """Register callback URL on the Exotel virtual number via IncomingPhoneNumbers API."""
    url = (
        f"https://{api_key}:{api_token}@{subdomain}"
        f"/v1/Accounts/{sid}/IncomingPhoneNumbers/{from_number}.json"
    )
    payload = {"StatusCallback": webhook_url, "StatusCallbackMethod": "POST"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, data=payload)
    if resp.status_code in (200, 201):
        return True, ""
    return False, f"HTTP {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Aurora 1.0 - Production Setup CLI"""


@cli.command("check")
def cmd_check():
    """Validate all environment variables and test connectivity."""
    section("Environment Variables - Required")
    all_required_ok = True
    for group, keys in REQUIRED_VARS.items():
        click.echo(f"\n  {click.style(group, bold=True)}")
        for key in keys:
            val = _env(key)
            if val:
                ok(f"{key} = {'*' * min(8, len(val))}...")
            else:
                fail(f"{key} - MISSING")
                all_required_ok = False

    section("Environment Variables - Recommended")
    for group, keys in RECOMMENDED_VARS.items():
        click.echo(f"\n  {click.style(group, bold=True)}")
        for key in keys:
            val = _env(key)
            if val:
                ok(f"{key} = {'*' * min(8, len(val))}...")
            else:
                warn(f"{key} - not set (optional)")

    section("Connectivity Checks")
    asyncio.run(_check_connectivity())

    click.echo()
    if all_required_ok:
        ok("All required env vars present.")
    else:
        fail("Some required env vars are missing - fix before running init.")


async def _check_connectivity() -> None:
    supabase_url = _env("SUPABASE_URL")
    supabase_key = _env("SUPABASE_SERVICE_KEY", required=False) or _env("SUPABASE_KEY", required=False)
    whatsapp_token = _env("WHATSAPP_TOKEN", required=False)
    whatsapp_phone_id = _env("WHATSAPP_PHONE_ID", required=False)

    async with httpx.AsyncClient(timeout=10) as client:
        if supabase_url and supabase_key:
            try:
                r = await client.get(
                    f"{supabase_url}/rest/v1/leads?select=id&limit=1",
                    headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                )
                if r.status_code in (200, 206):
                    ok("Supabase REST API - reachable")
                else:
                    warn(f"Supabase REST API - HTTP {r.status_code} (check service key or RLS)")
            except Exception as exc:
                fail(f"Supabase - {exc}")
        else:
            warn("Supabase - skipped (SUPABASE_URL / SUPABASE_SERVICE_KEY missing)")

        if whatsapp_token and whatsapp_phone_id:
            try:
                r = await client.get(
                    f"https://graph.facebook.com/v20.0/{whatsapp_phone_id}",
                    headers={"Authorization": f"Bearer {whatsapp_token}"},
                )
                if r.status_code == 200:
                    ok("Meta Graph API - WhatsApp phone ID valid")
                elif r.status_code == 401:
                    fail("Meta Graph API - invalid token (WHATSAPP_TOKEN)")
                else:
                    warn(f"Meta Graph API - HTTP {r.status_code}")
            except Exception as exc:
                fail(f"Meta Graph API - {exc}")
        else:
            warn("Meta WhatsApp - skipped (WHATSAPP_PHONE_ID / WHATSAPP_TOKEN missing)")


# ---------------------------------------------------------------------------

@cli.command("supabase-migrate")
@click.option("--dry-run", is_flag=True, help="Print SQL without executing.")
def cmd_supabase_migrate(dry_run: bool):
    """Run all Supabase DDL migrations via the Management API."""
    asyncio.run(_do_supabase_migrate(dry_run=dry_run))


async def _do_supabase_migrate(dry_run: bool = False) -> None:
    section("Supabase Migrations")

    supabase_url = _env("SUPABASE_URL")
    access_token = _env("SUPABASE_ACCESS_TOKEN", required=False)

    if not supabase_url:
        abort("SUPABASE_URL not set.")
        return

    project_ref = _project_ref_from_url(supabase_url)
    if not project_ref:
        abort(f"Cannot parse project ref from SUPABASE_URL: {supabase_url}")
        return

    info(f"Project ref: {project_ref}")

    if dry_run:
        warn("DRY RUN - SQL printed, not executed.")
        for name, sql in MIGRATIONS:
            click.echo(f"\n  -- {name}")
            click.echo(textwrap.indent(sql.strip(), "  "))
        click.echo("\n  -- Seed prompt v1")
        click.echo(textwrap.indent(PROMPT_SEED_SQL[:300] + "...", "  "))
        return

    if not access_token:
        warn("SUPABASE_ACCESS_TOKEN not set.")
        info("Get a Personal Access Token: https://supabase.com/dashboard/account/tokens")
        info("Add SUPABASE_ACCESS_TOKEN=<token> to backend/.env and re-run.")
        info("Or run with --dry-run to get SQL to paste into the Supabase SQL Editor.")
        return

    click.echo()
    passed = 0
    failed = 0
    for name, sql in MIGRATIONS:
        success, err = await _run_sql_via_management_api(project_ref, access_token, sql)
        if success:
            ok(name)
            passed += 1
        else:
            fail(f"{name} - {err}")
            failed += 1

    success, err = await _run_sql_via_management_api(project_ref, access_token, PROMPT_SEED_SQL)
    if success:
        ok("Seed ARIA prompt v1 (skipped if already exists)")
        passed += 1
    else:
        fail(f"Seed prompt - {err}")
        failed += 1

    click.echo()
    failed_str = click.style(str(failed), fg="red") if failed else "0"
    click.echo(
        f"  Migrations: {click.style(str(passed), fg='green')} passed  {failed_str} failed"
    )


# ---------------------------------------------------------------------------

@cli.command("whatsapp-templates")
@click.option("--dry-run", is_flag=True, help="Print payloads without submitting.")
def cmd_whatsapp_templates(dry_run: bool):
    """Submit 4 shango_* WhatsApp templates to Meta Business Manager."""
    asyncio.run(_do_whatsapp_templates(dry_run=dry_run))


async def _do_whatsapp_templates(dry_run: bool = False) -> None:
    section("WhatsApp Template Registration (Meta Business API)")

    waba_id = _env("WHATSAPP_WABA_ID", required=False)
    token = _env("WHATSAPP_TOKEN", required=False)

    if dry_run:
        warn("DRY RUN - template payloads (not submitted):")
        for t in WHATSAPP_TEMPLATES:
            click.echo(f"\n  Template: {click.style(t['name'], bold=True)}")
            click.echo(json.dumps(t, indent=4))
        info("Set WHATSAPP_WABA_ID + WHATSAPP_TOKEN in .env and re-run without --dry-run.")
        return

    if not waba_id:
        warn("WHATSAPP_WABA_ID not set.")
        info("Find it in Meta Business Manager -> WhatsApp -> API Setup -> WhatsApp Business Account ID.")
        info("Add WHATSAPP_WABA_ID=<id> to backend/.env and re-run.")
        return

    if not token:
        warn("WHATSAPP_TOKEN not set (need a permanent system user token).")
        return

    click.echo()
    async with httpx.AsyncClient(timeout=20) as client:
        for template in WHATSAPP_TEMPLATES:
            success, name, msg = await _submit_whatsapp_template(waba_id, token, template, client)
            if success:
                ok(f"{name} - {msg}")
            else:
                fail(f"{name} - {msg}")

    click.echo()
    info("Templates in PENDING status require Meta review (typically 1-24h).")
    info("Check status: https://business.facebook.com/wa/manage/message-templates/")


# ---------------------------------------------------------------------------

@cli.command("exotel-webhook")
@click.option("--dry-run", is_flag=True, help="Print config without applying.")
def cmd_exotel_webhook(dry_run: bool):
    """Register the Aurora /webhooks/exotel callback URL on your Exotel virtual number."""
    asyncio.run(_do_exotel_webhook(dry_run=dry_run))


async def _do_exotel_webhook(dry_run: bool = False) -> None:
    section("Exotel Webhook Configuration")

    sid = _env("EXOTEL_SID", required=False)
    api_key = _env("EXOTEL_API_KEY", required=False)
    api_token = _env("EXOTEL_API_TOKEN", required=False)
    subdomain = _env("EXOTEL_SUBDOMAIN", required=False)
    from_number = _env("EXOTEL_FROM_NUMBER", required=False)
    webhook_base = (_env("WEBHOOK_BASE_URL", required=False) or "").rstrip("/")
    webhook_url = f"{webhook_base}/webhooks/exotel"

    info(f"Webhook URL: {webhook_url}")

    if dry_run:
        warn("DRY RUN - configuration not applied.")
        info("This command POSTs to:")
        info(
            f"  https://<key>:<token>@{subdomain or '<EXOTEL_SUBDOMAIN>'}"
            f"/v1/Accounts/{sid or '<SID>'}"
            f"/IncomingPhoneNumbers/{from_number or '<FROM_NUMBER>'}.json"
        )
        info(f"  StatusCallback = {webhook_url}")
        return

    missing = [
        k for k, v in {
            "EXOTEL_SID": sid, "EXOTEL_API_KEY": api_key, "EXOTEL_API_TOKEN": api_token,
            "EXOTEL_SUBDOMAIN": subdomain, "EXOTEL_FROM_NUMBER": from_number,
        }.items() if not v
    ]
    if missing:
        for m in missing:
            warn(f"{m} not set.")
        info("Set all EXOTEL_* vars in .env and re-run.")
        return

    if not webhook_base:
        warn("WEBHOOK_BASE_URL not set.")
        return

    click.echo()
    success, err = await _configure_exotel_webhook(
        sid, api_key, api_token, subdomain, from_number, webhook_url
    )
    if success:
        ok(f"Exotel StatusCallback set to: {webhook_url}")
    else:
        fail(f"Exotel API error: {err}")
        info("Manual fallback - set in Exotel dashboard:")
        info("  My Virtual Numbers -> Select number -> Status Callback URL")
        info(f"  URL: {webhook_url}  |  Method: POST")


# ---------------------------------------------------------------------------

@cli.command("seed-prompt")
def cmd_seed_prompt():
    """Seed the initial ARIA v1 prompt into prompt_versions table."""
    asyncio.run(_do_seed_prompt())


async def _do_seed_prompt() -> None:
    section("Seed ARIA Prompt v1")

    supabase_url = _env("SUPABASE_URL")
    access_token = _env("SUPABASE_ACCESS_TOKEN", required=False)

    if not supabase_url:
        abort("SUPABASE_URL not set.")
        return

    project_ref = _project_ref_from_url(supabase_url)
    if not project_ref:
        abort(f"Cannot parse project ref from: {supabase_url}")
        return

    if not access_token:
        warn("SUPABASE_ACCESS_TOKEN not set - printing SQL instead.")
        click.echo()
        click.echo(PROMPT_SEED_SQL)
        info("Paste the SQL above into the Supabase SQL Editor.")
        return

    success, err = await _run_sql_via_management_api(project_ref, access_token, PROMPT_SEED_SQL)
    if success:
        ok("ARIA prompt v1 seeded (ON CONFLICT DO NOTHING).")
    else:
        fail(f"Seed failed: {err}")


# ---------------------------------------------------------------------------

@cli.command("init")
@click.option("--dry-run", is_flag=True, help="Print all actions without executing anything.")
@click.pass_context
def cmd_init(ctx: click.Context, dry_run: bool):
    """
    Full production setup - runs all steps in sequence:

      1. check                 (env vars + connectivity)
      2. supabase-migrate      (DDL migrations)
      3. seed-prompt           (ARIA v1 prompt)
      4. whatsapp-templates    (Meta template registration)
      5. exotel-webhook        (Exotel callback URL)
    """
    click.echo()
    click.echo(click.style("  Aurora 1.0 - Production Setup", bold=True, fg="bright_cyan"))
    click.echo(click.style("  Shango Revenue Systems", fg="cyan"))
    click.echo()

    if dry_run:
        warn("DRY RUN MODE - nothing will be modified.")
        click.echo()

    section("Step 1 / 5 - Environment Check")
    asyncio.run(_check_connectivity())

    section("Step 2 / 5 - Supabase Migrations")
    asyncio.run(_do_supabase_migrate(dry_run=dry_run))

    section("Step 3 / 5 - Seed ARIA Prompt")
    asyncio.run(_do_seed_prompt())

    section("Step 4 / 5 - WhatsApp Templates")
    asyncio.run(_do_whatsapp_templates(dry_run=dry_run))

    section("Step 5 / 5 - Exotel Webhook")
    asyncio.run(_do_exotel_webhook(dry_run=dry_run))

    click.echo()
    click.echo(click.style("-" * 64, fg="bright_black"))
    ok("Setup complete.")
    click.echo()
    info("Next steps:")
    click.echo("    1. Deploy backend to Render:        https://render.com")
    click.echo("    2. Deploy landing page to Vercel:   https://vercel.com")
    click.echo("    3. Set WEBHOOK_BASE_URL in Render env after first deploy")
    click.echo("    4. Push code to GitHub:              git push origin main")
    click.echo(
        "    5. Check WhatsApp template approval: "
        "https://business.facebook.com/wa/manage/message-templates/"
    )
    click.echo()


if __name__ == "__main__":
    cli()

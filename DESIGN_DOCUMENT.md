# Aurora 1.0 — Design Document

**Project**: Shango Revenue Systems  
**Codename**: Aurora 1.0  
**Version**: 1.1.0  
**Date**: February 2026  
**Status**: Complete (39 stories shipped — aurora-001 to aurora-026)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [System Architecture](#4-system-architecture)
5. [Component Deep-Dive](#5-component-deep-dive)
   - 5.1 [FastAPI Backend](#51-fastapi-backend)
   - 5.2 [AI Cascade Orchestrator](#52-ai-cascade-orchestrator)
   - 5.3 [Lead Scoring Engine](#53-lead-scoring-engine)
   - 5.4 [Vapi Voice Agent (ARIA)](#54-vapi-voice-agent-aria)
   - 5.5 [Post-Call Critique Engine](#55-post-call-critique-engine)
   - 5.6 [Self-Improvement Loop](#56-self-improvement-loop)
   - 5.7 [Database Layer (Supabase)](#57-database-layer-supabase)
   - 5.8 [Streamlit Dashboard](#58-streamlit-dashboard)
   - 5.9 [Next.js Landing Page](#59-nextjs-landing-page)
   - 5.10 [Lead Nurture Engine](#510-lead-nurture-engine-aurora-10)
   - 5.11 [OpenClaw Integration Summary](#511-openclaw-integration-summary)
   - 5.12 [MARS Self-Improvement Loop](#512-mars-self-improvement-loop)
   - 5.13 [Serper Enrichment Engine](#513-serper-enrichment-engine)
   - 5.14 [MCP Server](#514-mcp-server)
6. [Data Models](#6-data-models)
7. [Database Schema](#7-database-schema)
8. [API Reference](#8-api-reference)
9. [Infrastructure & Deployment](#9-infrastructure--deployment)
10. [Test Suite](#10-test-suite)
11. [The 0.01% Flywheel](#11-the-001-flywheel)
12. [Environment Variables](#12-environment-variables)
13. [Cost Model](#13-cost-model)
14. [Development Guide](#14-development-guide)
15. [Story Completion Log](#15-story-completion-log)

---

## 1. Executive Summary

Aurora 1.0 (branded as **Shango Revenue Systems**) is a fully autonomous AI Sales Development Representative (SDR) system. When a prospect fills out a form on the landing page, the system automatically:

1. **Scores** their fit (0–100) against the Ideal Customer Profile using AI, then **enriches** the score with real company data (employees, funding, LinkedIn) via Serper
2. **Calls** them via a Vapi AI voice agent within minutes
3. **Critiques** every call across 9 performance dimensions
4. **Self-improves** the agent prompt every 25 calls using meta-analysis (MARS loop)

Zero humans required in the loop. Zero missed follow-ups. The system gets measurably better with every call batch.

---

## 2. Problem Statement

Traditional B2B sales development suffers from three compounding failures:

| Failure | Real Cost |
|---------|-----------|
| Speed to lead | 35–50% of deals go to the first vendor who responds — median response time is 47 hours |
| Manual qualification | SDRs spend 60–70% of their time on leads that will never convert |
| No feedback loop | Call scripts never improve because nobody has time to review 100+ transcripts/week |

Aurora 1.0 eliminates all three simultaneously — and adds a fourth: lost pipeline recovery via automated nurture sequences.

---

## 3. Solution Overview

```
Prospect fills form
      ↓
AI scores them 0–100 in <1 second       ← 6-LLM cascade (Gemini→Groq→Cerebras→Mistral→DeepSeek→GPT-4o)
      ↓
Serper enriches the score               ← company lookup (+/-12 pts based on funding, headcount, LinkedIn)
      ↓
Vapi AI calls them within minutes       ← ARIA voice agent, geo-local caller ID
      ↓
Claude critiques the call (9 categories) ← pacing + silence_handling added in 1.0
      ↓
Results stored + pipeline updated       ← Supabase + geo_region tracking
      ↓
  ┌─────────────────────────────────────────┐
  │  Meeting booked?  │  Not booked?
  │  Done ✔           │  Nurture Sequence triggered
  └────────────────── └─ NurtureAgent (OpenClaw)
                         │    ↓ hot / warm / cold sequence
                         │    ↓ OpenClaw personalises each email
                         │    ↓ Brevo sends emails
                         │    ↓ Vapi follow-up calls (APScheduler, 15-min tick)
      ↓
Every 25 calls → MARS self-improvement  ← MCTS planner → Vapi PATCH
```

---

## 4. System Architecture

### 4.1 Full Request Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     LANDING PAGE (Next.js)                  │
│  Form: name, email, phone, company, lead_volume, message    │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /api/lead
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (Python)                  │
│                                                             │
│  1. score_lead()          → AI Cascade → LeadScore(0-100, tier)    │
│  1b. enrich_lead_score()  → Serper → CompanySignals + score adj.    │
│  2. upsert_lead() → Supabase leads table                            │
│  3. log_event()   → Supabase audit_log                      │
│  4. trigger_call() → POST Vapi API                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST (Vapi outbound call)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  VAPI AI VOICE AGENT (ARIA)                 │
│  - Customized system prompt with lead context               │
│  - Real-time voice conversation                             │
│  - Records transcript + audio                               │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /webhooks/vapi (end-of-call-report)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    WEBHOOK HANDLER                          │
│                                                             │
│  1. critique_call()  → 9-category AI analysis               │
│  2. insert_call()    → Supabase calls table                 │
│  3. update_lead_status() → Supabase leads table             │
│  4. insert_improvement() → Supabase agent_improvements      │
│  5. if not meeting_booked → NurtureAgent.create_sequence()  │
│  6. [if call_count % 25 == 0] → run_improvement_cycle()     │
└──────────────────────────┬──────────────────────────────────┘
                           │ (every 25 calls)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           MARS SELF-IMPROVEMENT LOOP (MCTS)                 │
│                                                             │
│  1. Fetch 25 recent calls + pending improvements            │
│  2. Meta-analysis via AI cascade                            │
│  3. Generate new complete Vapi system prompt                │
│  4. PATCH Vapi API with new prompt                          │
│  5. insert_prompt_version() → Supabase prompt_versions      │
│  6. mark_improvements_applied()                             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│             STREAMLIT COMMAND CENTER DASHBOARD              │
│  Overview KPIs | Pipeline | Call Center | Agent Brain | Nurture | Geo Analytics | Settings │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Service Topology

| Service | Tech | Port | Deploy Target |
|---------|------|------|---------------|
| Backend API | Python / FastAPI | 8000 | Render (web service) |
| Dashboard | Python / Streamlit | 8501 | Render (web service) |
| Landing Page | Next.js / TypeScript | 3000 | Vercel |
| MCP Server | Python / FastMCP | stdio / 8001 | Local — Claude Desktop, Cursor, VS Code |
| Database | PostgreSQL via Supabase | — | Supabase cloud |
| Voice Agent | Vapi | — | Vapi cloud |

---

## 5. Component Deep-Dive

### 5.1 FastAPI Backend

**File**: [backend/main.py](backend/main.py)

The application entry point. Responsibilities:

- **Lifespan handler**: On startup, logs availability of each API key (Gemini, Groq, Cerebras, Mistral, DeepSeek/OpenRouter, OpenAI, Vapi, Supabase) and starts the nurture APScheduler. Gracefully signals missing integrations without crashing.
- **CORS middleware**: Configurable via `ALLOWED_ORIGINS` env var (comma-separated). Defaults to `http://localhost:3000`.
- **TrustedHostMiddleware**: Available for production hardening.
- **Router registration**: Mounts `api.leads` (prefix `/api`), `api.webhooks` (prefix `/webhooks`), and `api.nurture` (prefix `/api/nurture`).
- **`GET /health`**: Calls `get_supabase_client()` (module-level, patchable by tests). Returns DB connectivity, AI cascade status, Vapi geo-number readiness, and `nurture_scheduler` (bool — whether APScheduler is still running). Returns `status: "degraded"` if Supabase is unreachable.
- **`GET /api/stats`**: Aggregates live KPIs — total leads, calls made, meetings booked, avg call score, conversion rate, total cost USD, pending improvements count, active prompt version.
- **`GET /api/provider-stats`**: Per-provider usage counters (calls, failures, avg latency) from the in-memory orchestrator stats map.

> **Implementation note**: `db/supabase.py` exports `get_supabase_client = get_supabase` as an alias. This allows tests to patch `db.supabase.get_supabase_client` while production code calls `get_supabase()` via `lru_cache`.

```
Startup log:
🛰  AURORA 1.0 booting up — 6-LLM · MARS · Geo-Routing · Nurture
  Gemini:     ✓
  Groq:       ✓
  Cerebras:   ✓
  Mistral:    ✓
  OpenRouter: ✓
  OpenAI:     ✓ (last resort)
  Claude:     ✓
  Vapi:       ✓
  Vapi IN:    ✓
  Vapi US:    ✓
  Vapi UK:    ✓
  Supabase:   ✓
```

### 5.2 AI Cascade Orchestrator

**File**: [backend/ai/orchestrator.py](backend/ai/orchestrator.py)

The most critical infrastructure component. All AI calls in the system go through this single function:

```python
await cascade_ai_call(prompt, system_prompt, task_type, max_tokens, use_cache)
```

#### Cascade Order (cost-optimized, 6 providers)

```
1. Gemini 2.0 Flash         — Free: 15 req/min, 1M token context     GEMINI_API_KEY
         ↓ (on failure)
2. Groq Llama 3.3 70B       — Free: 6,000 req/day, 128K context       GROQ_API_KEY
         ↓ (on failure)
3. Cerebras Llama 3.3 70B   — Free: 1M tokens/day, ultra-fast         CEREBRAS_API_KEY
         ↓ (on failure)
4. Mistral Small            — Free tier, strong multilingual support   MISTRAL_API_KEY
         ↓ (on failure)
5. DeepSeek V3 (OpenRouter) — Free: strong reasoning, 65K context      OPENROUTER_API_KEY
         ↓ (on failure)
6. GPT-4o-mini              — ~$0.15/M tokens (true last resort)       OPENAI_API_KEY
```

Each provider is only tried if the previous one raises an exception. All failures are logged at `WARNING` level. With 6 providers, effective downtime is essentially zero.

#### 24-Hour In-Memory Cache

```python
_cache: dict[str, tuple[str, datetime]] = {}
CACHE_TTL = timedelta(hours=24)
```

- Key: `SHA-256(task_type + ":" + prompt)[:32]`
- Max 1,000 entries — oldest 100 evicted when full
- Disabled per-call by setting `use_cache=False` (used for scoring, critique, and improvement — all unique per request)

#### `humanize_text(text)`

Strips JSON markers, markdown fences, and normalizes output before returning to callers.

#### `parse_json_response(raw)`

Robust JSON extractor that strips `\`\`\`json` fences, trailing garbage, and validates structure before returning.

### 5.3 Lead Scoring Engine

**File**: [backend/ai/scoring.py](backend/ai/scoring.py)

Scores every inbound lead 0–100 against the company's Ideal Customer Profile.

#### ICP Definition (embedded in system prompt)

- **Target titles**: Founder, CEO, Head of Sales, VP Sales, CRO
- **Company size**: 2–200 employees
- **Lead volume**: 50+ leads/month
- **Pain**: Manual outreach, low conversion, no follow-up
- **Budget signals**: Paid tools, mentions of scale challenges

#### Scoring Rubric

| Range | Tier | Meaning |
|-------|------|---------|
| 80–100 | HIGH | Perfect ICP, clear pain, decision-maker, ready to buy |
| 50–79 | MEDIUM | Partial fit, some pain, possible decision-maker |
| 0–49 | LOW | Poor fit, no pain, not a decision-maker |

#### Prompting Strategy

Uses **few-shot Chain-of-Thought** prompting: 3 example leads with correct scoring are embedded in the prompt, followed by the actual lead. The model reasons step-by-step before committing to a JSON answer.

#### Output Schema

```json
{
  "score": 88,
  "tier": "high",
  "reasoning": "CEO of growing company, 200+ leads, explicit pain point about manual work",
  "icp_fit": "Strong — decision maker, right volume, clear pain",
  "urgency": "High — 'burning' language, resource waste",
  "budget_signals": "Company already doing outreach, willing to invest"
}
```

#### Fail-Open Behavior

If AI scoring fails for any reason, the system returns a default score of 30/LOW rather than crashing. The lead is still stored and can be rescored manually.

#### Serper Enrichment

Immediately after initial AI scoring, `enrich_lead_score()` in [backend/ai/enrichment.py](backend/ai/enrichment.py) fires a Serper company search. Real-world signals (funding round, employee count, LinkedIn presence) adjust the raw score by −12 to +17 points before the lead is stored. See [§5.13 Serper Enrichment Engine](#513-serper-enrichment-engine) for full details.

### 5.4 Vapi Voice Agent (ARIA)

**Function**: `trigger_call()` in [backend/ai/improvement.py](backend/ai/improvement.py)

The outbound call trigger makes a POST to `https://api.vapi.ai/call/phone` with:

> **Geo-routing**: `phoneNumberId` is resolved by `_get_phone_number_id(lead.phone)` — automatically selects `VAPI_PHONE_NUMBER_ID_IN` (+91 prefixes), `VAPI_PHONE_NUMBER_ID_US` (+1), `VAPI_PHONE_NUMBER_ID_UK` (+44), or `VAPI_PHONE_NUMBER_ID_GLOBAL` (all others). Local caller ID improves answer rates by ~40%.

```json
{
  "assistantId": "<VAPI_ASSISTANT_ID>",
  "phoneNumberId": "<VAPI_PHONE_NUMBER_ID>",
  "customer": {
    "number": "<lead_phone>",
    "name": "<lead_name>"
  },
  "assistantOverrides": {
    "variableValues": {
      "lead_name": "Sarah Chen",
      "company": "TechStartup Inc",
      "pain_hint": "Manual outreach eating 40hrs/week",
      "lead_score": "88",
      "tier": "high"
    }
  },
  "metadata": {
    "lead_email": "sarah@techstartup.com",
    "lead_name": "Sarah Chen",
    "lead_score": 88,
    "lead_tier": "high",
    "company": "TechStartup Inc",
    "pain_hint": "Original message text"
  }
}
```

The `metadata` object is passed back verbatim in the `end-of-call-report` webhook, enabling the critique engine to access the original lead context without a DB lookup.

**Graceful degradation**: If `VAPI_API_KEY` or `VAPI_ASSISTANT_ID` is not set, `trigger_call()` logs a warning and returns `None`. The lead status is set to `follow_up_needed` instead of crashing.

### 5.5 Post-Call Critique Engine

**File**: [backend/ai/critique.py](backend/ai/critique.py)

Every call gets deeply analyzed across 9 categories immediately after the call ends.

#### 9 Scoring Dimensions (0–100 each)

| Category | What It Measures |
|----------|-----------------|
| `opening` | First impression, hook, permission to continue |
| `discovery` | Pain uncovering, question quality, active listening |
| `rapport` | Conversational feel, not robotic |
| `objection_handling` | Graceful, empathetic, redirects well |
| `closing` | Clear ask, calendar-focused, specific next steps |
| `naturalness` | Sounds human, not scripted |
| `relevance` | Responses tied to what the prospect actually said |
| `pacing` | *(Aurora 1.0)* Speaking tempo, pauses, not rushing the prospect |
| `silence_handling` | *(Aurora 1.0)* Comfortable with silence; doesn't panic-fill |
| `overall` | Weighted composite of all 9 dimensions |

#### Critique Outputs

Beyond scores, the critique engine extracts:

- `meeting_booked` (bool): Was a meeting scheduled?
- `should_follow_up` (bool): Worth pursuing further?
- `follow_up_strategy`: `email | call | whatsapp | sms | none`
- `estimated_deal_probability` (0–100)
- `one_line_summary`: One sentence on what happened
- `coach_verdict`: What the AI did well and what to fix
- `prospect_analysis`:
  - `pain_points[]`: List of pains expressed by the prospect
  - `buying_stage`: `awareness | consideration | decision | unknown`
  - `sentiment_overall`: `positive | neutral | negative | hostile`
  - `budget_signals`: Budget-related statements from the call
  - `objections_raised[]`: Specific objections heard
- `action_items[]`: Specific next actions to take
- `script_improvements[]`: Each improvement has `category`, `current_behavior`, `suggested_behavior`, `example_script`, `impact`

#### Analyst Persona

The system prompt gives the AI the persona of "an elite sales call analyst with 20 years of experience training SDR teams at companies like Salesforce, Gong, and Outreach." Honest scoring — 70+ means genuinely good, below 40 means immediate fixes needed.

#### Minimum Transcript Guard

If the transcript is under 50 characters, critique is skipped and an empty critique object is returned rather than wasting tokens.

### 5.6 Self-Improvement Loop

**File**: [backend/ai/improvement.py](backend/ai/improvement.py)

The system's most innovative feature — it rewrites its own Vapi agent prompt automatically.

#### Trigger

The improvement cycle fires in `webhooks.py` after each `end-of-call-report`:
```python
recent_calls = await get_calls_since(days=90)
if len(recent_calls) >= MARS_CYCLE_THRESHOLD and len(recent_calls) % MARS_CYCLE_THRESHOLD == 0:
    await run_improvement_cycle(n_calls=MARS_CYCLE_THRESHOLD)
```

This fires on the 25th call, 50th, 75th, etc. — exactly once per completed batch, never on every call once the threshold is passed. `MARS_CYCLE_THRESHOLD` is imported from `ai.mars` (not redefined locally). It can also be triggered manually via `POST /webhooks/trigger-improvement` with an admin secret.

#### Cycle Steps

```
1. Fetch last 25 call records from Supabase
2. Fetch all pending improvements (status = pending_review)
3. Fetch current active Vapi prompt from prompt_versions
4. Build meta-analysis prompt:
   - Score distribution breakdown
   - Call summaries (one-liners + coach verdicts)
   - Pending script improvements
   - Common failure category frequencies
5. Run AI meta-analysis (cascade_ai_call, task_type="self_improvement")
6. Parse:
   - Top 3 patterns causing low scores
   - Complete new system prompt (min 500 words)
   - Changelog of specific changes
   - Expected improvement metrics
7. PATCH Vapi API: PUT https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}
8. insert_prompt_version() → Supabase (deactivates previous, increments version)
9. mark_improvements_applied() for all consumed improvements
```

#### Meta-Analysis Persona

"You are a VP of Sales Operations with deep expertise in AI SDR optimization." Rules enforced in the prompt:
- Only fix patterns appearing in 3+ calls (no overfitting)
- New prompt must be complete and deployable (not a diff)
- Changelog must be specific and measurable

#### Prompt Versioning

Every prompt version is stored in `prompt_versions` with:
- `version` (integer, auto-incremented)
- `prompt_text` (full content)
- `changelog` (what changed and why)
- `based_on_calls` (how many calls drove this version)
- `avg_score_before` / `avg_score_after` (for measuring improvement)
- `is_active` (only one active at a time)

### 5.7 Database Layer (Supabase)

**File**: [backend/db/supabase.py](backend/db/supabase.py)

All database operations are centralized in this module. No direct Supabase client calls anywhere else in the codebase.

#### Client Initialization

```python
@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

Uses the **service role key** (bypasses Row Level Security) for backend operations. The anon key is reserved for the frontend landing page.

#### Operations by Domain

**Leads**
- `upsert_lead(data)` — upsert on `email` conflict (deduplication)
- `get_lead_by_email(email)` — fetch single lead
- `update_lead_status(email, updates)` — update status and other fields

**Calls**
- `insert_call(data)` — store complete call record with critique
- `get_recent_calls(limit=50)` — ordered by `created_at DESC`
- `get_calls_since(days=7)` — time-bounded query

**Improvements**
- `insert_improvement(data)` — queue a script improvement
- `get_pending_improvements()` — fetch all `pending_review` sorted by impact
- `mark_improvements_applied(ids)` — bulk update status to `applied`

**Prompt Versions**
- `get_active_prompt()` — fetch the current `is_active=True` prompt
- `insert_prompt_version(data)` — deactivate all others, insert new active version

**Audit Log**
- `log_event(event_type, entity_id, entity_type, payload)` — immutable event trace

### 5.8 Streamlit Dashboard

**File**: [dashboard/dashboard.py](dashboard/dashboard.py)

A 7-page dark-themed command center built on Streamlit + Plotly.

#### Dark Theme

Custom CSS targeting `.stApp`, `.metric-card`, `.lead-card`, `.status-badge`, and score bars gives the dashboard a deep space aesthetic with purple/blue gradients on a `#07070E` background.

#### Pages

| Page | Content |
|------|---------|
| **Overview** | KPI cards: Total Leads, Calls Made, Meetings Booked, Avg Call Score, Conversion Rate, Total Cost. Plotly line chart showing lead volume over time. |
| **Pipeline** | Lead table with status badges (color-coded), score bars, tier badges. Filter by tier/status. |
| **Call Center** | Call records with transcript viewer, per-call scores across 9 categories, radar chart of performance dimensions, pacing and silence-handling bars. |
| **Agent Brain** | Prompt version history, active prompt viewer, improvement suggestions queue, MARS lesson viewer, trigger manual improvement cycle button. |
| **Nurture** | Active nurture sequences, per-lead step progress, sequence type badges (hot/warm/cold), pause/resume controls. |
| **Geo Analytics** | Call answer rates by region (IN/US/UK/Global), phone-number-ID routing map, geo breakdown of meeting conversion rates. |
| **Settings** | Environment health check, API connectivity status, Supabase table row counts. |

#### Data Fetching

```python
@st.cache_data(ttl=30)     # 30-second refresh cache
def fetch_leads():
    r = sb.table("leads").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(r.data or [])
```

All data fetchers use `@st.cache_data(ttl=30)` to avoid hammering Supabase on every render cycle. Supabase client uses `@st.cache_resource` for singleton sharing across sessions.

### 5.9 Next.js Landing Page

**Files**: [landing/src/app/page.tsx](landing/src/app/page.tsx), [landing/src/app/globals.css](landing/src/app/globals.css), [landing/src/app/layout.tsx](landing/src/app/layout.tsx)

A single-page lead capture form built in Next.js 15 (App Router), TypeScript, no external UI libraries.

#### User Flow

1. Hero: "Stop Losing Leads. Let AI Close Them." headline + 4 trust badges
2. Form: Name \*, Email \*, Country (auto-detected from `navigator.language`), Phone, Company, Lead Volume \* (1–10 / 10–50 / 50–200 / 200+), Message
3. Submit → spinner + "Scoring your lead…" → `POST /api/lead` → success score card

#### Country Geo-Detection

`detectCountry()` reads `navigator.language` on the client and maps to IN / US / UK / AU / SG / OTHER. The selected country pre-fills the phone prefix and shows a geo-trust message (e.g., *"📞 Mumbai local call in <5 min"*).

#### Loading State

Disables button, renders an inline CSS spinner (`@keyframes spin`) with the label **"Scoring your lead…"**.

#### Success Score Card

Replaces the form on success:

- **Animated SVG ring gauge**: `stroke-dashoffset` CSS animation (`spin-in`, 1.2s ease-in-out) draws the score arc from 0 to `score/100 × 2πR`. Stroke color matches score (green ≥70, amber ≥45, red <45).
- **Tier badge**: gradient backgrounds (HIGH=`#065F46→#064E3B`, MEDIUM=`#78350F→#92400E`, LOW=`#1F2937`). HIGH tier gets a `pulse-ring` breathing animation.
- **Dynamic ETA line** from `TIER_ETA` map:
  - `high` → "📞 Expect a call in < 5 minutes."
  - `medium` → "📞 Expect a call within 15 minutes."
  - `low` → "📞 Expect a call within 60 minutes."
- **Breakdown row**: ICP Fit / Urgency / Lead Score derived from score + tier.
- **"Submit another lead"** ghost button resets state.

#### Styling

Inline `React.CSSProperties` objects throughout. `globals.css` provides `@keyframes spin` for the button spinner. Background `#07070E` matches dashboard.

---

### 5.10 Lead Nurture Engine (Aurora 1.0)

**Files**: `backend/nurture/agent.py`, `backend/nurture/templates.py`, `backend/nurture/scheduler.py`

When a call ends without a meeting booked, the NurtureAgent automatically enrolls the lead in a personalised multi-step sequence of emails, WhatsApp messages, and Exotel outbound calls.

#### Sequence Tiers

| Tier | Score | Steps (delay = hours from sequence creation) |
|------|-------|----------------------------------------------|
| `hot_nurture` | ≥60 | 0h email → +24h WhatsApp (`hot_day1`) → +24h Exotel call → +72h email → +168h final email |
| `warm_nurture` | 40–59 | 0h email → +24h WhatsApp (`warm_day1`) → +96h email → +168h Exotel call → +336h final email |
| `cold_nurture` | <40 | +48h email → +96h WhatsApp (`cold_day4`) → +168h email → +336h WhatsApp reactivation |

All delays are **absolute from sequence creation time**, not relative to the previous step. The scheduler checks every 15 minutes and fires any step whose `scheduled_at` has passed.

#### WhatsApp Delivery (Meta Business API)

WhatsApp messages use the Meta WhatsApp Business Cloud API (`graph.facebook.com/v20.0`). Template messages must be pre-approved by Meta; Aurora uses the prefix `shango_` for all templates:

```python
payload = {
    "messaging_product": "whatsapp",
    "to": phone,
    "type": "template",
    "template": {
        "name": f"shango_{template}",   # e.g. shango_hot_day1
        "language": {"code": "en_US"},
        "components": [{"type": "body", "parameters": [
            {"type": "text", "text": lead_first_name},    # {{1}}
            {"type": "text", "text": company_name},        # {{2}}
            {"type": "text", "text": pain_point},          # {{3}}
        ]}],
    },
}
```

If `WHATSAPP_PHONE_ID` or `WHATSAPP_TOKEN` are absent, the step dry-runs and logs the payload — it does **not** block the sequence.

**Templates that must be approved in Meta Business Manager:**

| Template name | Used in |
|---------------|---------|
| `shango_hot_day1` | hot_nurture step 1 |
| `shango_hot_immediate` | hot_nurture step 0 (email, but WhatsApp variant optional) |
| `shango_warm_day1` | warm_nurture step 1 |
| `shango_cold_day4` | cold_nurture step 1 |
| `shango_cold_reactivation` | cold_nurture step 3 |

#### Exotel Outbound Calls

Outbound calls use the Exotel Click-to-Call API with basic auth embedded in the request URL:

```
POST https://{EXOTEL_API_KEY}:{EXOTEL_API_TOKEN}@{EXOTEL_SUBDOMAIN}/v1/Accounts/{EXOTEL_SID}/Calls/connect.json
```

Payload: `From=EXOTEL_FROM_NUMBER`, `To=lead_phone`, `Url={WEBHOOK_BASE_URL}/webhooks/exotel`, `Method=POST`. Exotel POSTs call status updates back to `/webhooks/exotel` (not yet implemented — see Manual Steps).

#### OpenClaw Agent Orchestration

Each nurture email is personalised by the OpenClaw SDK (`pip install openclaw`), an AI agent SDK for email personalisation with cascade fallback.

```python
from openclaw import AsyncCMDOPClient, AgentRunOptions, AgentRunRequest

async with AsyncCMDOPClient.local() as client:
    result = await client.run(AgentRunRequest(
        prompt=personalization_prompt,
        options=AgentRunOptions(model="auto", max_tokens=300),
    ))
personalised_body = result.output
```

If the OpenClaw daemon is not running, falls back transparently to `cascade_ai_call()`.

#### Email Delivery (Brevo)

Personalised emails are sent via the Brevo REST API (`BREVO_API_KEY`). HTML is wrapped in a branded dark-theme template with a “Book a 15-min call” CTA and unsubscribe footer.

#### Background Scheduler (APScheduler)

An `AsyncIOScheduler` runs every 15 minutes and calls `advance_sequence()` for every active nurture sequence. Started in the FastAPI lifespan, gracefully stopped on shutdown.

#### API Surface

| Endpoint | Description |
|----------|-------------|
| `GET /api/nurture/sequences` | List all sequences (paginated) |
| `GET /api/nurture/sequences/{email}` | Get sequence for a lead |
| `POST /api/nurture/sequences` | Manually enrol a lead |
| `POST /api/nurture/sequences/{id}/pause` | Pause a sequence |
| `POST /api/nurture/sequences/{id}/resume` | Resume a sequence |
| `DELETE /api/nurture/sequences/{id}` | Deactivate a sequence |
| `GET /api/nurture/stats` | Pipeline summary stats |

---

### 5.11 OpenClaw Integration Summary

OpenClaw (`pip install openclaw`) is a lightweight Python AI agent SDK for email personalisation. In Aurora 1.0 it powers the **email personalisation step** inside every nurture sequence.

**Why OpenClaw?**
- Simple `AgentRunRequest` / `AgentResult` API — wraps any LLM endpoint
- Graceful fallback to `cascade_ai_call()` ensures zero downtime when daemon is offline
- Keeps the nurture engine independently upgradeable as an "agent node"
- Drop-in replacement path to more advanced orchestration without touching the rest of the system

**Integration point**: `backend/nurture/agent.py` → `_openclaw_personalize()`

---

### 5.12 MARS Self-Improvement Loop

**File**: [backend/ai/improvement.py](backend/ai/improvement.py)

**MARS** (Meta-Analysis Reinforcement System) is Aurora 1.0's continuous self-improvement engine. Every 25 calls it runs an MCTS-guided planning pass, selects the highest-leverage prompt changes, and patches the live Vapi assistant.

#### MCTS Planner

```python
@dataclass
class MCTSNode:
    module: str       # "opening" | "discovery" | "objection_handling" | ...
    action: str       # Proposed prompt change description
    reward: float     # Expected score delta (0–1)
    compute_cost: float  # Relative token cost (0–1)
    children: list["MCTSNode"]
```

The planner scores each candidate change as `reward / compute_cost` and selects the top-N actions that fit within a **60-minute compute budget** (tunable via `MARS_BUDGET_MINUTES` env var).

#### Trigger

```python
MARS_CYCLE_THRESHOLD = 25   # calls between improvement cycles

if call_count % MARS_CYCLE_THRESHOLD == 0:
    await run_improvement_cycle()
```

#### Cycle Steps

```
1. Fetch last 25 call records + pending script improvements
2. Run MCTS planner → ranked MCTSNode list
3. cascade_ai_call() → module-level prompt diff (task_type="self_improvement")
4. insert_mars_lesson() → Supabase mars_lessons table
5. _update_vapi_assistant() → PATCH Vapi API with full new system prompt
6. insert_prompt_version() → Supabase prompt_versions (deactivates previous)
7. mark_improvements_applied() for all consumed improvements
```

#### `mars_lessons` Table Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid | Primary key |
| `created_at` | timestamptz | When lesson was generated |
| `call_batch_start` | int | First call in the batch |
| `call_batch_end` | int | Last call in the batch |
| `patterns_found` | jsonb | Top patterns from meta-analysis |
| `prompt_diff` | text | Changelog of specific changes |
| `avg_score_before` | float | Average score of the batch |
| `avg_score_after` | float | Measured score of next batch (backfilled) |
| `mcts_nodes` | jsonb | Full MCTSNode tree serialized |
| `was_applied` | bool | Whether patch was pushed to Vapi |

---

### 5.13 Serper Enrichment Engine

**File**: [backend/ai/enrichment.py](backend/ai/enrichment.py)

After the 6-LLM cascade scores a lead, `enrich_lead_score()` fires a real-time Serper company search to validate the score against real-world signals before the lead is stored.

#### Flow

```
score_lead()        →  raw_score (AI only)
      ↓
company_lookup()    →  POST https://google.serper.dev/search
                        X-API-KEY: SERPER_API_KEY
      ↓
_parse_serper_response()  →  CompanySignals dataclass
      ↓
_adjust_score()     →  enriched_score (clamped 0–100, tier recalculated)
      ↓
enrich_lead_score() →  (LeadScore, CompanySignals)   [fail-open]
```

#### `CompanySignals` Dataclass

```python
@dataclass
class CompanySignals:
    found: bool = False
    employee_range: str = ""   # "2-10"|"10-50"|"50-200"|"200+"|"unknown"
    has_funding: bool = False
    has_linkedin: bool = False
    is_large_enterprise: bool = False
    is_student_or_freelancer: bool = False
    industry_signals: list[str] = field(default_factory=list)
    raw_snippets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict: ...
```

#### Score Adjustment Rules

| Signal | Delta | Rationale |
|--------|-------|-----------|
| `has_funding` | +10 | Funded company buys tools |
| `has_linkedin` | +7 | Verified legitimate business |
| `employee_range` 10–200 | +8 | ICP sweet spot |
| `employee_range` 2–10 | +3 | Small team, still buys |
| `is_large_enterprise` | −8 | Outside ICP (complex procurement) |
| `is_student_or_freelancer` | −12 | Disqualifying signal |
| `not found` | −5 | Unverifiable company |

The final score is clamped to 0–100 and the tier recalculated using the same thresholds as initial scoring.

#### Fail-Open Guarantee

If Serper returns an error or the `SERPER_API_KEY` is absent, `enrich_lead_score()` returns the original unmodified `LeadScore` and an empty `CompanySignals`. The lead submission never fails due to enrichment.

#### Audit Trail

`log_event()` records both the `initial_score` and `enriched_score` with the full `serper_signals` payload, so score deltas are fully auditable in the `audit_log` table.

---

### 5.14 MCP Server

**File**: [backend/mcp_server.py](backend/mcp_server.py)

An MCP (Model Context Protocol) server that exposes Aurora’s full pipeline as tools and resources. Any MCP-compatible AI assistant — Claude Desktop, Cursor, GitHub Copilot, custom agents — can score leads, inspect calls, manage nurture sequences, and trigger self-improvement cycles directly.

#### Transport

- **stdio** (default) — for Claude Desktop and Cursor integration
- **SSE** (`--sse --port 8001`) — for browser-based or remote agent clients

The MCP server talks to the running Aurora FastAPI backend at `AURORA_BACKEND_URL` (default `http://localhost:8000`). It does **not** re-implement any business logic; all calls proxy to existing Aurora endpoints or read directly from Supabase for read-only queries.

#### Tools (13)

| Tool | Description |
|------|-------------|
| `score_and_enrich_lead` | AI-score + Serper-enrich a prospect. Returns score, tier, ICP fit, delta, and company signals. Does NOT trigger a call. |
| `get_lead` | Fetch full lead record by email |
| `search_leads` | Filter pipeline by tier / status / score range |
| `get_pipeline_stats` | Live KPIs: total_leads, calls_made, meetings_booked, avg_score, conversion_rate, cost |
| `list_recent_calls` | Last N calls with all 9 scores and critique summaries |
| `get_call_detail` | Full critique object for a specific call_id |
| `get_nurture_sequence` | Nurture status + step array for a lead |
| `enrol_lead_in_nurture` | Manually start a hot / warm / cold nurture sequence |
| `pause_nurture_sequence` | Pause an active sequence by sequence_id |
| `list_mars_lessons` | Recent MARS improvement cycles with patterns + score deltas |
| `get_active_prompt` | Current live ARIA system prompt with changelog |
| `trigger_improvement_cycle` | Manually fire the MARS cycle (requires `ADMIN_SECRET`) |
| `health_check` | System health: DB, AI cascade, Vapi geo-numbers, scheduler |

#### Resources (4)

| URI | Description |
|-----|-------------|
| `aurora://stats` | Live KPI payload as JSON |
| `aurora://leads/recent` | 50 most recent leads |
| `aurora://prompt/active` | Active ARIA prompt with version header |
| `aurora://health` | Health check payload |

#### Claude Desktop Config

```json
{
  "mcpServers": {
    "aurora-sdr": {
      "command": "python",
      "args": ["path/to/aurora-0.01/backend/mcp_server.py"]
    }
  }
}
```

#### Cursor MCP Config (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "aurora-sdr": {
      "command": "python",
      "args": ["backend/mcp_server.py"],
      "cwd": "path/to/aurora-0.01"
    }
  }
}
```

---

## 6. Data Models

**File**: [backend/models.py](backend/models.py)

### `CompanySignals` (Enrichment)

Returned by `enrich_lead_score()` in `backend/ai/enrichment.py`. Serialized to `enrichment_signals JSONB` in the `leads` table.

```python
@dataclass
class CompanySignals:
    found: bool = False
    employee_range: str = ""   # "2-10"|"10-50"|"50-200"|"200+"|"unknown"
    has_funding: bool = False
    has_linkedin: bool = False
    is_large_enterprise: bool = False
    is_student_or_freelancer: bool = False
    industry_signals: list[str] = field(default_factory=list)
    raw_snippets: list[str] = field(default_factory=list)
```

### Enums

```python
class LeadTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"  
    LOW = "low"
    UNSCORED = "unscored"

class LeadStatus(str, Enum):
    NEW = "new"
    CALL_INITIATED = "call_initiated"
    CALL_COMPLETED = "call_completed"
    MEETING_BOOKED = "meeting_booked"
    FOLLOW_UP_NEEDED = "follow_up_needed"
    NURTURE_QUEUE = "nurture_queue"
    CLOSED_LOST = "closed_lost"
    NOT_ACTIVE = "not_active"

class ImprovementImpact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ImprovementStatus(str, Enum):
    PENDING = "pending_review"
    APPLIED = "applied"
    REJECTED = "rejected"
```

### Request/Response Models

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `LeadCreate` | Inbound form POST | name, email, phone, company, lead_volume, message |
| `LeadScore` | AI scoring result | score (0-100), tier, reasoning, icp_fit, urgency, budget_signals |
| `LeadResponse` | API response to landing page | id, status, score, tier, message |
| `CallScores` | 9-dimensional scores | opening, discovery, rapport, objection_handling, closing, naturalness, relevance, pacing, silence_handling, overall |
| `ScriptImprovement` | Single improvement suggestion | category, current_behavior, suggested_behavior, example_script, impact |
| `ProspectAnalysis` | Prospect intelligence | pain_points[], buying_stage, sentiment_overall, budget_signals, objections_raised[] |
| `CallCritique` | Full AI critique | call_id, scores, meeting_booked, follow_up strategy, prospect_analysis, action_items, improvements |
| `PromptUpdate` | New prompt from improvement cycle | version, prompt_text, changelog, patterns |
| `DashboardStats` | `/api/stats` response | All KPI fields |

---

## 7. Database Schema

**File**: [supabase/schema.sql](supabase/schema.sql)

### Table: `leads`

```sql
id            UUID PRIMARY KEY
name          TEXT NOT NULL
email         TEXT UNIQUE NOT NULL        -- Deduplication key
phone         TEXT
company       TEXT
lead_volume   TEXT                        -- "1-10", "10-50", "50-200", "200+"
message       TEXT
score         INTEGER (0-100)
tier          TEXT ('high','medium','low','unscored')
score_reasoning TEXT
status        TEXT                        -- See LeadStatus enum
pain_points   JSONB DEFAULT '[]'          -- Post-call enrichment
deal_probability INTEGER DEFAULT 0
buying_stage  TEXT
last_call_score INTEGER DEFAULT 0
follow_up_type TEXT
next_touch_at TIMESTAMPTZ
source        TEXT DEFAULT 'landing_page'
icp_fit       BOOLEAN DEFAULT FALSE       -- Serper: ICP-sized team confirmed
budget_signals JSONB DEFAULT '[]'         -- Serper: funding / scale signals
enrichment_signals JSONB DEFAULT '{}'     -- Full CompanySignals payload
created_at    TIMESTAMPTZ DEFAULT NOW()
updated_at    TIMESTAMPTZ DEFAULT NOW()
```

Indexes: `status`, `tier`, `created_at DESC`

### Table: `calls`

```sql
id                UUID PRIMARY KEY
call_id           TEXT UNIQUE             -- Vapi call ID
lead_email        TEXT → leads(email)
transcript        TEXT
recording_url     TEXT
duration_seconds  INTEGER
cost_usd          NUMERIC(8,4)
ended_reason      TEXT
-- 10 AI critique scores (0-100 each)
overall_score, opening_score, discovery_score, rapport_score,
objection_score, closing_score, naturalness_score, relevance_score,
pacing_score, silence_handling_score
-- Outcomes
meeting_booked    BOOLEAN
should_follow_up  BOOLEAN
follow_up_strategy TEXT CHECK (follow_up_strategy IN ('email','call','whatsapp','sms','none'))
-- Structured JSONB
pain_points       JSONB
action_items      JSONB
script_improvements JSONB
full_critique     JSONB                   -- Complete critique object
-- Insights
one_line_summary  TEXT
sentiment         TEXT
buying_stage      TEXT
deal_probability  INTEGER
created_at        TIMESTAMPTZ
```

Indexes: `lead_email`, `created_at DESC`, `overall_score DESC`

### Table: `agent_improvements`

```sql
id                UUID PRIMARY KEY
improvement_type  TEXT                    -- 'script','objection','opening','closing'
source_call_id    TEXT                    -- Vapi call ID that generated this
current_behavior  TEXT
suggested_behavior TEXT
example_script    TEXT
impact            TEXT ('high','medium','low')
status            TEXT ('pending_review','applied','rejected')
created_at        TIMESTAMPTZ
```

Indexes: `status`, `impact`

### Table: `prompt_versions`

```sql
id                UUID PRIMARY KEY
version           INTEGER UNIQUE          -- Auto-incremented
prompt_text       TEXT NOT NULL           -- Complete Vapi system prompt
changelog         TEXT                    -- What was changed and why
based_on_calls    INTEGER                 -- How many calls drove this version
avg_score_before  NUMERIC(5,2)
avg_score_after   NUMERIC(5,2)
is_active         BOOLEAN                 -- Only one true at a time
created_at        TIMESTAMPTZ
```

Seeded in schema.sql with `version=1` — the initial ARIA sales agent prompt.

### Table: `audit_log`

```sql
id          UUID PRIMARY KEY
event_type  TEXT                          -- 'lead_scored','call_initiated','critique_run','prompt_updated'
entity_id   TEXT                          -- The lead email or call ID
entity_type TEXT                          -- 'lead' | 'call' | 'prompt'
payload     JSONB                         -- Full event context
created_at  TIMESTAMPTZ
```

Immutable governance trace. Never updated, only inserted.

Indexes: `event_type`, `created_at DESC`

### Table: `daily_stats`

Pre-aggregated daily metrics for fast dashboard time-series queries. Avoids full table scans on high-volume data.

### Table: `nurture_sequences`

Stores every lead nurture sequence and its individual steps.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | Auto-generated |
| `lead_email` | TEXT | Lead email (FK to leads) |
| `lead_name` | TEXT | Lead display name |
| `lead_company` | TEXT | Company name |
| `lead_score` | INTEGER | Score at time of enrolment |
| `phone` | TEXT | Phone for call steps |
| `pain_points` | JSONB | Array of pain points from critique |
| `call_summary` | TEXT | One-line call summary |
| `geo_region` | TEXT | `india` / `us` / `uk` / `global` |
| `sequence_type` | TEXT | `hot_nurture` / `warm_nurture` / `cold_nurture` |
| `current_step` | INTEGER | Index of the last executed step |
| `steps` | JSONB | Full step array with `scheduled_at` / `status` / `result` |
| `is_active` | BOOLEAN | False = paused or cancelled |
| `completed` | BOOLEAN | True = all steps done |
| `created_at` | TIMESTAMPTZ | Enrolment timestamp |
| `last_action_at` | TIMESTAMPTZ | Last step execution |

RLS enabled. Service role key bypasses for backend writes.

### Table: `mars_lessons`

Stores every MARS improvement cycle run. Backfilled with `avg_score_after` once the next batch of calls completes.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | Primary key |
| `created_at` | TIMESTAMPTZ | When lesson was generated |
| `call_batch_start` | INTEGER | First call number in the batch |
| `call_batch_end` | INTEGER | Last call number in the batch |
| `patterns_found` | JSONB | Top patterns from meta-analysis |
| `prompt_diff` | TEXT | Changelog of specific changes made |
| `avg_score_before` | FLOAT | Average score of the triggering batch |
| `avg_score_after` | FLOAT | Measured score of next batch (backfilled) |
| `mcts_nodes` | JSONB | Full MCTSNode tree serialized |
| `was_applied` | BOOLEAN | Whether patch was pushed to Vapi |

Indexes: `created_at DESC`, `was_applied`

---

## 8. API Reference

### `POST /api/lead`

Receive an inbound lead, score it, and trigger an outbound call.

**Request body** (`LeadCreate`):
```json
{
  "name": "Sarah Chen",
  "email": "sarah@techstartup.com",
  "phone": "+14155551234",
  "company": "TechStartup Inc",
  "lead_volume": "200+",
  "message": "We're burning 40 hours/week on manual outreach"
}
```

**Response** (`LeadResponse`):
```json
{
  "id": "uuid",
  "status": "received",
  "score": 88,
  "tier": "high",
  "message": "Thanks Sarah! We'll be in touch shortly."
}
```

**Side effects**: 
1. AI scores lead (6-LLM cascade)
2. Serper enriches score with company signals (+/−12 pts, fail-open)
3. Supabase upsert (`enrichment_signals` column included)
4. Audit log entry (records `initial_score`, `enriched_score`, `score_delta`, `serper_signals`)
5. Vapi call trigger (if phone provided, respects `recommended_delay_minutes`)

---

### `POST /webhooks/vapi`

Receive Vapi call events. Handles `end-of-call-report`, `call-started`, `status-update`, and unknown types.

**Security**: Optional `WEBHOOK_SECRET` validated via `X-Vapi-Secret` or `X-Aurora-Secret` header.

**Response by event type**:

| Event type | Response |
|------------|----------|
| `end-of-call-report` / `call.ended` | `{"status": "processed"}` |
| `call-started` | `{"status": "acknowledged"}` |
| `status-update` | `{"status": "acknowledged"}` |
| anything else | `{"status": "ignored"}` |

**On `end-of-call-report`**:
1. Extracts transcript, duration, cost, geo_region, metadata from Vapi payload
2. Runs `critique_call()` → `CallCritique` (9-category scores + all structured fields)
3. Stores complete call record in `calls` table via `insert_call()`
4. Updates lead status: `meeting_booked` / `follow_up_needed` / `closed_lost`
5. Creates nurture sequence if `not meeting_booked` (via `NurtureAgent.create_sequence()`)
6. Queues high-impact script improvements in `agent_improvements` via `insert_improvement()`
7. Logs `critique_completed` audit event
8. Checks MARS trigger: `len(get_calls_since(days=90)) % MARS_CYCLE_THRESHOLD == 0`

---

### `POST /webhooks/trigger-improvement`
00
Manually trigger the self-improvement cycle.

**Security**: Requires `X-Admin-Secret: <ADMIN_SECRET>` header. Returns `403 Forbidden` if missing or incorrect (not 401 — the distinction is intentional: the resource exists, the caller is simply not permitted).

**Response**:
```json
{
  "status": "completed",
  "new_version": 3,
  "patterns_found": 3,
  "improvements_applied": 12,
  "changelog": "Improved objection handling..."
}
```

---

### `GET /health`

```json
{
  "status": "ok",
  "db": "connected",
  "ai_cascade": {
    "gemini": true,
    "groq": true,
    "cerebras": true,
    "mistral": true,
    "openrouter": true,
    "openai": true,
    "anthropic": true
  },
  "vapi": true,
  "geo_numbers": {
    "in": true,
    "us": true,
    "uk": true,
    "global": true
  },
  "nurture_scheduler": true
}
```

`nurture_scheduler` reflects `is_scheduler_running()` from `nurture/scheduler.py`.

---

### `GET /api/stats`

```json
{
  "total_leads": 142,
  "calls_made": 97,
  "meetings_booked": 23,
  "avg_call_score": 71.4,
  "conversion_rate": 16.2,
  "total_cost_usd": 1.2340,
  "pending_improvements": 8,
  "active_prompt_version": 1
}
```

---

## 9. Infrastructure & Deployment

### Docker Compose (Local / Self-hosted)

**File**: [docker-compose.yml](docker-compose.yml)

Three services:

```yaml
backend:   localhost:8000  (FastAPI, env_file: .env, health check on /health)
dashboard: localhost:8501  (Streamlit)
landing:   localhost:3000  (Next.js, depends_on: backend)
```

Traefik labels included for production reverse-proxy routing.

### Render.com (Production)

**File**: [render.yaml](render.yaml)

**`srs-backend`** (web service):
- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Auto-deploy on `main` branch push

**`srs-dashboard`** (web service):
- Runtime: Python  
- Start: `streamlit run dashboard.py --server.port $PORT`

All environment variables are marked `sync: false` — manually set in Render dashboard.

### Vercel (Landing Page)

Standard Next.js deployment. Root directory: `landing/`. Set `NEXT_PUBLIC_BACKEND_URL` to Render backend URL.

### CI/CD — GitHub Actions

**File**: `.github/workflows/ci.yml`

- **On PR**: Run full pytest suite
- **On `main` merge**: Trigger Render deploy hooks for both backend and dashboard services

Deploy hooks stored as GitHub repository secrets:
- `RENDER_DEPLOY_HOOK_BACKEND`
- `RENDER_DEPLOY_HOOK_DASHBOARD`

### Backend Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 10. Test Suite

**Directory**: [backend/tests/](backend/tests/)

| File | What it tests |
|------|--------------|
| `test_health.py` | `GET /health` returns 200 with correct shape; all dependency imports present |
| `test_leads.py` | `POST /api/lead` — valid submission, 201 status, missing fields, invalid email, tier delay values |
| `test_webhooks.py` | Vapi webhook — `end-of-call-report` → `"processed"`, `call-started` → `"acknowledged"`, `status-update` → `"acknowledged"`, unknown type → `"ignored"`, `trigger-improvement` 403 without secret, 200 with valid `X-Admin-Secret` |
| `test_scoring.py` | `score_lead()` — high/medium tiers, fallback on AI error, malformed JSON handling, few-shot prompt content, orchestrator caching |
| `test_improvement.py` | `run_improvement_cycle()` — full pipeline mock, skip when no calls, `trigger_call()` payload validation, Vapi PATCH, 9-category critique shape |
| `test_geo_routing.py` | `_detect_geo_region()` — IN/US/UK/AU/SG prefix detection, `_get_phone_number_id()` returns correct env key, metadata pass-through |

### Test Infrastructure (conftest.py)

Three session/function-scoped fixtures:

```python
@pytest.fixture(scope="session", autouse=True)
def _preload_app():
    """Import app once so load_dotenv() fires before any test clears env vars."""
    from main import app  # side-effect: runs load_dotenv()

@pytest.fixture(autouse=True)
def clear_secret_env_vars(monkeypatch, _preload_app):
    """Unset WEBHOOK_SECRET + ADMIN_SECRET per-test so no .env pollutes auth checks."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_SECRET", raising=False)

@pytest.fixture
def mock_supabase():
    # MagicMock with chainable query builder (.select().eq().order().limit().execute())
    # Injected into routes via dependency override
```

All external services are patched at the module level where they are *imported*, not where they are defined:

```python
patch("api.webhooks.critique_call", new_callable=AsyncMock)
patch("api.webhooks.insert_call", new_callable=AsyncMock)
patch("api.leads.score_lead", new_callable=AsyncMock)
patch("ai.improvement.run_improvement_cycle", new_callable=AsyncMock)
```

Run tests:
```bash
cd backend
pytest tests/ -v --tb=short
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## 11. The 0.01% Flywheel

The name "Aurora 1.0" references the core loop: the system continuously improves by a measurable percentage with every 25-call batch.

```
Calls accumulate
      ↓
Critique identifies patterns (3+ call threshold to avoid overfitting)
      ↓
Pending improvements queue in Supabase
      ↓
[Every 25 calls] MARS meta-analysis synthesizes patterns via MCTS planner
      ↓
New complete prompt generated with specific changelog
      ↓
Vapi assistant updated via API PATCH
      ↓
Prompt version stored with before/after score expectations
      ↓
Next 25 calls run on improved prompt
      ↓
avg_score_after > avg_score_before ← measured improvement
      ↓
Repeat forever
```

Key design decisions that make this work:

1. **Full prompt replacement, not diffs**: The improvement AI generates a complete deployable prompt, not a patch. Prevents compounding errors.
2. **3+ call threshold**: Improvements only recommended if the pattern appeared in at least 3 calls. Prevents one bad call from corrupting the script.
3. **Versioned history**: Every prompt version is stored with its changelog. You can roll back by marking a previous version `is_active = True`.
4. **Manual trigger**: Admin can force the cycle at any time via webhook, not just the automatic 25-call trigger.

---

## 12. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon key (safe for frontend) |
| `SUPABASE_SERVICE_KEY` | Yes | Service role key — bypasses RLS in backend |
| `GEMINI_API_KEY` | Yes (primary) | Gemini 2.0 Flash — free, handles 95%+ of calls |
| `GROQ_API_KEY` | Recommended | Groq Llama 3.3 70B — free fallback (6K req/day) |
| `CEREBRAS_API_KEY` | Recommended | Cerebras Llama 3.3 70B — free 1M tokens/day, ultra-fast |
| `MISTRAL_API_KEY` | Recommended | Mistral Small — free tier, strong multilingual support |
| `OPENROUTER_API_KEY` | Recommended | DeepSeek V3 via OpenRouter — free reasoning model |
| `OPENAI_API_KEY` | Optional | GPT-4o-mini — last resort fallback |
| `ANTHROPIC_API_KEY` | Optional | Not used in current cascade (kept for API compat) |
| `VAPI_API_KEY` | Required for calls | Vapi platform key |
| `VAPI_ASSISTANT_ID` | Required for calls | Your Vapi assistant UUID |
| `VAPI_PHONE_NUMBER_ID` | Required for calls | Your Vapi outbound phone number UUID |
| `VAPI_PHONE_NUMBER_ID_IN` | Geo-routing | India local caller ID (+91) |
| `VAPI_PHONE_NUMBER_ID_US` | Geo-routing | US local caller ID (+1) |
| `VAPI_PHONE_NUMBER_ID_UK` | Geo-routing | UK local caller ID (+44) |
| `VAPI_PHONE_NUMBER_ID_GLOBAL` | Geo-routing | Global fallback number |
| `WEBHOOK_BASE_URL` | Yes | Public backend URL (e.g., `https://srs-backend.onrender.com`) |
| `WEBHOOK_SECRET` | Optional | Validates incoming Vapi webhooks |
| `ADMIN_SECRET` | Recommended | Protects `POST /webhooks/trigger-improvement` |
| `ALLOWED_ORIGINS` | Production | Comma-separated CORS origins |
| `SLACK_WEBHOOK_URL` | Optional | Slack notifications for key events |
| `RESEND_API_KEY` | Optional | Legacy email follow-up |
| `FROM_EMAIL` | Optional | Sender email address |
| `BREVO_API_KEY` | Nurture emails | Brevo (Sendinblue) API key for nurture sequence emails |
| `FROM_NAME` | Nurture emails | Display name for nurture emails (e.g., `Shango Revenue Systems`) |
| `WHATSAPP_PHONE_ID` | Nurture WhatsApp | Meta WhatsApp Business phone number ID (numeric string) |
| `WHATSAPP_TOKEN` | Nurture WhatsApp | Meta system user permanent access token |
| `EXOTEL_SID` | Nurture calls | Exotel account SID |
| `EXOTEL_API_KEY` | Nurture calls | Exotel API key (basic-auth username) |
| `EXOTEL_API_TOKEN` | Nurture calls | Exotel API token (basic-auth password) |
| `EXOTEL_SUBDOMAIN` | Nurture calls | Exotel API subdomain, e.g. `mycompany.api.exotel.com` |
| `EXOTEL_FROM_NUMBER` | Nurture calls | Exotel ExoPhone / virtual caller number |
| `SERPER_API_KEY` | Recommended | Serper.dev search API — 2,500 req/month free. Powers enrichment score adjustment. |
| `MARS_BUDGET_MINUTES` | Optional | MCTS compute budget per improvement cycle (default: `60`) |

---

## 13. Cost Model

At scale, the system is designed to run almost free under normal load.

| Operation | Provider | Est. Cost |
|-----------|----------|-----------|
| Lead scoring (~500 tokens) | Gemini Flash (free) | $0.000 |
| Post-call critique (~2,500 tokens) | Gemini Flash (free) | $0.000 |
| Improvement meta-analysis (~3,000 tokens) | Gemini Flash (free) | $0.000 |
| Outbound call (1–3 min) | Vapi | ~$0.05–0.15 |
| **Total per lead** | — | **~$0.05–0.15** |

If Gemini rate limits are hit (15 req/min on free tier), Groq absorbs the overflow at $0 (6,000 req/day). GPT-4o-mini is reserved for when both are down simultaneously — in practice this should never happen at modest scale.

For 100 leads/day: ~$5–15/day in Vapi call costs. AI analysis: effectively free.

---

## 14. Development Guide

### Setup

```bash
# Clone and set up backend
cd aurora-0.01/backend
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
cp ../.env.example .env        # Fill in your keys

# Run backend
uvicorn main:app --reload --port 8000

# Open API docs
http://localhost:8000/docs
```

### Key Development Patterns

**All AI calls go through the orchestrator:**
```python
# CORRECT
from ai.orchestrator import cascade_ai_call
result = await cascade_ai_call(prompt, system_prompt=SYSTEM, task_type="scoring")

# WRONG — bypasses caching, rate limiting, and fallback chain
import google.generativeai as genai
```

**All DB operations go through db/supabase.py:**
```python
# CORRECT
from db.supabase import upsert_lead, insert_call
await upsert_lead(lead_data)

# WRONG — direct client calls in routes
sb = get_supabase()
sb.table("leads").insert(data).execute()
```

**Fail open, never crash:**
```python
try:
    result = await cascade_ai_call(...)
    return parse_result(result)
except Exception as e:
    logger.error(f"Operation failed: {e}")
    return safe_default  # Never raise — caller handles gracefully
```

### Running the Dashboard

```bash
cd aurora-0.01/dashboard
pip install -r requirements.txt
# Create .streamlit/secrets.toml:
# SUPABASE_URL = "..."
# SUPABASE_KEY = "..."
streamlit run dashboard.py
```

### Running Tests

```bash
cd aurora-0.01/backend
pytest tests/ -v
pytest tests/test_scoring.py -v          # Single file
pytest -k "test_trigger_improvement" -v  # Single test
pytest tests/ --cov=. --cov-report=html  # Coverage report
```

---

## 16. Manual Setup Checklist

This section lists every *human* action required before Aurora 1.0 is production-ready. Code is complete; the items below require accounts, dashboards, or SQL editors.

---

### 16.1 Supabase — Schema Migrations

If your Supabase project was created before February 2026 (i.e., from the original `schema.sql`), run the following migrations in the Supabase **SQL Editor**:

#### 1. Add CHECK constraint on `follow_up_strategy`
```sql
ALTER TABLE calls
  ADD CONSTRAINT follow_up_strategy_check
  CHECK (follow_up_strategy IN ('email','call','whatsapp','sms','none'));
```

#### 2. Verify `nurture_sequences` table has all required columns
```sql
-- Confirm these columns exist (added in schema.sql v2):
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'nurture_sequences'
ORDER BY ordinal_position;

-- Expected columns: id, lead_email, lead_name, lead_company, lead_score,
-- phone, pain_points, call_summary, geo_region, sequence_type,
-- current_step, steps, is_active, completed, created_at, last_action_at
```

#### 3. Add `pacing_score`, `silence_score`, `geo_region` to calls if missing
```sql
ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS pacing_score   INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS silence_score  INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS geo_region     TEXT    DEFAULT 'global';
```

#### 4. Seed initial prompt version (required for MARS loop)
```sql
INSERT INTO prompt_versions (version_number, prompt_text, is_active, created_at)
VALUES (
  1,
  'You are ARIA, Shango Revenue Systems\u2019 AI sales agent. Your goal is to qualify the lead, understand their pain points, and book a discovery call.',
  TRUE,
  NOW()
);
```

---

### 16.2 Meta WhatsApp Business — Template Registration

All WhatsApp messages sent by Aurora use **pre-approved template messages**. Templates must be submitted in Meta Business Manager and approved (typically 1–24 hours).

**Account setup:**
1. Go to [business.facebook.com](https://business.facebook.com) → Create/use existing Business Account
2. Add a **WhatsApp Business** phone number
3. Note the **Phone Number ID** → set as `WHATSAPP_PHONE_ID`
4. Create a **System User** with `whatsapp_business_messaging` permission → generate permanent token → set as `WHATSAPP_TOKEN`

**Templates to register** (all in `en_US`, category: `MARKETING`):

| Template name | Body (with variable placeholders) | Used in |
|---------------|-----------------------------------|---------|
| `shango_hot_day1` | `Hi {{1}}, following up on Shango Revenue Systems reaching out to {{2}}. We\u2019d love to address {{3}} — worth a 15-min chat?` | hot step 1 |
| `shango_warm_day1` | `Hi {{1}}, quick note from Shango Revenue Systems re: {{2}}. We help teams tackle {{3}} — can we find 15 mins?` | warm step 1 |
| `shango_cold_day4` | `Hi {{1}} — Shango Revenue Systems here. We specialize in helping {{2}} solve {{3}}. Open to a brief call?` | cold step 1 |
| `shango_cold_reactivation` | `Hi {{1}}, it\u2019s been a while! Shango Revenue Systems is back with new solutions for {{2}} around {{3}}. Interested?` | cold step 3 |

> `{{1}}` = first name, `{{2}}` = company name, `{{3}}` = primary pain point

---

### 16.3 Exotel — Account & Webhook Setup

1. **Create Exotel account** at [exotel.com](https://exotel.com) → get SID, API key, API token
2. **Buy/assign an ExoPhone** (virtual number) → set as `EXOTEL_FROM_NUMBER`
3. **Note your API subdomain** from the Exotel dashboard (format: `<company>.api.exotel.com`) → set as `EXOTEL_SUBDOMAIN`
4. **Set the webhook URL** for call status callbacks:
   - In Exotel dashboard: Applets → set `{WEBHOOK_BASE_URL}/webhooks/exotel` as the callback
   - **Note**: `POST /webhooks/exotel` endpoint is not yet implemented in `api/webhooks.py`. Add a stub handler to avoid Exotel retries:
   ```python
   @router.post("/exotel")
   async def exotel_callback(request: Request):
       data = await request.form()
       logger.info(f"Exotel callback: {dict(data)}")
       return {"status": "received"}
   ```

---

### 16.4 Vapi — Assistant & Phone Numbers

1. Go to [vapi.ai](https://vapi.ai) → create assistant
2. Copy the initial system prompt from `supabase/schema.sql` (seeds `prompt_versions` table row 1)
3. Set webhook: Dashboard → Assistant → Server URL → `{WEBHOOK_BASE_URL}/webhooks/vapi`
4. Buy phone numbers for each region and collect IDs:
   - India (+91) → `VAPI_PHONE_NUMBER_ID_IN`
   - US (+1) → `VAPI_PHONE_NUMBER_ID_US`
   - UK (+44) → `VAPI_PHONE_NUMBER_ID_UK`
   - Global fallback → `VAPI_PHONE_NUMBER_ID_GLOBAL`

---

### 16.5 Brevo — Sender Domain Verification

1. Go to [brevo.com](https://www.brevo.com) → Senders & IPs → Add a new domain
2. Add DNS records (SPF, DKIM, DMARC)
3. Verify sender email (`FROM_EMAIL`, e.g. `team@shango.in`)
4. Get API key → set as `BREVO_API_KEY`

---

### 16.6 Environment Variables — Full `.env` for Production

Create `backend/.env` with all variables. Variables marked **NEW** were added in the nurture/WhatsApp/Exotel work; they are absent from any existing `.env.example`:

```env
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...

# AI Cascade
GEMINI_API_KEY=
GROQ_API_KEY=
CEREBRAS_API_KEY=
MISTRAL_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Vapi
VAPI_API_KEY=
VAPI_ASSISTANT_ID=
VAPI_PHONE_NUMBER_ID=          # legacy / fallback
VAPI_PHONE_NUMBER_ID_IN=
VAPI_PHONE_NUMBER_ID_US=
VAPI_PHONE_NUMBER_ID_UK=
VAPI_PHONE_NUMBER_ID_GLOBAL=

# Backend
WEBHOOK_BASE_URL=https://srs-backend.onrender.com
WEBHOOK_SECRET=
ADMIN_SECRET=
ALLOWED_ORIGINS=https://srs-dashboard.onrender.com,https://shango.ai

# Brevo (email)
BREVO_API_KEY=                 # also accepted: SENDINBLUE_API_KEY
FROM_EMAIL=aria@shango.ai
FROM_NAME=ARIA \u2014 Shango Revenue Systems

# WhatsApp via Meta (NEW)
WHATSAPP_PHONE_ID=             # numeric phone number ID from Meta dashboard
WHATSAPP_TOKEN=                # system user permanent access token

# Exotel (NEW)
EXOTEL_SID=
EXOTEL_API_KEY=
EXOTEL_API_TOKEN=
EXOTEL_SUBDOMAIN=mycompany.api.exotel.com
EXOTEL_FROM_NUMBER=+91XXXXXXXXXX
```

---

### 16.7 Render — Production Deployment

1. Push repo to GitHub (`git push origin main`)
2. Go to [render.com](https://render.com) → New → Blueprint → connect repo
3. `render.yaml` auto-creates two services: `srs-backend` (FastAPI) and `srs-dashboard` (Streamlit)
4. In each service → Environment → add all API keys and secrets
5. After first deploy, go to `srs-backend` → Settings → Custom Domains → add `api.shango.in`
6. Go to `srs-dashboard` → Settings → Custom Domains → add `dashboard.shango.in`
7. Render will show you CNAME values → add them to your DNS immediately (see §17 DNS)
8. Add Render deploy hooks to GitHub repo Secrets: `RENDER_DEPLOY_HOOK_BACKEND`, `RENDER_DEPLOY_HOOK_DASHBOARD`

---

### 16.8 Vercel — Landing Page

1. Go to [vercel.com](https://vercel.com) → New Project → import from GitHub
2. Root directory: `landing`
3. Add env var: `NEXT_PUBLIC_BACKEND_URL=https://api.shango.in`
4. After deploy, go to Settings → Domains → add `shango.in` and `www.shango.in`
5. Vercel will show you nameserver or CNAME values → update DNS (see §17)

---

### 16.9 GitHub — Push Repo (Manual — aurora-018)

```bash
cd "d:\AI Projects\Projects\Projects\aurora-0.01"
git init
git add .
git commit -m "feat: Aurora 1.0 — complete autonomous AI SDR"
git branch -M main
git remote add origin https://github.com/Shangoin/aurora-0.01.git
git push -u origin main
```

---

### 16.10 Serper — Enrichment API Key

1. Go to [serper.dev](https://serper.dev) → sign up (free: 2,500 searches/month)
2. Copy your API key → set as `SERPER_API_KEY` in `backend/.env`
3. If absent at runtime, `enrich_lead_score()` silently skips enrichment and returns the raw AI score unchanged—no leads are lost.

#### Run enrichment migration
```sql
-- In Supabase SQL Editor (if upgrading from Aurora 1.0.0):
ALTER TABLE leads ADD COLUMN IF NOT EXISTS icp_fit           BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS budget_signals    JSONB DEFAULT '[]';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS enrichment_signals JSONB DEFAULT '{}';
```

---

All 39 implementation stories shipped. Story aurora-018 (git push) requires one-time manual execution.

### Original Stories (aurora-001 – aurora-024)

| Story ID | Title | Status |
|----------|-------|--------|
| aurora-001 | FastAPI backend scaffolding | ✅ done |
| aurora-002 | Pydantic data models | ✅ done |
| aurora-003 | AI cascade orchestrator | ✅ done |
| aurora-004 | AI lead scoring | ✅ done |
| aurora-005 | 9-category call critique engine | ✅ done |
| aurora-006 | Autonomous self-improvement loop | ✅ done |
| aurora-007 | Vapi outbound call trigger | ✅ done |
| aurora-008 | Lead ingestion API endpoint | ✅ done |
| aurora-009 | Vapi webhook handler | ✅ done |
| aurora-010 | Supabase database layer | ✅ done |
| aurora-011 | Supabase schema | ✅ done |
| aurora-012 | Streamlit command center dashboard | ✅ done |
| aurora-013 | Next.js landing page | ✅ done |
| aurora-014 | Docker Compose orchestration | ✅ done |
| aurora-015 | Complete test suite | ✅ done |
| aurora-016 | Render deployment config | ✅ done |
| aurora-017 | GitHub Actions CI/CD | ✅ done |
| aurora-018 | Git repo initialization + GitHub push | ⏳ pending manual |
| aurora-019 | Lead Nurture Engine (OpenClaw + Brevo + APScheduler) | ✅ done |
| aurora-020 | OpenClaw agent integration + email personalisation | ✅ done |
| aurora-021 | Geo-routing: 4-region Vapi phone number map | ✅ done |
| aurora-022 | 9-category critique upgrade (pacing + silence_handling) | ✅ done |
| aurora-023 | MARS self-improvement loop (MCTS, 25-call trigger) | ✅ done |
| aurora-024 | 6-LLM cascade upgrade (Cerebras + Mistral + DeepSeek) | ✅ done |
| aurora-025 | Serper lead enrichment engine | ✅ done |
| aurora-026 | MCP server (13 tools, 4 resources, stdio + SSE) | ✅ done |

### Hardening Pass (Steps 1–13, February 2026)

| Step | File(s) | Changes |
|------|---------|--------|
| Step 1 | `backend/db/supabase.py` | `get_supabase_client` alias for test patchability; `get_call_count()`, `get_calls_since()`, `get_mars_lessons()` added |
| Step 2 | `backend/models.py` | Verified all 9 `CallScores` fields; `LeadResponse`, `VapiWebhookPayload`, MARS models, Nurture models confirmed |
| Step 3 | `backend/ai/orchestrator.py` | `get_provider_stats()` added; `parse_json_response()` hardened; `humanize_text()` tested |
| Step 4 | `backend/ai/scoring.py` | Few-shot CoT prompt verified; `score_lead()` fail-open default confirmed |
| Step 5 | `backend/ai/critique.py` | 9-category `CallScores` schema enforced; `minimum_transcript_guard` (50 chars) |
| Step 6 | `backend/ai/improvement.py` | `trigger_call()` kwargs fixed (`phone=` not `phone_number=`); `_detect_geo_region(None)` guard added |
| Step 7 | `backend/ai/mars.py` | New file: `MCTSNode` dataclass, `MARS_CYCLE_THRESHOLD=25`, `run_mcts_planner()`, `plan_improvements()`, `insert_mars_lesson()` |
| Step 8 | `backend/nurture/` | `agent.py` bug: `trigger_call` kwarg mismatch + `lead_company` param fixed; `__init__.py` exports corrected to `start_scheduler, stop_scheduler` |
| Step 9 | `backend/api/leads.py` | Full rewrite: `BackgroundTasks` (non-blocking), `recommended_delay_minutes`, `_fire_call()`, `_mark_no_phone()`, 201 status, call_failed event, no_phone_lead event |
| Step 10 | `backend/api/webhooks.py` | 4 fixes: imports `MARS_CYCLE_THRESHOLD` from `ai.mars`; `.model_dump()` not `.dict()`; distinct response status per event type; `X-Admin-Secret` header + 403 (not Bearer + 401); MARS trigger via `get_calls_since() % N == 0` |
| Step 10 | `backend/tests/conftest.py` | Added `_preload_app` session fixture + `clear_secret_env_vars` autouse fixture to isolate `.env` from tests |
| Step 11 | `backend/main.py` | `/health` uses `_supabase.get_supabase_client()` (patch-friendly); returns `nurture_scheduler: is_scheduler_running()` |
| Step 11 | `backend/nurture/scheduler.py` | `is_scheduler_running() -> bool` added; exported via `__init__.py` |
| Step 12 | `dashboard/dashboard.py` | Expanded to 7 pages: added Nurture page (sequences + animated step progress bars + Pause/Resume controls + distribution charts); Settings page rebuilt with live health check panel; `fetch_nurture_sequences()` and `fetch_health()` added as `@st.cache_data(ttl=30)` fetchers |
| Step 13 | `landing/src/app/page.tsx` | Redesigned success card: animated SVG ring gauge, `TIER_ETA` map (HIGH < 5 min / MEDIUM 15 min / LOW 60 min), pulsing tier badge (HIGH), ICP Fit / Urgency / Lead Score breakdown row; loading spinner via `@keyframes spin` in `globals.css` |
| Step 13 | `landing/src/app/globals.css` | New file: `@keyframes spin`, `box-sizing` reset |
| Step 13 | `landing/src/app/layout.tsx` | Imports `globals.css` |

---

*Design document last updated February 2026 (v1.1.0). Built with GitHub Copilot across 39 automated implementation iterations.*

---

## 17. Production Launch Guide — shango.in

This section is the **complete ordered checklist** for taking Aurora 1.0 live at `shango.in` with `team@shango.in` as the sender email. Execute in the order shown — some steps depend on completions earlier in the list.

---

### Step 1 — GitHub: Push the repo

```bash
cd "d:\AI Projects\Projects\Projects\aurora-0.01"
git init
git add .
git commit -m "feat: Aurora 1.0 — Shango Revenue Systems"
git branch -M main
git remote add origin https://github.com/Shangoin/aurora-0.01.git
git push -u origin main
```

---

### Step 2 — Supabase: Create database

1. Go to [supabase.com](https://supabase.com) → New project (name: `shango-aurora`)
2. Wait for project to provision (~2 min)
3. Go to **SQL Editor** → paste the full contents of `supabase/schema.sql` → **Run**
4. Collect these values from **Settings → API**:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_KEY`
   - **service_role key** (bottom, hidden) → `SUPABASE_SERVICE_KEY`

---

### Step 3 — AI API Keys: All free, get all 5

| Key | Get it at | Env var |
|-----|-----------|--------|
| Gemini 2.0 Flash | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `GEMINI_API_KEY` |
| Groq Llama 3.3 | [console.groq.com](https://console.groq.com) → API Keys | `GROK_API_KEY` |
| Cerebras | [inference.cerebras.ai](https://inference.cerebras.ai) → API Keys | `CEREBRAS_API_KEY` |
| Mistral | [console.mistral.ai](https://console.mistral.ai) → API Keys | `MISTRAL_API_KEY` |
| OpenRouter (DeepSeek) | [openrouter.ai](https://openrouter.ai) → Keys | `OPENROUTER_API_KEY` |
| Serper | [serper.dev](https://serper.dev) → API Key (2,500 free/month) | `SERPER_API_KEY` |

---

### Step 4 — Vapi: Create ARIA voice assistant

1. Go to [vapi.ai](https://vapi.ai) → sign up / log in
2. **Create assistant**:
   - Name: `ARIA — Shango Revenue Systems`
   - System prompt: copy from `supabase/schema.sql` (the text seeded in `prompt_versions`)
   - Voice: ElevenLabs or PlayHT — a confident, warm female voice
3. Note the **Assistant ID** → `VAPI_ASSISTANT_ID`
4. **Server URL** (webhook): set to `https://api.shango.in/webhooks/vapi` *(set again after Step 8)*
5. **Buy 4 phone numbers** → Phone Numbers → Buy New:
   - India +91 (Mumbai) → `VAPI_PHONE_NUMBER_ID_IN`
   - US +1 (any area code) → `VAPI_PHONE_NUMBER_ID_US`
   - UK +44 (London) → `VAPI_PHONE_NUMBER_ID_UK`
   - Australia/Singapore/Global +61 or +65 → `VAPI_PHONE_NUMBER_ID_GLOBAL`
6. Note your **Vapi private API key** → `VAPI_API_KEY`

---

### Step 5 — Brevo: Verify shango.in sender domain

1. Go to [app.brevo.com](https://app.brevo.com) → sign up
2. **Senders & IPs → Domains → Add a domain** → enter `shango.in`
3. Brevo gives you 3 DNS records to add (SPF, DKIM, DMARC) → add them in your DNS registrar **now** (same session as Step 6)
4. Come back to Brevo and click **Verify** once DNS propagates (can take up to 30 min)
5. **Senders → Add a new sender**: `team@shango.in`, name `Shango Revenue Systems`
6. Get your API key → **SMTP & API → API Keys** → `BREVO_API_KEY`

---

### Step 6 — DNS: Configure shango.in

Log into your domain registrar for `shango.in` and add these records. You’ll fill in Render/Vercel CNAME values from Steps 7–8.

#### Root domain and www → Vercel (landing page)

| Type | Name | Value |
|------|------|-------|
| `A` | `@` | `76.76.21.21` (Vercel’s IP) |
| `CNAME` | `www` | `cname.vercel-dns.com` |

#### API backend → Render

| Type | Name | Value |
|------|------|-------|
| `CNAME` | `api` | from Render: `srs-backend.onrender.com` |

#### Dashboard → Render

| Type | Name | Value |
|------|------|-------|
| `CNAME` | `dashboard` | from Render: `srs-dashboard.onrender.com` |

#### Email (for Brevo delivery of team@shango.in)

Brevo gives you the exact values for these — add verbatim:

| Type | Name | Value |
|------|------|-------|
| `TXT` | `@` | `v=spf1 include:spf.brevo.com ~all` |
| `TXT` | `brevo._domainkey` | *(DKIM key from Brevo dashboard)* |
| `TXT` | `_dmarc` | `v=DMARC1; p=none; rua=mailto:team@shango.in` |

> DNS propagation takes 5–30 minutes. You can continue Steps 7–9 while waiting.

---

### Step 7 — Render: Deploy backend and dashboard

1. Go to [render.com](https://render.com) → New → **Blueprint** → connect GitHub repo `Shangoin/aurora-0.01`
2. Render reads `render.yaml` and creates:
   - `srs-backend` (FastAPI at port 8000)
   - `srs-dashboard` (Streamlit)
3. On first deploy, both will fail because API keys are not set yet — that’s OK
4. **srs-backend → Environment** → add every key from this table:

```
SUPABASE_URL              (from Step 2)
SUPABASE_KEY              (from Step 2)
SUPABASE_SERVICE_KEY      (from Step 2)
GEMINI_API_KEY            (from Step 3)
GROK_API_KEY              (from Step 3)
CEREBRAS_API_KEY          (from Step 3)
MISTRAL_API_KEY           (from Step 3)
OPENROUTER_API_KEY        (from Step 3)
SERPER_API_KEY            (from Step 3)
VAPI_API_KEY              (from Step 4)
VAPI_ASSISTANT_ID         (from Step 4)
VAPI_PHONE_NUMBER_ID_IN   (from Step 4)
VAPI_PHONE_NUMBER_ID_US   (from Step 4)
VAPI_PHONE_NUMBER_ID_UK   (from Step 4)
VAPI_PHONE_NUMBER_ID_GLOBAL (from Step 4)
VAPI_PHONE_NUMBER_ID      (same as GLOBAL is fine)
BREVO_API_KEY             (from Step 5)
WEBHOOK_SECRET            generate: openssl rand -hex 32
ADMIN_SECRET              generate: openssl rand -hex 32
```
5. Click **Manual Deploy** → wait for green health check at `/health`
6. **srs-backend → Settings → Custom Domains** → add `api.shango.in`
   - Render shows: `srs-backend.onrender.com` → copy and add as CNAME `api` in your DNS
7. **srs-dashboard → Settings → Custom Domains** → add `dashboard.shango.in`
   - Same: copy CNAME → add DNS record
8. **srs-dashboard → Environment** → add:
```
SUPABASE_URL
SUPABASE_KEY
BACKEND_URL    https://api.shango.in
ADMIN_SECRET   (same as above)
```

---

### Step 8 — Vercel: Deploy landing page at shango.in

1. Go to [vercel.com](https://vercel.com) → Add New Project → Import `Shangoin/aurora-0.01`
2. **Root directory**: `landing`
3. **Environment Variables** (add before first deploy):
   - `NEXT_PUBLIC_BACKEND_URL` = `https://api.shango.in`
4. Click **Deploy** → wait for build complete
5. **Project Settings → Domains** → Add `shango.in` and `www.shango.in`
6. Vercel shows DNS records → confirm they match what you added in Step 6 (`A` record for `@`, CNAME for `www`)

---

### Step 9 — Vapi: Update webhook URL

1. Go back to [vapi.ai](https://vapi.ai) → your ARIA assistant → Server URL
2. Set to: `https://api.shango.in/webhooks/vapi`
3. If you set a `WEBHOOK_SECRET` in Step 7, also add it in Vapi → Server Secret

---

### Step 10 — Meta WhatsApp Business (for nurture sequences)

> **Can be deferred** — the system works without WhatsApp; nurture email steps still fire.

1. Go to [business.facebook.com](https://business.facebook.com) → add WhatsApp → verify `shango.in` business
2. Add a WhatsApp Business phone number (can be your Indian mobile)
3. Note the **Phone Number ID** → `WHATSAPP_PHONE_ID`
4. **System Users → Create** → assign `whatsapp_business_messaging` permission → generate permanent token → `WHATSAPP_TOKEN`
5. **Message Templates → Create** (category: Marketing, language: en_US) — create all 4:

| Template name | Body |
|---------------|------|
| `shango_hot_day1` | `Hi {{1}}, following up from Shango Revenue Systems re: {{2}}. We’d love to address {{3}} — worth a 15-min chat?` |
| `shango_warm_day1` | `Hi {{1}}, quick note from Shango Revenue Systems re: {{2}}. We help teams tackle {{3}} — can we find 15 mins?` |
| `shango_cold_day4` | `Hi {{1}} — Shango Revenue Systems here. We specialise in helping {{2}} solve {{3}}. Open to a brief call?` |
| `shango_cold_reactivation` | `Hi {{1}}, it’s been a while! Shango has new solutions for {{2}} around {{3}}. Interested?` |

6. Wait for Meta approval (1–24 hours)
7. Add `WHATSAPP_PHONE_ID` and `WHATSAPP_TOKEN` to Render `srs-backend` environment → redeploy

---

### Step 11 — Exotel: Nurture outbound calls in India

> **Can be deferred** — Exotel powers India nurture calls only. Vapi handles initial calls.

1. Sign up at [exotel.com](https://exotel.com) → KYC verify with GST/business docs (~1 business day)
2. Buy a virtual ExoPhone (Indian outbound number) → `EXOTEL_FROM_NUMBER`
3. Collect: Account SID, API Key, API Token, API Subdomain from Exotel dashboard
4. Add all 5 Exotel vars to Render `srs-backend` → redeploy

---

### Step 12 — Verify everything is live

Run through this checklist in order:

```
☐  https://shango.in               → landing page loads, form visible
☐  https://api.shango.in/health    → {"status": "ok", "db": "connected"}
☐  https://api.shango.in/docs      → FastAPI Swagger UI
☐  https://dashboard.shango.in     → Streamlit dashboard loads, KPI cards visible
☐  Supabase SQL Editor             → SELECT COUNT(*) FROM prompt_versions; returns 1
☐  Vapi dashboard                  → ARIA assistant shows server URL = api.shango.in
☐  Brevo                           → shango.in domain shows ‘Authenticated’ status
```

---

### Step 13 — End-to-end smoke test

1. Go to `https://shango.in`
2. Fill the form with a **real phone number you can answer** (use your own mobile)
3. Submit → confirm the score card appears with tier and ETA
4. Check Supabase `leads` table → row should appear with score + enrichment_signals
5. Check Supabase `audit_log` → `lead_scored` and `call_initiated` events
6. Wait for Vapi to call your number → ARIA should introduce herself and ask about your business
7. End the call → wait 30 seconds → check Supabase `calls` table for the critique record
8. Check `https://dashboard.shango.in` → KPI cards should now show 1 lead, 1 call

---

### Step 14 — GitHub Actions secrets (CI/CD auto-deploy)

Add these secrets to `github.com/Shangoin/aurora-0.01 → Settings → Secrets → Actions`:

| Secret name | Where to get it |
|-------------|----------------|
| `RENDER_DEPLOY_HOOK_BACKEND` | Render → srs-backend → Settings → Deploy Hook |
| `RENDER_DEPLOY_HOOK_DASHBOARD` | Render → srs-dashboard → Settings → Deploy Hook |

Now every push to `main` auto-deploys both services.

---

### Quick reference: final URLs

| Service | URL |
|---------|-----|
| Landing page | https://shango.in |
| Landing page (www) | https://www.shango.in |
| Backend API | https://api.shango.in |
| API docs (Swagger) | https://api.shango.in/docs |
| Health check | https://api.shango.in/health |
| Dashboard | https://dashboard.shango.in |
| Sender email | team@shango.in |
| Vapi webhook | https://api.shango.in/webhooks/vapi |
| Manual MARS trigger | POST https://api.shango.in/webhooks/trigger-improvement (X-Admin-Secret header) |

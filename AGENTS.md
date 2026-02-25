# Shango Revenue Systems — Agent Instructions

## Project Summary

**Aurora 1.0** — Shango Revenue Systems is an **autonomous AI SDR** targeting the top 0.01% of call performance. It scores every inbound lead, routes calls through geo-local Vapi numbers, critiques every call across 9 dimensions, and runs MARS self-improvement every 25 calls using MCTS budget planning.

**Target metrics:** 85+ avg call score · 25%+ meeting rate · ₹4/lead · <5 min speed-to-lead

## Architecture (Aurora 1.0)

```
Landing Page (Next.js) — country dropdown + geo phone prefix
    ↓ POST /api/lead  { country_code, phone_prefix, ... }
FastAPI Backend
    ↓ score_lead() → 6-LLM cascade (Gemini→Groq→Cerebras→Mistral→DeepSeek→GPT-4o-mini)
    ↓ tier: high=5min, medium=15min, low=60min
    ↓ trigger_call() → _get_phone_number_id(phone) → geo-local Vapi number
Vapi Voice Agent (ARIA)
    ↓ POST /webhooks/vapi  (end-of-call-report)
FastAPI Backend
    ↓ critique_call() → 9-category scores (pacing + silence_handling NEW)
    ↓ insert_call() → Supabase  { pacing_score, silence_score, geo_region }
    ↓ every 25 calls → run_improvement_cycle()  [MARS loop]
        ↓ _run_mcts_planner() → MCTSNode list (reward = delta/compute_cost)
        ↓ cascade_ai_call() → module-level prompt diff
        ↓ insert_mars_lesson() → Supabase mars_lessons table
        ↓ _update_vapi_assistant() → PATCH Vapi API
        ↓ insert_prompt_version() → Supabase
Streamlit Dashboard (6 pages) → Supabase + /api/provider-stats
```

## Commands

```bash
# Backend (from aurora-0.01/ root)
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
source .venv/bin/activate         # Mac/Linux
pip install -r requirements.txt
cp ../.env.example .env           # Then fill in your keys
uvicorn main:app --reload --port 8000

# Run tests
pytest tests/ -v --tb=short

# Dashboard
cd dashboard
streamlit run dashboard.py

# Landing page
cd landing
npm install
npm run dev   # http://localhost:3000

# Full stack via Docker
docker compose up -d --build
```

## Key Files

| Layer | File | Purpose |
|-------|------|---------|
| Entry | `backend/main.py` | FastAPI app, lifespan, CORS, /health, /api/stats |
| Models | `backend/models.py` | All Pydantic types |
| AI Core | `backend/ai/orchestrator.py` | Gemini→Grok→Claude→OpenAI cascade + cache |
| Scoring | `backend/ai/scoring.py` | Lead score 0-100, tier, delay |
| Critique | `backend/ai/critique.py` | 7-category call analysis |
| Self-improve | `backend/ai/improvement.py` | Improvement cycle + trigger_call + Vapi PATCH |
| Routes | `backend/api/leads.py` | POST /api/lead |
| Routes | `backend/api/webhooks.py` | POST /webhooks/vapi, POST /webhooks/trigger-improvement |
| DB | `backend/db/supabase.py` | All Supabase ops |
| Schema | `supabase/schema.sql` | Run once in Supabase SQL Editor |
| Dashboard | `dashboard/dashboard.py` | Streamlit 5-page command center |
| Landing | `landing/src/app/page.tsx` | Lead capture form + live score display |
| Deploy | `render.yaml` | Render.com one-click deploy |
| CI/CD | `.github/workflows/ci.yml` | Test on PR, deploy to Render on main |

## Environment Variables

See `.env.example` for all required variables. Critical ones:

```
SUPABASE_URL          # Your Supabase project URL
SUPABASE_KEY          # Supabase anon key (frontend safe)
SUPABASE_SERVICE_KEY  # Supabase service key (backend only)
GEMINI_API_KEY        # Primary AI — cascade provider 1
GROK_API_KEY          # Cascade provider 2
CEREBRAS_API_KEY      # Cascade provider 3 — free 1M tokens/day
MISTRAL_API_KEY       # Cascade provider 4 — multilingual
OPENROUTER_API_KEY    # Cascade provider 5 — DeepSeek V3
OPENAI_API_KEY        # Cascade provider 6 — last resort
ANTHROPIC_API_KEY     # Claude Sonnet for critique (quality-critical)
VAPI_API_KEY          # Vapi voice platform
VAPI_ASSISTANT_ID     # Your Vapi assistant UUID
VAPI_PHONE_NUMBER_ID  # Fallback/legacy global number
VAPI_PHONE_NUMBER_ID_IN     # India local number (+91 routing)
VAPI_PHONE_NUMBER_ID_US     # US local number (+1 routing)
VAPI_PHONE_NUMBER_ID_UK     # UK local number (+44 routing)
VAPI_PHONE_NUMBER_ID_GLOBAL # Global fallback (+61/+65/other)
WEBHOOK_BASE_URL      # Public URL where backend is deployed
ADMIN_SECRET          # Protects manual improvement trigger endpoint
```

## Deployment (Manual Steps Required)

### 1. GitHub — Push Code
```bash
cd "d:\AI Projects\Projects\Projects\aurora-0.01"
git init
git add .
git commit -m "feat: Shango Revenue Systems — autonomous AI sales agent (complete)"
git branch -M main
git remote add origin https://github.com/Shangoin/aurora-0.01.git
git push -u origin main
```

### 2. Supabase — Create Database
1. Go to https://supabase.com → New project
2. SQL Editor → paste contents of `supabase/schema.sql` → Run
3. Note your project URL and API keys

### 3. Vapi — Create Voice Assistant
1. Go to https://vapi.ai → Create assistant
2. The schema.sql seeds the initial v1 prompt — copy it to Vapi assistant system prompt
3. Note your `assistant_id` and buy a phone number, note `phone_number_id`
4. Set webhook URL to: `https://<your-render-url>/webhooks/vapi`

### 4. Render — Deploy Backend + Dashboard
1. Go to https://render.com → New → Blueprint (connects to `render.yaml`)
2. Connect your GitHub repo `Shangoin/aurora-0.01`
3. Set all env vars in each service's Environment tab
4. Note the backend URL after first deploy → set as `WEBHOOK_BASE_URL`

### 5. Vercel — Deploy Landing Page
1. Go to https://vercel.com → New Project → Import from GitHub
2. Root directory: `landing`
3. Set env var: `NEXT_PUBLIC_BACKEND_URL` = your Render backend URL

### 6. GitHub Secrets (for CI auto-deploy)
Add to repo Settings → Secrets → Actions:
- `RENDER_DEPLOY_HOOK_BACKEND` — from Render service dashboard → Deploy Hook
- `RENDER_DEPLOY_HOOK_DASHBOARD` — from Render dashboard service

## Aurora 1.0 Patterns

### Geo-routing: Always use _get_phone_number_id()
```python
# CORRECT — uses local caller ID for 40%+ answer rate
from ai.improvement import trigger_call
await trigger_call(phone_number="+919876543210", ...)
# _get_phone_number_id will pick VAPI_PHONE_NUMBER_ID_IN automatically

# WRONG — always uses same phone number regardless of region
payload = {"phoneNumberId": os.environ["VAPI_PHONE_NUMBER_ID"]}
```

### MARS cycle threshold is 25 calls
```python
# MARS_CYCLE_THRESHOLD = 25  (was 50 in Aurora 0.01)
# Every 25 calls, MCTS planner runs, module-level changes stored to mars_lessons
```

### 9 critique categories (not 7)
```python
# Critique returns CallScores with 9 fields:
# opening, discovery, rapport, objection_handling, closing,
# naturalness, relevance, pacing (NEW), silence_handling (NEW)
```

### insert_call() now requires pacing_score, silence_score, geo_region
```python
record = {
    "overall_score": 78,
    "pacing_score": 72,        # NEW Aurora 1.0 field
    "silence_score": 68,       # NEW Aurora 1.0 field
    "geo_region": "india",     # NEW Aurora 1.0 field
    ...other fields...
}
await insert_call(record)
```

## Development Patterns

### AI calls always go through the orchestrator
```python
# CORRECT
from ai.orchestrator import cascade_ai_call, humanize_text
result = await cascade_ai_call(prompt, task_type="scoring")
return humanize_text(result)

# WRONG — bypasses caching, rate limiting, fallback
import google.generativeai as genai
```

### All DB ops go through db/supabase.py
```python
# CORRECT
from db.supabase import upsert_lead, get_lead_by_email
await upsert_lead(lead_data)

# WRONG — direct Supabase client calls in routes
```

### Auth on admin routes
```python
# Protect sensitive endpoints with admin secret
from api.webhooks import verify_admin_secret
```

## Testing

```bash
# All tests
cd backend && pytest tests/ -v

# Single file
pytest tests/test_improvement.py -v

# With env vars inline
SUPABASE_URL=test SUPABASE_KEY=test pytest tests/ -v
```

## n8n Workflow

The `n8n/` directory contains a workflow JSON that:
1. Receives webhook from landing page (alternative to direct FastAPI)
2. Enriches lead via Apollo
3. Triggers Shango Revenue Systems backend `/api/lead`

Import at: https://n8n.yoursite.com → Workflows → Import

## Prior Versions & Progress

Aurora 0.01 → 17 stories shipped (see `prd.json` in ralph-sentinel-prime).
Aurora 1.0 → Backend complete: 6-LLM cascade, MARS loop, geo-routing, 9-category critique.
Remaining: landing page deployed, dashboard running, tests green.

# Shango Revenue Systems — Agent Instructions

## Project Summary

Shango Revenue Systems is an **autonomous AI sales development agent**. It scores every inbound lead, calls them within minutes using a Vapi AI voice assistant (ARIA), critiques every call, and rewrites its own script after 50 calls using Claude meta-analysis.

## Architecture

```
Landing Page (Next.js)
    ↓ POST /api/lead
FastAPI Backend
    ↓ score_lead() → Gemini 2.0 Flash
    ↓ tier: high=5min, medium=15min, low=60min
    ↓ trigger_call() → Vapi API
Vapi Voice Agent (ARIA)
    ↓ POST /webhooks/vapi  (end-of-call-report)
FastAPI Backend
    ↓ critique_call() → Claude Sonnet (force_openai)
    ↓ insert_call() → Supabase
    ↓ every 50 calls → run_improvement_cycle()
        ↓ cascade_ai_call() → meta-analysis
        ↓ _update_vapi_assistant() → PATCH Vapi API
        ↓ insert_prompt_version() → Supabase
Streamlit Dashboard → Supabase (read-only)
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
SUPABASE_SERVICE_KEY  # Supabase service key (backend only — bypasses RLS)
GEMINI_API_KEY        # Primary AI — cheapest
GROK_API_KEY          # Fallback AI
OPENAI_API_KEY        # Final fallback
ANTHROPIC_API_KEY     # Claude Sonnet for critique (quality-critical)
VAPI_API_KEY          # Vapi voice platform
VAPI_ASSISTANT_ID     # Your Vapi assistant UUID
VAPI_PHONE_NUMBER_ID  # Your Vapi phone number UUID
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

See `prd.json` for the complete story history. All 17 stories are done. Story srs-018 (git push) requires manual execution.

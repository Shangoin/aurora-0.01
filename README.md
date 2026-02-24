# 🛰 Shango Revenue Systems — Autonomous AI Sales Agent

> **Lead → Score → Call → Critique → Improve. Zero humans. Infinite scale.**

Built on the Syntropy tech stack by Shango. Every component maps directly to learnable skills. The system gets smarter after every 50 calls — automatically.

---

## What This Does

A lead fills out your landing page. Within 5 minutes:

1. **AI scores them** (Gemini Flash, ~$0.001) — tier: high/medium/low
2. **Vapi calls them** — AI voice agent asks discovery questions
3. **Claude critiques the call** — 7 category scores, pain points extracted
4. **Script improvements queued** — high-impact fixes stored for next cycle
5. **Every 50 calls:** Claude rewrites the agent's own prompt → Vapi updated
6. **Follow-ups automated** — email/SMS sequences via n8n if no booking
7. **Dashboard shows everything** — real-time pipeline view

**You wake up to booked meetings.**

---

## Architecture

```
Landing Page (Next.js/Vercel)
        │ POST /api/lead
        ▼
FastAPI Backend (Render/Fly.io)
        │ AI Cascade: Gemini → Grok → OpenAI
        │ Score lead (< $0.001)
        │ Trigger Vapi call (async, delayed by tier)
        ▼
Vapi Voice AI ──► Webhook ──► FastAPI /webhooks/vapi
                                  │
                           Claude Critique
                           7-category scoring
                                  │
                          Supabase (PostgreSQL)
                          leads | calls | improvements | prompt_versions
                                  │
                   Every 50 calls: Self-Improvement Cycle
                   Claude meta-analysis → New prompt → Vapi updated
                                  │
                   Streamlit Dashboard (real-time)
                   + n8n Follow-Up Automation
```

### AI Cost Stack (Cheapest First)

| Task | Model | Cost/Call | Monthly (100 leads) |
|------|-------|-----------|---------------------|
| Lead Scoring | Gemini 2.0 Flash | ~$0.001 | ~$0.10 |
| Post-Call Critique | Claude Sonnet | ~$0.02 | ~$2.00 |
| Self-Improvement | Claude Sonnet | ~$0.10/cycle | ~$0.40 |
| **Voice Call (Vapi)** | ElevenLabs + Deepgram | ~$0.05–0.20/min | ~$10–40 |
| **Total** | | | **~$15/month** |

---

## 10-Day Build Plan

Based on the Shango Revenue Systems × Syntropy mastery matrix (77 hours, 26 sessions):

| Day | Component | Key Tech |
|-----|-----------|----------|
| 1 | Landing Page + Supabase | Next.js, Vercel, PostgreSQL |
| 2 | n8n Workflows | n8n Cloud, Supabase webhooks |
| 3 | AI Lead Scoring | Gemini Flash, CoT prompting |
| 4 | Vapi Voice AI | Vapi, ElevenLabs, call trigger |
| 5 | Post-Call Critique | Claude Sonnet, 7-category rubric |
| 6 | Streamlit Dashboard | Plotly, Supabase, dark theme |
| 7 | Self-Improvement Loop | LangGraph state machine concepts |
| 8 | Guardrails + Hardening | Error handling, rate limits |
| 9 | Docker + CI/CD | GitHub Actions, Render deploy |
| 10 | Full System Test | End-to-end demo, metrics baseline |

---

## Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- Supabase account (free)
- At least one AI API key (Gemini recommended — cheapest)
- Vapi account for voice calls (optional — system works without it)

### 1. Database Setup

```sql
-- Run in Supabase SQL Editor
-- File: supabase/schema.sql
```

### 2. Backend Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt

# Copy .env.example → .env and fill in your keys
copy ..\\.env.example .env

uvicorn main:app --reload --port 8000
# → http://localhost:8000/docs
```

### 3. Dashboard Setup

```powershell
cd dashboard
pip install streamlit supabase pandas plotly

# Create .streamlit/secrets.toml:
# SUPABASE_URL = "..."
# SUPABASE_KEY = "..."
# BACKEND_URL = "http://localhost:8000"

streamlit run dashboard.py
# → http://localhost:8501
```

### 4. Landing Page Setup

```powershell
cd landing
npm install
# Set NEXT_PUBLIC_BACKEND_URL in .env.local
npm run dev
# → http://localhost:3000
```

### 5. n8n Setup

1. Create account at [n8n.io](https://n8n.io)
2. Import `n8n/followup_and_notifications.json`
3. Configure credentials: Supabase DB, Resend (email), Slack
4. Activate workflows

### 6. Production Deploy

```powershell
# Docker (all services)
docker compose up -d --build

# Or individual:
# Backend → Render.com (free tier)
# Dashboard → Streamlit Community Cloud (free)
# Landing → Vercel (free)
```

---

## Project Structure

```
aurora-0.01/
├── backend/
│   ├── main.py              # FastAPI app, health, stats endpoints
│   ├── models.py            # All Pydantic types and enums
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── api/
│   │   ├── leads.py         # POST /api/lead — ingest, score, trigger call
│   │   └── webhooks.py      # POST /webhooks/vapi — call ended handler
│   ├── ai/
│   │   ├── orchestrator.py  # Cascade: Gemini → Grok → OpenAI + cache
│   │   ├── scoring.py       # Lead qualification (few-shot CoT)
│   │   ├── critique.py      # Post-call analysis (7 categories)
│   │   └── improvement.py   # Self-improvement loop + Vapi trigger
│   └── db/
│       └── supabase.py      # All DB operations
├── dashboard/
│   ├── dashboard.py         # 5-page Streamlit command center
│   └── Dockerfile
├── landing/
│   ├── src/app/page.tsx     # Lead capture form (Next.js)
│   └── package.json
├── supabase/
│   └── schema.sql           # Complete DB schema with seed data
├── n8n/
│   └── followup_and_notifications.json  # Follow-up + Slack workflow
├── docker-compose.yml
└── .env.example
```

---

## Key Patterns (Syntropy Tech Stack)

### AI Cascade (`backend/ai/orchestrator.py`)
```python
# CORRECT: Always use cascade for cost optimization
result = await cascade_ai_call(prompt, task_type="lead_scoring")

# Quality-critical tasks use Claude/GPT-4o
critique = await cascade_ai_call(prompt, force_openai=True)
```

### Self-Improvement Loop
The system is a state machine:
```
State: { current_prompt, call_history, improvements_pending }
Transitions:
  analyze_calls() → propose_improvements() → update_vapi() → monitor_scores()
```

After every 50 calls, Claude:
1. Reads all critique summaries
2. Identifies top 3 failure patterns
3. Rewrites the Vapi agent's system prompt
4. Pushes it live via Vapi API
5. Stores version in `prompt_versions` table

### Guardrails
- Rate limiting at `/api/lead` endpoint
- Input validation (fake email detection)
- PII not sent to AI — only metadata (score, tier, summary)
- All decisions logged in `audit_log` table

---

## Vapi Configuration

1. Create assistant at [dashboard.vapi.ai](https://dashboard.vapi.ai)
2. Set the initial system prompt from `prompt_versions` table (v1 is seeded)
3. Set server URL: `https://your-backend.onrender.com/webhooks/vapi`
4. Configure voice: ElevenLabs (Rachel or Bella — most natural)
5. Configure transcriber: Deepgram Nova-2
6. Add phone number (US: ~$2/month)

The system auto-updates the assistant prompt every 50 calls via:
```
PUT https://api.vapi.ai/assistant/{ASSISTANT_ID}
Body: { "model": { "systemPrompt": "..." } }
```

---

## Performance Targets

| Metric | Target | Measured |
|--------|--------|----------|
| Time to first call | < 5 min | — |
| Lead scoring latency | < 2 sec | — |
| Call critique latency | < 90 sec post-call | — |
| Dashboard refresh | 30 sec | ✓ (Streamlit ttl) |
| Conversion rate improvement | +5% per cycle | — |

---

## The 0.01% Flywheel

```
Lead submits → Scored in 2s → Called in 5 min
     ↑                                    ↓
Prompt v(n+1) ← Self-improve ← Critique 50 calls
     ↑                                    ↓
Vapi updated  ← Meta-analysis ← Pain points extracted
```

Most sales teams run static scripts. Shango Revenue Systems' script evolves every 50 calls based on real call data. After 6 months: the prompt has been rewritten 10+ times, optimized on hundreds of real conversations. **That's the 0.01% edge.**

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Calls not triggering | Check `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` in `.env` |
| Critique returning empty | Transcript too short (< 50 chars) — check Vapi transcription settings |
| Gemini quota exceeded | Free tier limit hit — add OpenAI key as fallback |
| Dashboard not loading | Check `SUPABASE_URL` and `SUPABASE_KEY` in secrets.toml |
| Improvement cycle skipped | Need 5+ calls in DB to trigger analysis |

---

Built with:  [Syntropy](https://github.com/shango-apex) tech stack — FastAPI, Supabase, Gemini/Grok/OpenAI cascade, Streamlit

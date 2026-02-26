"""
AURORA 1.0 — FastAPI Main Application
Autonomous AI SDR: 6-LLM Cascade · MARS Reflective Loop · Geo-Routing
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("aurora")

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start nurture scheduler
    from nurture.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()
    logger.info("🛰  AURORA 1.0 booting up — 6-LLM · MARS · Geo-Routing · Nurture")
    # 6-provider cascade
    logger.info(f"  Gemini:    {'✓' if os.environ.get('GEMINI_API_KEY') else '✗'}")
    logger.info(f"  Groq:      {'✓' if os.environ.get('GROK_API_KEY') else '✗'}")
    logger.info(f"  Cerebras:  {'✓' if os.environ.get('CEREBRAS_API_KEY') else '✗'}")
    logger.info(f"  Mistral:   {'✓' if os.environ.get('MISTRAL_API_KEY') else '✗'}")
    logger.info(f"  OpenRouter:{'✓' if os.environ.get('OPENROUTER_API_KEY') else '✗'}")
    logger.info(f"  OpenAI:    {'✓' if os.environ.get('OPENAI_API_KEY') else '✗ (last resort)'}")
    logger.info(f"  Claude:    {'✓' if os.environ.get('ANTHROPIC_API_KEY') else '✗'}")
    # Vapi geo numbers
    logger.info(f"  Vapi:      {'✓' if os.environ.get('VAPI_API_KEY') else '✗ (calls disabled)'}")
    logger.info(f"  Vapi IN:   {'✓' if os.environ.get('VAPI_PHONE_NUMBER_ID_IN') else '–'}")
    logger.info(f"  Vapi US:   {'✓' if os.environ.get('VAPI_PHONE_NUMBER_ID_US') else '–'}")
    logger.info(f"  Vapi UK:   {'✓' if os.environ.get('VAPI_PHONE_NUMBER_ID_UK') else '–'}")
    logger.info(f"  Supabase:  {'✓' if os.environ.get('SUPABASE_URL') else '✗'}")
    yield
    from nurture.scheduler import stop_scheduler
    await stop_scheduler()
    logger.info("AURORA shutting down")

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AURORA 1.0 — AI SDR API",
    description="Autonomous AI SDR: 6-LLM Cascade · MARS Reflective Loop · Geo-Routing · 9-Category Critique",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

origins = os.getenv("ALLOWED_ORIGINS", 
    "https://shango.in,https://www.shango.in,https://shango-landing.vercel.app,http://localhost:3000"
).split(",")
origins = [o.strip() for o in origins if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routes ───────────────────────────────────────────────────────────────────

from api.leads import router as leads_router
from api.webhooks import router as webhooks_router
from api.nurture import router as nurture_router

app.include_router(leads_router)
app.include_router(webhooks_router)
app.include_router(nurture_router)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    import db.supabase as _supabase
    try:
        sb = _supabase.get_supabase_client()
        sb.table("leads").select("id").limit(1).execute()
        db_ok = True
    except Exception:
        db_ok = False

    from nurture.scheduler import is_scheduler_running
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "error",
        "ai_cascade": {
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "groq": bool(os.environ.get("GROK_API_KEY")),
            "cerebras": bool(os.environ.get("CEREBRAS_API_KEY")),
            "mistral": bool(os.environ.get("MISTRAL_API_KEY")),
            "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "vapi": bool(os.environ.get("VAPI_API_KEY")),
        "geo_numbers": {
            "in": bool(os.environ.get("VAPI_PHONE_NUMBER_ID_IN")),
            "us": bool(os.environ.get("VAPI_PHONE_NUMBER_ID_US")),
            "uk": bool(os.environ.get("VAPI_PHONE_NUMBER_ID_UK")),
            "global": bool(os.environ.get("VAPI_PHONE_NUMBER_ID_GLOBAL")),
        },
        "nurture_scheduler": is_scheduler_running(),
    }


# ─── Stats (for dashboard) ────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    from db.supabase import get_supabase
    sb = get_supabase()
    
    leads = sb.table("leads").select("id, status, score, tier, created_at").execute()
    calls = sb.table("calls").select("id, overall_score, meeting_booked, cost_usd").execute()
    improvements = sb.table("agent_improvements").select("id").eq("status", "pending_review").execute()
    prompt = sb.table("prompt_versions").select("version").eq("is_active", True).limit(1).execute()

    leads_data = leads.data or []
    calls_data = calls.data or []

    total_leads = len(leads_data)
    meetings = sum(1 for l in leads_data if l.get("status") == "meeting_booked")
    scores = [c.get("overall_score", 0) for c in calls_data if c.get("overall_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    total_cost = sum(float(c.get("cost_usd") or 0) for c in calls_data)

    return {
        "total_leads": total_leads,
        "calls_made": len(calls_data),
        "meetings_booked": meetings,
        "avg_call_score": round(avg_score, 1),
        "conversion_rate": round(meetings / total_leads * 100, 1) if total_leads else 0,
        "total_cost_usd": round(total_cost, 4),
        "pending_improvements": len(improvements.data or []),
        "active_prompt_version": prompt.data[0]["version"] if prompt.data else 1,
    }


# ─── Provider Stats ──────────────────────────────────────────────────────────

@app.get("/api/provider-stats")
async def provider_stats():
    """Per-provider LLM usage: calls, failures, avg latency (ms). Resets on restart."""
    from ai.orchestrator import get_provider_stats
    return get_provider_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("ENV", "development") == "development",
    )

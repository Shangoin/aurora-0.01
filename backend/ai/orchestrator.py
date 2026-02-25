"""
AURORA 1.0 — AI Cascade Orchestrator (6-Provider ₹0 Stack)
Gemini 2.0 Flash → Groq 3.3 70B → Cerebras 70B → Mistral Small → DeepSeek V3 → GPT-4o-mini
24-hour response cache using in-memory LRU. Provider performance tracked per-session.
"""
import os
import json
import hashlib
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.ai")

# ─── Provider registry ────────────────────────────────────────────────────────

PROVIDERS = [
    "gemini-2.0-flash",          # Primary:     Free 15 RPM, 1M context
    "groq/llama-3.3-70b",         # Speed:       Free 6k req/day, 128K context
    "cerebras/llama-3.3-70b",    # Tokens:      1M tokens/day free
    "mistral/small",             # Multilingual: 1B tokens/mo free (Hindi/EU)
    "openrouter/deepseek-v3",    # Reasoning:   Free 50 req/day, 77.9% MMLU
    "openai/gpt-4o-mini",        # Last resort: ~$0.15/M tokens
]

# Per-session provider performance tracking (resets on restart)
_stats: dict[str, dict] = {
    p: {"calls": 0, "failures": 0, "total_ms": 0} for p in PROVIDERS
}

# ─── 24-hour in-memory cache ──────────────────────────────────────────────────

_cache: dict[str, tuple[str, datetime]] = {}
CACHE_TTL = timedelta(hours=24)


def _cache_key(prompt: str, task: str) -> str:
    return hashlib.sha256(f"{task}:{prompt}".encode()).hexdigest()[:32]


def _cache_get(key: str) -> str | None:
    entry = _cache.get(key)
    if entry and datetime.utcnow() - entry[1] < CACHE_TTL:
        return entry[0]
    return None


def _cache_set(key: str, value: str) -> None:
    _cache[key] = (value, datetime.utcnow())
    if len(_cache) > 1000:
        oldest = sorted(_cache.items(), key=lambda x: x[1][1])[:100]
        for k, _ in oldest:
            del _cache[k]


# ─── Provider implementations ────────────────────────────────────────────────

async def _call_gemini(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """Gemini 2.0 Flash — free 15 RPM, 1M token context (primary)."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.2,
        ),
    )
    return response.text


async def _call_groq(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """Groq — Llama 3.3 70B, 6k req/day free, 128K context (speed demon)."""
    import httpx
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": min(max_tokens, 8000),
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_cerebras(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """Cerebras — Llama 3.3 70B, 1M tokens/day free (OpenAI-compat API)."""
    import httpx
    payload = {
        "model": "llama-3.3-70b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.cerebras.ai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['CEREBRAS_API_KEY']}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_mistral(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """Mistral Small — 1B tokens/month free, multilingual (Hindi/English)."""
    import httpx
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_openrouter_deepseek(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """DeepSeek V3 via OpenRouter — free 50 req/day, 77.9% MMLU reasoning."""
    import httpx
    payload = {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                "HTTP-Referer": "https://shango.ai",
                "X-Title": "Aurora SDR",
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_openai(prompt: str, system: str, max_tokens: int = 2000) -> str:
    """GPT-4o-mini — absolute last resort (~$0.15/M tokens)."""
    import httpx
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ─── Ordered cascade list ─────────────────────────────────────────────────────

_PROVIDER_CALLS = [
    ("gemini-2.0-flash",          "GEMINI_API_KEY",       _call_gemini),
    ("groq/llama-3.3-70b",         "GROQ_API_KEY",         _call_groq),
    ("cerebras/llama-3.3-70b",    "CEREBRAS_API_KEY",     _call_cerebras),
    ("mistral/small",             "MISTRAL_API_KEY",      _call_mistral),
    ("openrouter/deepseek-v3",    "OPENROUTER_API_KEY",   _call_openrouter_deepseek),
    ("openai/gpt-4o-mini",        "OPENAI_API_KEY",       _call_openai),
]


# ─── Main Cascade ─────────────────────────────────────────────────────────────

async def cascade_ai_call(
    prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
    task_type: str = "general",
    max_tokens: int = 2000,
    use_cache: bool = True,
    force_openai: bool = False,  # Kept for API compatibility — unused
) -> str:
    """
    ₹0 AI cascade — 6 providers in cost-priority order:
      Gemini → Groq → Cerebras → Mistral → DeepSeek → GPT-4o-mini

    Each provider is tried only if its API key is set.
    Falls through to next on any exception.
    """
    if use_cache:
        key = _cache_key(prompt, task_type)
        cached = _cache_get(key)
        if cached:
            logger.debug(f"Cache hit: {task_type}")
            return cached

    result = None

    for provider_name, env_key, call_fn in _PROVIDER_CALLS:
        if not os.environ.get(env_key):
            continue
        t0 = time.monotonic()
        try:
            result = await call_fn(prompt, system_prompt, max_tokens)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _stats[provider_name]["calls"] += 1
            _stats[provider_name]["total_ms"] += elapsed_ms
            logger.info(f"AI cascade: {provider_name} served {task_type} ({elapsed_ms}ms)")
            break
        except Exception as e:
            _stats[provider_name]["failures"] += 1
            logger.warning(f"{provider_name} failed for {task_type}: {e}")

    if not result:
        raise RuntimeError(f"All 6 AI providers failed for task: {task_type}")

    if use_cache:
        _cache_set(_cache_key(prompt, task_type), result)

    return result


def get_provider_stats() -> dict:
    """Return per-provider call statistics for dashboard."""
    return {
        name: {
            "calls": s["calls"],
            "failures": s["failures"],
            "avg_latency_ms": round(s["total_ms"] / s["calls"], 0) if s["calls"] else 0,
            "success_rate": round((s["calls"] - s["failures"]) / s["calls"] * 100, 1) if s["calls"] else 0,
        }
        for name, s in _stats.items()
    }


def parse_json_response(text: str) -> dict | list:
    """Extract JSON from AI response — handles ```json blocks and raw JSON."""
    import re
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match2 = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", text)
        if match2:
            return json.loads(match2.group(1))
        raise ValueError(f"Could not parse JSON from AI response: {text[:200]}")


def humanize_text(text: str) -> str:
    """Strip AI-speak artifacts."""
    replacements = {
        "utilize": "use", "leverage": "use",
        "groundbreaking": "new", "revolutionary": "different",
        "paradigm": "approach", "robust": "strong",
        "seamless": "smooth", "empower": "help",
        "delve": "look", "multifaceted": "complex",
        " — ": ", ", "—": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

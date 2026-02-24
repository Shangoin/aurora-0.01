"""
Shango Revenue Systems — AI Cascade Orchestrator
Pattern: Gemini 2.0 Flash (free) → Groq Llama 3.3 70B (free) → GPT-4o-mini (cheap fallback)
24-hour response cache using in-memory LRU
"""
import os
import json
import hashlib
import logging
from typing import Any
from functools import lru_cache
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.ai")

# ─── Simple 24-hour cache ─────────────────────────────────────────────────────

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
    # Trim if > 1000 entries
    if len(_cache) > 1000:
        oldest = sorted(_cache.items(), key=lambda x: x[1][1])[:100]
        for k, _ in oldest:
            del _cache[k]


# ─── Provider calls ──────────────────────────────────────────────────────────

async def _call_gemini(prompt: str, system: str, max_tokens: int = 2000) -> str:
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
    """Groq free tier — Llama 3.3 70B, 6000 req/day, 128K context."""
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['GROK_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_openai(prompt: str, system: str, max_tokens: int = 2000, model: str = "gpt-4o-mini") -> str:
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ─── Main Cascade ─────────────────────────────────────────────────────────────

async def cascade_ai_call(
    prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
    task_type: str = "general",
    max_tokens: int = 2000,
    use_cache: bool = True,
    force_openai: bool = False,  # Kept for API compatibility — ignored, Gemini handles all tasks
) -> str:
    """
    Cost-optimized AI cascade (all free/cheap):
      Gemini 2.0 Flash (free 15 req/min) ─► Groq Llama 3.3 70B (free 6000/day) ─► GPT-4o-mini (fallback)
    """
    if use_cache:
        key = _cache_key(prompt, task_type)
        cached = _cache_get(key)
        if cached:
            logger.debug(f"Cache hit: {task_type}")
            return cached

    result = None

    # 1. Gemini 2.0 Flash — free tier, 1M token context
    if os.environ.get("GEMINI_API_KEY"):
        try:
            result = await _call_gemini(prompt, system_prompt, max_tokens)
            logger.info(f"AI cascade: Gemini served {task_type}")
        except Exception as e:
            logger.warning(f"Gemini failed for {task_type}: {e}")

    # 2. Groq Llama 3.3 70B — free 6000 req/day, 128K context
    if not result and os.environ.get("GROK_API_KEY"):
        try:
            result = await _call_groq(prompt, system_prompt, max_tokens)
            logger.info(f"AI cascade: Groq served {task_type}")
        except Exception as e:
            logger.warning(f"Groq failed for {task_type}: {e}")

    # 3. GPT-4o-mini — last resort fallback (~$0.15/M tokens)
    if not result and os.environ.get("OPENAI_API_KEY"):
        try:
            result = await _call_openai(prompt, system_prompt, max_tokens)
            logger.info(f"AI cascade: OpenAI served {task_type}")
        except Exception as e:
            logger.warning(f"OpenAI failed for {task_type}: {e}")

    if not result:
        raise RuntimeError(f"All AI providers failed for task: {task_type}")

    if use_cache:
        _cache_set(_cache_key(prompt, task_type), result)

    return result


def parse_json_response(text: str) -> dict | list:
    """
    Extract JSON from AI response — handles ```json blocks and raw JSON.
    """
    import re
    text = text.strip()
    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try extracting first JSON object/array
        match2 = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", text)
        if match2:
            return json.loads(match2.group(1))
        raise ValueError(f"Could not parse JSON from AI response: {text[:200]}")


def humanize_text(text: str) -> str:
    """Strip AI-speak artifacts"""
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

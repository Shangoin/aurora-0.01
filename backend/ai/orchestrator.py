"""
AURORA — AI Cascade Orchestrator
Pattern: Gemini Flash (cheapest) → Grok → OpenAI GPT-4o-mini (fallback)
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


async def _call_grok(prompt: str, system: str, max_tokens: int = 2000) -> str:
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['GROK_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers)
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
    force_openai: bool = False,  # Set True for critique (quality matters most)
) -> str:
    """
    Cost-optimized AI cascade:
      Gemini 2.0 Flash (cheapest) ─► Grok 3 Mini ─► GPT-4o-mini
    
    For quality-critical tasks (critique), set force_openai=True to use Claude
    via the Anthropic API, or GPT-4o.
    """
    # Check cache first
    if use_cache:
        key = _cache_key(prompt, task_type)
        cached = _cache_get(key)
        if cached:
            logger.debug(f"Cache hit: {task_type}")
            return cached

    result = None

    # 1. Try Gemini Flash (cheapest — ~$0.075/M input tokens)
    if not force_openai and os.environ.get("GEMINI_API_KEY"):
        try:
            result = await _call_gemini(prompt, system_prompt, max_tokens)
            logger.info(f"AI cascade: Gemini served {task_type}")
        except Exception as e:
            logger.warning(f"Gemini failed for {task_type}: {e}")

    # 2. Try Grok 3 Mini (backup)
    if not result and os.environ.get("GROK_API_KEY"):
        try:
            result = await _call_grok(prompt, system_prompt, max_tokens)
            logger.info(f"AI cascade: Grok served {task_type}")
        except Exception as e:
            logger.warning(f"Grok failed for {task_type}: {e}")

    # 3. Try Anthropic Claude (for quality-critical tasks)
    if (not result or force_openai) and os.environ.get("ANTHROPIC_API_KEY") and force_openai:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            result = msg.content[0].text
            logger.info(f"AI cascade: Claude served {task_type}")
        except Exception as e:
            logger.warning(f"Claude failed for {task_type}: {e}")

    # 4. Fallback GPT-4o-mini
    if not result:
        result = await _call_openai(prompt, system_prompt, max_tokens)
        logger.info(f"AI cascade: OpenAI served {task_type}")

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

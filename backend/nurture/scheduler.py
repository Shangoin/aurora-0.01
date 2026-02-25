"""
Aurora 1.0 — Nurture Scheduler
APScheduler background task that advances active nurture sequences every 15 min.
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def _tick() -> None:
    """Check all active nurture sequences and advance any that are due."""
    try:
        from db.supabase import get_active_nurture_sequences
        from nurture.agent import get_nurture_agent

        sequences = await get_active_nurture_sequences()
        if not sequences:
            return

        agent = get_nurture_agent()
        for seq in sequences:
            try:
                await agent.advance_sequence(seq)
            except Exception as exc:
                logger.error("Nurture scheduler: error advancing sequence %s — %s", seq.get("id"), exc)
    except Exception as exc:
        logger.error("Nurture scheduler tick error: %s", exc)


async def start_scheduler() -> None:
    """Start the APScheduler background tick (call from FastAPI lifespan)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _tick,
        trigger=IntervalTrigger(minutes=15),
        id="nurture_tick",
        name="Advance nurture sequences",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Nurture scheduler started — checking every 15 min")


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully (call from FastAPI lifespan shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Nurture scheduler stopped")
    _scheduler = None


def is_scheduler_running() -> bool:
    """Return True if the APScheduler is currently running."""
    return bool(_scheduler and _scheduler.running)

"""
Aurora 1.0 — Lead Nurture Module
Orchestrates follow-up sequences: email + call cadences driven by OpenClaw agent.
"""
from .agent import NurtureAgent
from .scheduler import start_scheduler, stop_scheduler, is_scheduler_running

__all__ = ["NurtureAgent", "start_scheduler", "stop_scheduler", "is_scheduler_running"]

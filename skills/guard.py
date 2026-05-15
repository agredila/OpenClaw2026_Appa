"""
Guard — cross-cutting rate limiter and cost guard.

Called by APPA before delegating to any worker agent.
Prevents runaway API costs and enforces daily limits.
"""
from __future__ import annotations

import os
from base import get_daily_usage, increment_daily_usage


class DailyLimitExceeded(Exception):
    pass


class AgentTimeout(Exception):
    pass


def check_and_increment(user_id: str) -> int:
    """
    Check daily limit then increment counter.
    Raises DailyLimitExceeded if limit is reached.
    Returns new count on success.
    """
    limit = int(os.environ.get("MAX_OPPORTUNITIES_PER_DAY", 20))
    current = get_daily_usage(user_id)
    if current >= limit:
        raise DailyLimitExceeded(
            f"Daily limit of {limit} opportunities reached. "
            f"Processed today: {current}."
        )
    return increment_daily_usage(user_id)


def run_with_timeout(fn, timeout_seconds: int | None = None):
    """
    Run fn() with a timeout. Raises AgentTimeout if exceeded.
    Uses threading so it works without async context.
    """
    import threading

    limit = timeout_seconds or int(os.environ.get("AGENT_TIMEOUT_SECONDS", 30))
    result = [None]
    error = [None]

    def target():
        try:
            result[0] = fn()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=limit)

    if thread.is_alive():
        raise AgentTimeout(f"Agent exceeded {limit}s timeout.")
    if error[0]:
        raise error[0]
    return result[0]

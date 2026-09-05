"""
Trading hours utility for A-share continuous auction sessions.

Only returns True during 9:30-11:30 and 13:00-15:00 on weekdays.
Auction periods (9:15-9:25) and weekends are excluded.
No holiday calendar — simple weekday + time check.
"""
from __future__ import annotations

from datetime import datetime, time

# Morning continuous auction
_MORNING_START = time(9, 30)
_MORNING_END = time(11, 30)
# Afternoon continuous auction
_AFTERNOON_START = time(13, 0)
_AFTERNOON_END = time(15, 0)


def is_continuous_auction(now: datetime | None = None) -> bool:
    """Return True if we are inside A-share continuous auction hours on a trading weekday."""
    if now is None:
        now = datetime.now()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now.time()
    return (_MORNING_START <= t <= _MORNING_END) or (_AFTERNOON_START <= t <= _AFTERNOON_END)

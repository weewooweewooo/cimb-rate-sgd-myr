"""Decide whether a user should get an alert for the current best rate."""
from __future__ import annotations

from datetime import datetime

from models import User
from settings import REALERT_STEP

_EPSILON = 1e-9


def decide(user: User, best_rate: float, now: datetime) -> str:
    """Return "alert", "reset" or "none"."""
    if not user.enabled:
        return "none"
    if best_rate < user.target_rate:
        # Only forget the last alert after a clear drop, so a rate wobbling around
        # the target (3.1599 <-> 3.1601) doesn't re-alert on every crossing.
        clear_drop = best_rate <= user.target_rate - REALERT_STEP + _EPSILON
        return "reset" if user.peak_rate > 0 and clear_drop else "none"
    if user.peak_rate <= 0:
        return "alert"
    if best_rate >= user.peak_rate + REALERT_STEP - _EPSILON:
        return "alert"
    return "none"

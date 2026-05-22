from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class AlertDecision:
    alert_threshold: float
    should_send_alert: bool
    alert_reason: str
    next_interval_seconds: int
    band: Literal["outside", "normal", "near", "critical", "alert"]
    cooldown_remaining_seconds: int


def calculate_alert_threshold(target_rate: float, buffer: float) -> float:
    return float(target_rate - buffer)


def evaluate_monitoring(
    *,
    current_rate: float,
    target_rate: float,
    buffer: float,
    near_target_gap: float,
    critical_gap: float,
    normal_seconds: int,
    near_target_seconds: int,
    critical_seconds: int,
    cooldown_minutes: int,
    active_window: bool,
    now: datetime,
    last_alerted_at: datetime | None,
) -> AlertDecision:
    alert_threshold = calculate_alert_threshold(target_rate, buffer)
    cooldown_remaining = cooldown_remaining_seconds(
        now=now,
        last_alerted_at=last_alerted_at,
        cooldown_minutes=cooldown_minutes,
    )

    if not active_window:
        return AlertDecision(
            alert_threshold=alert_threshold,
            should_send_alert=False,
            alert_reason="outside active window",
            next_interval_seconds=300,
            band="outside",
            cooldown_remaining_seconds=cooldown_remaining,
        )

    if current_rate >= alert_threshold:
        should_alert = cooldown_remaining <= 0
        reason = "threshold reached" if should_alert else "cooldown active"

        next_interval = normal_seconds
        if cooldown_remaining > 0:
            next_interval = min(normal_seconds, max(1, cooldown_remaining))

        return AlertDecision(
            alert_threshold=alert_threshold,
            should_send_alert=should_alert,
            alert_reason=reason,
            next_interval_seconds=next_interval,
            band="alert",
            cooldown_remaining_seconds=cooldown_remaining,
        )

    if current_rate >= (target_rate - critical_gap):
        return AlertDecision(
            alert_threshold=alert_threshold,
            should_send_alert=False,
            alert_reason="critical proximity",
            next_interval_seconds=critical_seconds,
            band="critical",
            cooldown_remaining_seconds=cooldown_remaining,
        )

    if current_rate >= (target_rate - near_target_gap):
        return AlertDecision(
            alert_threshold=alert_threshold,
            should_send_alert=False,
            alert_reason="near target",
            next_interval_seconds=near_target_seconds,
            band="near",
            cooldown_remaining_seconds=cooldown_remaining,
        )

    return AlertDecision(
        alert_threshold=alert_threshold,
        should_send_alert=False,
        alert_reason="normal monitoring",
        next_interval_seconds=normal_seconds,
        band="normal",
        cooldown_remaining_seconds=cooldown_remaining,
    )


def cooldown_remaining_seconds(
    *, now: datetime, last_alerted_at: datetime | None, cooldown_minutes: int
) -> int:
    if last_alerted_at is None:
        return 0

    elapsed = (now - last_alerted_at).total_seconds()
    cooldown_seconds = cooldown_minutes * 60
    remaining = int(cooldown_seconds - elapsed)
    return max(0, remaining)

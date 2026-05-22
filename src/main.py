from __future__ import annotations

import argparse
import time
from dataclasses import replace
from datetime import datetime

from .alert_engine import AlertDecision, evaluate_monitoring
from .cimb_fetcher import CimbRateResult, fetch_cimb_rate
from .config_loader import AppConfig, ConfigError, load_config
from .notifier_pushover import NotificationError, send_pushover_alert
from .state_store import AgentState, load_state, save_state
from .time_utils import is_within_active_window, now_in_timezone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIMB SGD->MYR rate hunter agent")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit")
    parser.add_argument("--headful", action="store_true", help="Run Playwright in headful mode")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run alerts")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config("config.yaml")
    except (FileNotFoundError, ConfigError, ValueError) as exc:
        print(f"Config error: {exc}")
        return 1

    if args.dry_run:
        config = replace(config, alerts=replace(config.alerts, dry_run=True))

    if not config.agent.enabled:
        print("Agent is disabled by config (agent.enabled=false). Exiting.")
        return 0

    state = load_state("state.json")
    headless = not args.headful

    try:
        while True:
            now = now_in_timezone(config.agent.timezone)
            active_window = is_within_active_window(
                now, config.monitoring.active_start, config.monitoring.active_end
            )

            if not active_window and not args.once:
                print(
                    f"[{now.isoformat()}] Active window: OFF "
                    f"({config.monitoring.active_start}-{config.monitoring.active_end}) | "
                    "next_sleep=300s"
                )
                time.sleep(300)
                continue

            state, sleep_seconds = run_single_check(
                config=config,
                state=state,
                now=now,
                active_window=active_window,
                headless=headless,
            )
            save_state(state, "state.json")

            if args.once:
                return 0

            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        print("Interrupted by user. Exiting cleanly.")
        return 0


def run_single_check(
    *,
    config: AppConfig,
    state: AgentState,
    now: datetime,
    active_window: bool,
    headless: bool,
) -> tuple[AgentState, int]:
    try:
        result = fetch_cimb_rate(headless=headless)
    except Exception as exc:  # noqa: BLE001
        print(f"[{now.isoformat()}] Rate fetch failed: {exc}")
        state.last_checked_at = now.isoformat()
        return state, config.intervals.normal_seconds

    last_alerted_at = _parse_dt(state.last_alerted_at)
    decision = evaluate_monitoring(
        current_rate=result.rate,
        target_rate=config.rate.target_rate,
        buffer=config.rate.buffer,
        near_target_gap=config.thresholds.near_target_gap,
        critical_gap=config.thresholds.critical_gap,
        normal_seconds=config.intervals.normal_seconds,
        near_target_seconds=config.intervals.near_target_seconds,
        critical_seconds=config.intervals.critical_seconds,
        cooldown_minutes=config.alerts.cooldown_minutes,
        active_window=active_window,
        now=now,
        last_alerted_at=last_alerted_at,
    )

    print_status(config=config, now=now, result=result, decision=decision, active_window=active_window)

    if decision.should_send_alert:
        title = "CIMB SGD->MYR Alert"
        message = (
            f"Rate {result.rate:.4f} reached threshold {decision.alert_threshold:.4f} "
            f"(target {config.rate.target_rate:.4f}, buffer {config.rate.buffer:.4f})"
        )
        try:
            notify_result = send_pushover_alert(
                title=title,
                message=message,
                dry_run=config.alerts.dry_run,
            )
            if notify_result.success:
                print(f"[{now.isoformat()}] Alert status: {notify_result.details}")
                state.last_alerted_at = now.isoformat()
                state.last_alert_rate = result.rate
            else:
                print(f"[{now.isoformat()}] Alert failed: {notify_result.details}")
        except NotificationError as exc:
            print(f"[{now.isoformat()}] Alert configuration error: {exc}")

    state.last_rate = result.rate
    state.last_checked_at = now.isoformat()
    state.alert_active = result.rate >= decision.alert_threshold
    if result.rate < decision.alert_threshold:
        state.alert_active = False

    return state, decision.next_interval_seconds


def print_status(
    *,
    config: AppConfig,
    now: datetime,
    result: CimbRateResult,
    decision: AlertDecision,
    active_window: bool,
) -> None:
    print(
        f"[{now.isoformat()}] rate={result.rate:.4f} "
        f"target={config.rate.target_rate:.4f} buffer={config.rate.buffer:.4f} "
        f"threshold={decision.alert_threshold:.4f} active_window={active_window} "
        f"band={decision.band} next_sleep={decision.next_interval_seconds}s"
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())

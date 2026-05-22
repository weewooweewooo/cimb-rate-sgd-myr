from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when config.yaml exists but is invalid."""


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool
    timezone: str


@dataclass(frozen=True)
class RateConfig:
    provider: str
    from_currency: str
    to_currency: str
    target_rate: float
    buffer: float


@dataclass(frozen=True)
class MonitoringConfig:
    active_start: str
    active_end: str


@dataclass(frozen=True)
class IntervalConfig:
    normal_seconds: int
    near_target_seconds: int
    critical_seconds: int


@dataclass(frozen=True)
class ThresholdConfig:
    near_target_gap: float
    critical_gap: float


@dataclass(frozen=True)
class AlertConfig:
    channel: str
    cooldown_minutes: int
    dry_run: bool


@dataclass(frozen=True)
class AppConfig:
    agent: AgentConfig
    rate: RateConfig
    monitoring: MonitoringConfig
    intervals: IntervalConfig
    thresholds: ThresholdConfig
    alerts: AlertConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}. "
            f"Copy config.example.yaml to {config_path.name} and adjust values."
        )

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ConfigError("config.yaml must contain a top-level YAML mapping.")

    agent = _require_dict(raw, "agent")
    rate = _require_dict(raw, "rate")
    monitoring = _require_dict(raw, "monitoring")
    intervals = _require_dict(raw, "intervals")
    thresholds = _require_dict(raw, "thresholds")
    alerts = _require_dict(raw, "alerts")

    return AppConfig(
        agent=AgentConfig(
            enabled=_require_bool(agent, "agent.enabled"),
            timezone=_require_str(agent, "agent.timezone"),
        ),
        rate=RateConfig(
            provider=_require_str(rate, "rate.provider"),
            from_currency=_require_str(rate, "rate.from_currency"),
            to_currency=_require_str(rate, "rate.to_currency"),
            target_rate=_require_float(rate, "rate.target_rate"),
            buffer=_require_float(rate, "rate.buffer"),
        ),
        monitoring=MonitoringConfig(
            active_start=_require_str(monitoring, "monitoring.active_start"),
            active_end=_require_str(monitoring, "monitoring.active_end"),
        ),
        intervals=IntervalConfig(
            normal_seconds=_require_int(intervals, "intervals.normal_seconds"),
            near_target_seconds=_require_int(intervals, "intervals.near_target_seconds"),
            critical_seconds=_require_int(intervals, "intervals.critical_seconds"),
        ),
        thresholds=ThresholdConfig(
            near_target_gap=_require_float(thresholds, "thresholds.near_target_gap"),
            critical_gap=_require_float(thresholds, "thresholds.critical_gap"),
        ),
        alerts=AlertConfig(
            channel=_require_str(alerts, "alerts.channel"),
            cooldown_minutes=_require_int(alerts, "alerts.cooldown_minutes"),
            dry_run=_require_bool(alerts, "alerts.dry_run"),
        ),
    )


def _require_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing or invalid section: {key}")
    return value


def _require_str(source: dict[str, Any], key: str) -> str:
    local_key = key.split(".")[-1]
    value = source.get(local_key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid string value: {key}")
    return value


def _require_bool(source: dict[str, Any], key: str) -> bool:
    local_key = key.split(".")[-1]
    value = source.get(local_key)
    if not isinstance(value, bool):
        raise ConfigError(f"Missing or invalid boolean value: {key}")
    return value


def _require_int(source: dict[str, Any], key: str) -> int:
    local_key = key.split(".")[-1]
    value = source.get(local_key)
    if not isinstance(value, int):
        raise ConfigError(f"Missing or invalid integer value: {key}")
    return value


def _require_float(source: dict[str, Any], key: str) -> float:
    local_key = key.split(".")[-1]
    value = source.get(local_key)
    if not isinstance(value, (int, float)):
        raise ConfigError(f"Missing or invalid numeric value: {key}")
    return float(value)

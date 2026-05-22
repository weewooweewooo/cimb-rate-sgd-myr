from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentState:
    last_rate: float | None = None
    last_checked_at: str | None = None
    last_alerted_at: str | None = None
    last_alert_rate: float | None = None
    alert_active: bool = False


def load_state(path: str | Path = "state.json") -> AgentState:
    state_path = Path(path)
    if not state_path.exists():
        return AgentState()

    with state_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if not isinstance(raw, dict):
        return AgentState()

    return AgentState(
        last_rate=_as_optional_float(raw.get("last_rate")),
        last_checked_at=_as_optional_str(raw.get("last_checked_at")),
        last_alerted_at=_as_optional_str(raw.get("last_alerted_at")),
        last_alert_rate=_as_optional_float(raw.get("last_alert_rate")),
        alert_active=bool(raw.get("alert_active", False)),
    )


def save_state(state: AgentState, path: str | Path = "state.json") -> None:
    state_path = Path(path)
    payload = asdict(state)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None

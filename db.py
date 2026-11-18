"""SQLite storage: users, rate history, Wise fee, small key/value meta."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from models import User, WiseFee
from settings import DEFAULT_TARGET

log = logging.getLogger(__name__)

_USER_FIELDS = tuple(f.name for f in fields(User))
_UPDATABLE = set(_USER_FIELDS) - {"discord_user_id"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    discord_user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_rate REAL NOT NULL,
    enabled INTEGER NOT NULL,
    peak_rate REAL NOT NULL DEFAULT 0,
    last_alerted_at TEXT,
    snoozed_until TEXT
);
CREATE TABLE IF NOT EXISTS rates (
    ts TEXT NOT NULL,
    provider TEXT NOT NULL,
    rate REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rates_provider_ts ON rates (provider, ts);
CREATE TABLE IF NOT EXISTS wise_fee (
    ts TEXT NOT NULL,
    fixed_sgd REAL NOT NULL,
    pct REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.executescript(_SCHEMA)

    # ---- users -------------------------------------------------------

    def _row_to_user(self, row: tuple) -> User:
        data = dict(zip(_USER_FIELDS, row))
        data["enabled"] = bool(data["enabled"])
        return User(**data)

    def get_user(self, uid: str) -> User | None:
        row = self._conn.execute(
            f"SELECT {', '.join(_USER_FIELDS)} FROM users WHERE discord_user_id = ?",
            (str(uid),),
        ).fetchone()
        return self._row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        rows = self._conn.execute(f"SELECT {', '.join(_USER_FIELDS)} FROM users").fetchall()
        return [self._row_to_user(row) for row in rows]

    def create_user(self, uid: str, name: str, target_rate: float = DEFAULT_TARGET) -> bool:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO users (discord_user_id, name, target_rate, enabled) "
            "VALUES (?, ?, ?, 1)",
            (str(uid), name, target_rate),
        )
        return cursor.rowcount == 1

    def update_user(self, uid: str, **values: object) -> bool:
        unknown = set(values) - _UPDATABLE
        if unknown:
            raise ValueError(f"unknown user fields: {sorted(unknown)}")
        if not values:
            return self.get_user(uid) is not None
        assignments = ", ".join(f"{key} = ?" for key in values)
        params = [int(v) if isinstance(v, bool) else v for v in values.values()]
        cursor = self._conn.execute(
            f"UPDATE users SET {assignments} WHERE discord_user_id = ?",
            (*params, str(uid)),
        )
        return cursor.rowcount == 1

    # ---- rates -------------------------------------------------------

    def record_rate(self, provider: str, rate: float, ts: datetime) -> bool:
        last = self._conn.execute(
            "SELECT rate FROM rates WHERE provider = ? ORDER BY ts DESC, rowid DESC LIMIT 1",
            (provider,),
        ).fetchone()
        if last is not None and last[0] == rate:
            return False
        self._conn.execute(
            "INSERT INTO rates (ts, provider, rate) VALUES (?, ?, ?)",
            (ts.isoformat(), provider, rate),
        )
        return True

    def rates_since(self, provider: str, since: datetime) -> list[tuple[datetime, float]]:
        rows = self._conn.execute(
            "SELECT ts, rate FROM rates WHERE provider = ? AND ts >= ? ORDER BY ts",
            (provider, since.isoformat()),
        ).fetchall()
        return [(datetime.fromisoformat(ts), rate) for ts, rate in rows]

    def prune(self, older_than: datetime) -> int:
        cursor = self._conn.execute("DELETE FROM rates WHERE ts < ?", (older_than.isoformat(),))
        return cursor.rowcount

    # ---- wise fee ----------------------------------------------------

    def save_wise_fee(self, fee: WiseFee, ts: datetime) -> None:
        if self.latest_wise_fee() == fee:
            return
        self._conn.execute(
            "INSERT INTO wise_fee (ts, fixed_sgd, pct) VALUES (?, ?, ?)",
            (ts.isoformat(), fee.fixed_sgd, fee.pct),
        )

    def latest_wise_fee(self) -> WiseFee | None:
        row = self._conn.execute(
            "SELECT fixed_sgd, pct FROM wise_fee ORDER BY ts DESC, rowid DESC LIMIT 1"
        ).fetchone()
        return WiseFee(row[0], row[1]) if row else None

    # ---- meta --------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ---- legacy JSON import -----------------------------------------

    def import_legacy_configs(self, config_dir: str | Path) -> int:
        directory = Path(config_dir)
        if not directory.is_dir():
            return 0
        imported = 0
        for path in sorted(directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.error("legacy config %s unreadable: %s", path.name, exc)
                continue
            uid = str(raw.get("discord_user_id", "")).strip() if isinstance(raw, dict) else ""
            if not uid or self.get_user(uid) is not None:
                continue
            self.create_user(uid, str(raw.get("name") or "User"), float(raw.get("target_rate", DEFAULT_TARGET)))
            self.update_user(
                uid,
                enabled=bool(raw.get("enabled", True)),
                peak_rate=float(raw.get("peak_rate") or 0.0),
                last_alerted_at=raw.get("last_alerted_at"),
            )
            path.rename(path.with_name(path.name + ".migrated"))
            imported += 1
        return imported

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles


# Manage user configs with atomic writes and automatic file watching
class ConfigLoader:
    def __init__(self, config_dir: str | Path = "config", poll_interval_seconds: float = 1.0):
        self.config_dir = Path(config_dir)
        self.poll_interval_seconds = poll_interval_seconds
        self._lock = asyncio.Lock()
        self._users_by_discord_id: Dict[str, Dict[str, Any]] = {}
        self._paths_by_discord_id: Dict[str, Path] = {}
        self._file_state: Dict[Path, float] = {}
        self._watch_task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()

    # Initialize config directory and start file watcher
    async def start(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        await self.reload()
        if self._watch_task is None or self._watch_task.done():
            self._stopping.clear()
            self._watch_task = asyncio.create_task(self._watch_loop(), name="config-watcher")
# Stop file watcher and cancel watch loop task
    
    async def stop(self) -> None:
        self._stopping.set()
        if self._watch_task is None:
            return
        self._watch_task.cancel()
        try:
            await self._watch_task
        except asyncio.CancelledError:
            pass
        self._watch_task = None
# Return list of all loaded user configurations
    
    async def get_all_users(self) -> List[Dict[str, Any]]:
        async with self._lock:
    # Retrieve user config by Discord ID or return None if not found
            return [dict(user) for user in self._users_by_discord_id.values()]

    async def get_user_by_discord_id(self, discord_user_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            user = self._users_by_discord_id.get(str(discord_user_id))
    # Update specific fields in user config and write atomically
            return dict(user) if user is not None else None

    async def update_user_fields(self, discord_user_id: str, fields: Dict[str, Any]) -> bool:
        async with self._lock:
            discord_user_id = str(discord_user_id)
            current = self._users_by_discord_id.get(discord_user_id)
            path = self._paths_by_discord_id.get(discord_user_id)
            if current is None or path is None:
                return False

            updated = dict(current)
            updated.update(fields)
            await self._write_json_atomic(path, updated)
            self._users_by_discord_id[discord_user_id] = updated
    # Create new user config file with defaults, fail if already exists
            self._file_state[path] = self._safe_mtime(path)
            return True

    async def create_user(self, discord_user_id: str, config: Dict[str, Any]) -> bool:
        # Use discord_user_id as filename to guarantee uniqueness
        file_path = self.config_dir / f"user_{discord_user_id}.json"

        if file_path.exists():
            return False

        async with self._lock:
            temp_fd, temp_path = tempfile.mkstemp(
                prefix=f"user_{discord_user_id}.",
                suffix=".tmp",
                dir=str(self.config_dir)
            )
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as tmpf:
                    json.dump(config, tmpf, indent=2)
                    tmpf.write("\n")
                os.replace(temp_path, file_path)
            except Exception:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return False

    # Scan config directory and load all JSON user files
        await self.reload()
        return True

    async def reload(self) -> None:
        users_by_discord_id: Dict[str, Dict[str, Any]] = {}
        paths_by_discord_id: Dict[str, Path] = {}
        file_state: Dict[Path, float] = {}

        for path in sorted(self.config_dir.glob("*.json")):
            if path.name.endswith(".tmp") or path.name.endswith(".lock"):
                continue
            try:
                user = await self._read_user_file(path)
            except Exception as exc:
                print(f"[config] failed to load {path}: {exc}")
                continue

            discord_user_id = str(user.get("discord_user_id", "")).strip()
            if not discord_user_id:
                print(f"[config] skipping {path}: missing discord_user_id")
                continue

            users_by_discord_id[discord_user_id] = user
            paths_by_discord_id[discord_user_id] = path
            file_state[path] = self._safe_mtime(path)

        async with self._lock:
    # Poll config directory for changes and reload when detected
            self._users_by_discord_id = users_by_discord_id
            self._paths_by_discord_id = paths_by_discord_id
            self._file_state = file_state

    async def _watch_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                if await self._has_config_changed():
                    await self.reload()
            except asyncio.CancelledError:
                raise
    # Check if any config file was added, deleted, or modified
            except Exception as exc:
                print(f"[config] watcher error: {exc}")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _has_config_changed(self) -> bool:
        current_state: Dict[Path, float] = {}
        for path in sorted(self.config_dir.glob("*.json")):
    # Parse JSON file into user config dictionary
            current_state[path] = self._safe_mtime(path)

        async with self._lock:
            return current_state != self._file_state

    async def _read_user_file(self, path: Path) -> Dict[str, Any]:
        async with aiofiles.open(path, "r", encoding="utf-8") as handle:
            content = await handle.read()
    # Write JSON config to temp file then atomic rename to target path
        raw = json.loads(content)
        if not isinstance(raw, dict):
            raise ValueError("user config must be a JSON object")
        return raw

    async def _write_json_atomic(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        content = json.dumps(data, indent=2, sort_keys=False) + "\n"

    # Get file modification time safely, returning 0.0 if file doesn't exist
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as handle:
            await handle.write(content)
            await handle.flush()

        os.replace(tmp_path, path)

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return 0.0
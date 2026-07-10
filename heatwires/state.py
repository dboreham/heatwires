"""Run-to-run state persisted to a JSON file (hysteresis timers, failure
counts, manual override)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class State:
    wires_on: bool = False          # last state this program commanded
    last_on_at: str | None = None   # ISO time wires were last turned on
    consecutive_failures: int = 0   # weather fetches failed in a row
    override: str | None = None     # "on" | "off" | None
    override_until: str | None = None  # ISO expiry for the override
    last_run_at: str | None = None
    last_reason: str | None = None

    def minutes_since_on(self, now: datetime) -> float | None:
        if self.last_on_at is None:
            return None
        return (now - datetime.fromisoformat(self.last_on_at)).total_seconds() / 60

    def active_override(self, now: datetime) -> str | None:
        if self.override is None:
            return None
        if self.override_until is not None:
            if now >= datetime.fromisoformat(self.override_until):
                return None
        return self.override


def load(path: Path) -> State:
    try:
        return State(**json.loads(path.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return State()


def save(path: Path, state: State) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2))
    tmp.replace(path)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

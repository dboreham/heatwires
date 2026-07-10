"""Configuration loading."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Device:
    host: str
    alias: str
    child_alias: str | None = None

    @property
    def label(self) -> str:
        return self.child_alias or self.alias


@dataclass
class Thresholds:
    on_temp_max_f: float = 35.0
    on_temp_min_f: float = 8.0
    off_temp_high_f: float = 38.0
    off_temp_low_f: float = 5.0
    snow_lookback_hours: int = 48
    snow_forecast_hours: int = 24
    snow_trigger_inches: float = 0.5
    snow_depth_trigger_inches: float = 1.0
    min_on_minutes: int = 60


@dataclass
class Failsafe:
    max_weather_failures: int = 3
    winter_months: list[int] = field(
        default_factory=lambda: [10, 11, 12, 1, 2, 3, 4]
    )


@dataclass
class Config:
    latitude: float
    longitude: float
    thresholds: Thresholds
    failsafe: Failsafe
    devices: list[Device]
    state_file: Path


def load(path: Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    loc = raw["location"]
    state_file = Path(raw.get("state", {}).get("file", "state.json"))
    if not state_file.is_absolute():
        state_file = path.parent / state_file

    return Config(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        thresholds=Thresholds(**raw.get("thresholds", {})),
        failsafe=Failsafe(**raw.get("failsafe", {})),
        devices=[Device(**d) for d in raw["devices"]],
        state_file=state_file,
    )

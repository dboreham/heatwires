"""Weather retrieval from Open-Meteo (keyless, free for non-commercial use)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from .config import Thresholds

API_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "heatwires/0.1 (roof heat-wire controller)"


@dataclass
class WeatherSignals:
    """Inputs to the icing decision, derived from hourly weather data."""

    temp_f: float
    snowfall_recent_in: float
    snowfall_forecast_in: float
    snow_depth_in: float
    observed_at: str


def fetch(latitude: float, longitude: float, th: Thresholds,
          timeout: float = 30.0) -> WeatherSignals:
    """Fetch weather and reduce it to decision signals. Raises on any failure."""
    params = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m",
        "hourly": "temperature_2m,snowfall,snow_depth",
        "past_days": max(1, -(-th.snow_lookback_hours // 24)),
        "forecast_days": max(1, -(-th.snow_forecast_hours // 24)),
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "timezone": "UTC",
    })
    req = urllib.request.Request(
        f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)

    now = datetime.fromisoformat(data["current"]["time"])
    times = [datetime.fromisoformat(t) for t in data["hourly"]["time"]]
    snowfall = data["hourly"]["snowfall"]
    snow_depth = data["hourly"]["snow_depth"]  # feet, per hourly_units

    lookback = th.snow_lookback_hours
    forecast = th.snow_forecast_hours
    recent = sum(
        s or 0.0
        for t, s in zip(times, snowfall)
        if 0 <= (now - t).total_seconds() / 3600 <= lookback
    )
    ahead = sum(
        s or 0.0
        for t, s in zip(times, snowfall)
        if 0 < (t - now).total_seconds() / 3600 <= forecast
    )
    # Snow depth: latest non-null value at or before now, feet -> inches.
    depth_ft = 0.0
    for t, d in zip(times, snow_depth):
        if t <= now and d is not None:
            depth_ft = d

    return WeatherSignals(
        temp_f=data["current"]["temperature_2m"],
        snowfall_recent_in=recent,
        snowfall_forecast_in=ahead,
        snow_depth_in=depth_ft * 12.0,
        observed_at=data["current"]["time"],
    )

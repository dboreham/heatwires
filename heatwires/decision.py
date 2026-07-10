"""Icing decision logic. Pure functions — no I/O — so it is unit-testable.

Ice dams form from melt-refreeze cycles: snow on the roof, heat loss melting
the underside, meltwater refreezing at the cold eaves. The wires should run
when there is snow AND the temperature is in the melt-refreeze band — not
merely when it is cold.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Failsafe, Thresholds
from .weather import WeatherSignals


@dataclass
class Decision:
    wires_on: bool
    reason: str


def snow_signal(w: WeatherSignals, th: Thresholds) -> bool:
    return (
        w.snowfall_recent_in >= th.snow_trigger_inches
        or w.snowfall_forecast_in >= th.snow_trigger_inches
        or w.snow_depth_in >= th.snow_depth_trigger_inches
    )


def decide(
    w: WeatherSignals,
    th: Thresholds,
    currently_on: bool,
    minutes_since_on: float | None,
) -> Decision:
    """Decide desired wire state.

    minutes_since_on: how long ago the wires were last turned on by this
    program (None if unknown/never). Used for the minimum-on hold, which only
    delays turning OFF — turning ON is never delayed.
    """
    snow = snow_signal(w, th)

    if snow and th.on_temp_min_f <= w.temp_f <= th.on_temp_max_f:
        return Decision(True, (
            f"melt-refreeze conditions: {w.temp_f:.0f}°F with snow "
            f"(recent {w.snowfall_recent_in:.1f}\", "
            f"forecast {w.snowfall_forecast_in:.1f}\", "
            f"depth {w.snow_depth_in:.1f}\")"
        ))

    if currently_on:
        held = (
            minutes_since_on is not None
            and minutes_since_on < th.min_on_minutes
        )
        if held and w.temp_f < th.off_temp_high_f:
            return Decision(True, (
                f"holding on: only {minutes_since_on:.0f} of "
                f"{th.min_on_minutes} minimum minutes elapsed"
            ))

    if not snow:
        return Decision(False, "no snow signal")
    if w.temp_f > th.on_temp_max_f:
        if w.temp_f < th.off_temp_high_f and currently_on:
            return Decision(True, (
                f"hysteresis: {w.temp_f:.0f}°F is above on-threshold "
                f"{th.on_temp_max_f:.0f}°F but below off-threshold "
                f"{th.off_temp_high_f:.0f}°F"
            ))
        return Decision(False, f"warm enough to drain ({w.temp_f:.0f}°F)")
    if w.temp_f < th.on_temp_min_f:
        if w.temp_f > th.off_temp_low_f and currently_on:
            return Decision(True, (
                f"hysteresis: {w.temp_f:.0f}°F is below on-threshold "
                f"{th.on_temp_min_f:.0f}°F but above off-threshold "
                f"{th.off_temp_low_f:.0f}°F"
            ))
        return Decision(False, f"too cold for melt ({w.temp_f:.0f}°F)")

    return Decision(False, "no icing conditions")


def decide_failsafe(
    month: int, consecutive_failures: int, fs: Failsafe, currently_on: bool
) -> Decision:
    """Weather data unavailable. Bias toward ON in winter: a false 'on' costs
    electricity, a false 'off' can cost the roof."""
    if consecutive_failures >= fs.max_weather_failures:
        if month in fs.winter_months:
            return Decision(True, (
                f"FAILSAFE: weather unavailable {consecutive_failures} runs "
                f"in a row during winter — wires on as a precaution"
            ))
        return Decision(False, (
            f"weather unavailable {consecutive_failures} runs, but not "
            f"winter — wires off"
        ))
    return Decision(currently_on, (
        f"weather fetch failed ({consecutive_failures} of "
        f"{fs.max_weather_failures} tolerated) — keeping last state"
    ))

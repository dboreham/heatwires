"""CLI entry point.

    python -m heatwires run [--dry-run]     evaluate weather and set switches
    python -m heatwires status              show weather, decision, and switch states
    python -m heatwires override on|off [--hours N]
    python -m heatwires override clear
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import timedelta
from pathlib import Path

from . import config as config_mod
from . import decision as decision_mod
from . import state as state_mod
from . import weather as weather_mod
from .control import read_state, set_state

log = logging.getLogger("heatwires")


def setup_logging(log_file: Path | None) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    if log_file is not None:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)


def get_decision(cfg, st, now):
    """Fetch weather and decide, handling overrides and fetch failures.
    Returns (decision, weather_or_none)."""
    override = st.active_override(now)
    if override is not None:
        until = st.override_until or "cleared"
        return decision_mod.Decision(
            override == "on", f"manual override {override!r} until {until}"
        ), None

    try:
        w = weather_mod.fetch(cfg.latitude, cfg.longitude, cfg.thresholds)
    except Exception as exc:  # noqa: BLE001 - fail-safe path handles it
        st.consecutive_failures += 1
        log.error("weather fetch failed (%d in a row): %s",
                  st.consecutive_failures, exc)
        return decision_mod.decide_failsafe(
            now.month, st.consecutive_failures, cfg.failsafe, st.wires_on
        ), None

    st.consecutive_failures = 0
    log.info(
        "weather: %.0f°F, snow recent %.1f\" / forecast %.1f\" / depth %.1f\"",
        w.temp_f, w.snowfall_recent_in, w.snowfall_forecast_in, w.snow_depth_in,
    )
    return decision_mod.decide(
        w, cfg.thresholds, st.wires_on, st.minutes_since_on(now)
    ), w


async def cmd_run(cfg, st, dry_run: bool) -> int:
    now = state_mod.utcnow()
    dec, _ = get_decision(cfg, st, now)
    log.info("decision: wires %s — %s", "ON" if dec.wires_on else "OFF",
             dec.reason)

    errors = 0
    if dry_run:
        log.info("dry run: not touching switches")
    else:
        results = await asyncio.gather(
            *(set_state(d, dec.wires_on) for d in cfg.devices)
        )
        errors = sum(1 for r in results if r.error is not None)
        if dec.wires_on and not st.wires_on:
            st.last_on_at = now.isoformat()
        st.wires_on = dec.wires_on
        st.last_run_at = now.isoformat()
        st.last_reason = dec.reason
        state_mod.save(cfg.state_file, st)

    if errors:
        log.error("%d of %d devices failed — check them in the Kasa app",
                  errors, len(cfg.devices))
    return 1 if errors else 0


async def cmd_status(cfg, st) -> int:
    now = state_mod.utcnow()
    dec, w = get_decision(cfg, st, now)
    if w is not None:
        print(f"weather:  {w.temp_f:.0f}°F, snow recent "
              f"{w.snowfall_recent_in:.1f}\" / forecast "
              f"{w.snowfall_forecast_in:.1f}\" / depth {w.snow_depth_in:.1f}\"")
    print(f"decision: wires {'ON' if dec.wires_on else 'OFF'} — {dec.reason}")
    print(f"last run: {st.last_run_at or 'never'}"
          + (f" ({st.last_reason})" if st.last_reason else ""))
    results = await asyncio.gather(*(read_state(d) for d in cfg.devices))
    for r in results:
        actual = ("ERROR: " + r.error if r.error
                  else "ON" if r.is_on else "OFF")
        print(f"  {r.device.label:<28} {actual}")
    return 1 if any(r.error for r in results) else 0


def cmd_override(cfg, st, mode: str, hours: float | None) -> int:
    now = state_mod.utcnow()
    if mode == "clear":
        st.override = None
        st.override_until = None
        print("override cleared; automatic control resumes on next run")
    else:
        st.override = mode
        st.override_until = (
            (now + timedelta(hours=hours)).isoformat() if hours else None
        )
        until = st.override_until or "manually cleared"
        print(f"override: wires {mode.upper()} until {until}")
        print("(takes effect on the next scheduled run, or run "
              "`python -m heatwires run` now)")
    state_mod.save(cfg.state_file, st)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="heatwires", description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).parent.parent / "config.toml")
    parser.add_argument("--log-file", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="evaluate weather and set switches")
    p_run.add_argument("--dry-run", action="store_true",
                       help="decide and log, but do not touch switches")

    sub.add_parser("status", help="show weather, decision, switch states")

    p_ov = sub.add_parser("override", help="force wires on/off")
    p_ov.add_argument("mode", choices=["on", "off", "clear"])
    p_ov.add_argument("--hours", type=float, default=None,
                      help="auto-expire the override after this many hours")

    args = parser.parse_args()
    setup_logging(args.log_file)

    cfg = config_mod.load(args.config)
    st = state_mod.load(cfg.state_file)

    if args.command == "run":
        return asyncio.run(cmd_run(cfg, st, args.dry_run))
    if args.command == "status":
        return asyncio.run(cmd_status(cfg, st))
    return cmd_override(cfg, st, args.mode, args.hours)


if __name__ == "__main__":
    sys.exit(main())

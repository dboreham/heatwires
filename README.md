# heatwires

Automated control of roof heat wires based on weather conditions, to prevent
ice dams. Talks directly to TP-Link Kasa switches (KP400, HS200, etc.) over
the local network using [python-kasa](https://github.com/python-kasa/python-kasa)
— no cloud dependency — and gets weather from the free, keyless
[Open-Meteo](https://open-meteo.com) API.

## How it decides

Ice dams form from melt-refreeze cycles, so the wires run when there is snow
AND the temperature is in the melt-refreeze band — not merely when it is cold:

- **ON** when temperature is 8–35°F and there is a snow signal (≥0.5" fallen
  in the last 48h, ≥0.5" forecast in the next 24h, or ≥1" standing snow depth).
- **OFF** when it warms past 38°F (meltwater drains freely), drops below 5°F
  (nothing melts), or the snow signal clears.
- The on/off threshold gaps provide temperature hysteresis, and a 60-minute
  minimum-on hold prevents rapid cycling. Turning ON is never delayed.
- **Fail-safe:** if weather data is unavailable 3 runs in a row during winter
  months, the wires turn ON — a false "on" costs electricity; a false "off"
  can cost the roof.

All thresholds are in `config.toml`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Edit `config.toml`:

- Set `latitude`/`longitude` to the building's actual location.
- List the switches under `[[devices]]`. The `alias` (and `child_alias` for
  multi-outlet devices like the KP400) is verified against the live device
  before every actuation — if DHCP hands the IP to something else, the run
  refuses to touch it rather than toggling the wrong equipment. **Give the
  switches static DHCP reservations in your router** so this never trips.

## Usage

```bash
.venv/bin/python -m heatwires status           # weather, decision, switch states (read-only)
.venv/bin/python -m heatwires run --dry-run    # decide and log, don't touch switches
.venv/bin/python -m heatwires run              # the real thing — run this on a schedule
.venv/bin/python -m heatwires override on --hours 12   # force on (e.g. ahead of a storm)
.venv/bin/python -m heatwires override off --hours 4   # force off (e.g. roof work)
.venv/bin/python -m heatwires override clear
```

Manual changes made in the Kasa app are overwritten on the next scheduled
run — use `override` instead when you want the program to stand down.

## Scheduling

Run every 15 minutes via cron on any always-on machine on the same LAN as the
switches (Raspberry Pi, NAS, home server):

```cron
*/15 * * * * cd /home/david/projects/play/heatwires && .venv/bin/python -m heatwires --log-file heatwires.log run
```

Note for WSL2: WSL does not reliably run cron while no session is open. Fine
for development, but deploy to an always-on Linux box for the winter. (Local
control requires being on the same LAN; WSL2's NAT blocks broadcast discovery
but unicast connections to known switch IPs work.)

Exit code is non-zero if any switch could not be reached or verified, so you
can wrap the cron line with your favorite alerting if wanted.

## Testing

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The decision logic is pure (no I/O) and covered by unit tests in
`tests/test_decision.py`.

## Firmware caveat

TP-Link has been migrating newer firmware toward an authenticated local
protocol (KLAP) and in some cases disabling local control. These switches
currently speak the legacy local protocol. **Avoid accepting Kasa firmware
updates** once this is working, and re-run `python -m heatwires status` after
any update to confirm the switches still respond.

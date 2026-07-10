"""Kasa switch actuation over the local network."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kasa import Device as KasaDevice
from kasa import Discover

from .config import Device

log = logging.getLogger("heatwires")


@dataclass
class DeviceState:
    device: Device
    is_on: bool | None  # None = unreachable or alias mismatch
    error: str | None = None


def _resolve_target(dev: KasaDevice, cfg: Device):
    """Return the switchable module (device or child outlet), verifying
    aliases so a moved IP address never toggles the wrong equipment."""
    if dev.alias != cfg.alias:
        raise ValueError(
            f"alias mismatch at {cfg.host}: expected {cfg.alias!r}, "
            f"found {dev.alias!r} — refusing to touch it"
        )
    if cfg.child_alias is None:
        return dev
    for child in dev.children:
        if child.alias == cfg.child_alias:
            return child
    raise ValueError(
        f"no child outlet named {cfg.child_alias!r} on {cfg.host} "
        f"(has: {[c.alias for c in dev.children]})"
    )


async def read_state(cfg: Device, timeout: int = 10) -> DeviceState:
    try:
        dev = await Discover.discover_single(
            cfg.host, timeout=timeout, discovery_timeout=timeout
        )
        try:
            await dev.update()
            target = _resolve_target(dev, cfg)
            return DeviceState(cfg, target.is_on)
        finally:
            await dev.disconnect()
    except Exception as exc:  # noqa: BLE001 - report, don't crash the run
        return DeviceState(cfg, None, error=str(exc))


async def set_state(cfg: Device, on: bool, timeout: int = 10) -> DeviceState:
    """Set one device/outlet, returning its confirmed state afterwards."""
    try:
        dev = await Discover.discover_single(
            cfg.host, timeout=timeout, discovery_timeout=timeout
        )
        try:
            await dev.update()
            target = _resolve_target(dev, cfg)
            if target.is_on != on:
                if on:
                    await target.turn_on()
                else:
                    await target.turn_off()
                await dev.update()
                target = _resolve_target(dev, cfg)
                if target.is_on != on:
                    raise RuntimeError(
                        f"commanded {'on' if on else 'off'} but device "
                        f"still reports {'on' if target.is_on else 'off'}"
                    )
                log.info("%s: turned %s", cfg.label, "ON" if on else "OFF")
            else:
                log.debug("%s: already %s", cfg.label, "ON" if on else "OFF")
            return DeviceState(cfg, target.is_on)
        finally:
            await dev.disconnect()
    except Exception as exc:  # noqa: BLE001
        log.error("%s: FAILED to set %s: %s", cfg.label,
                  "ON" if on else "OFF", exc)
        return DeviceState(cfg, None, error=str(exc))

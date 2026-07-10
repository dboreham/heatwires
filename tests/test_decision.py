from heatwires.config import Failsafe, Thresholds
from heatwires.decision import decide, decide_failsafe
from heatwires.weather import WeatherSignals

TH = Thresholds()
FS = Failsafe()


def w(temp, recent=0.0, forecast=0.0, depth=0.0):
    return WeatherSignals(
        temp_f=temp,
        snowfall_recent_in=recent,
        snowfall_forecast_in=forecast,
        snow_depth_in=depth,
        observed_at="2026-01-15T12:00",
    )


def test_on_in_melt_refreeze_band_with_recent_snow():
    assert decide(w(28, recent=2.0), TH, False, None).wires_on


def test_on_with_forecast_snow_only():
    assert decide(w(30, forecast=1.0), TH, False, None).wires_on


def test_on_with_standing_snow_depth():
    assert decide(w(25, depth=4.0), TH, False, None).wires_on


def test_off_when_no_snow_even_if_cold():
    assert not decide(w(20), TH, False, None).wires_on


def test_off_when_warm_despite_snow():
    assert not decide(w(45, recent=3.0), TH, True, 999).wires_on


def test_off_when_extremely_cold():
    assert not decide(w(-10, depth=6.0), TH, True, 999).wires_on


def test_temperature_hysteresis_stays_on_between_thresholds():
    # 36°F: above on-max (35) but below off-high (38)
    d = decide(w(36, depth=4.0), TH, True, 999)
    assert d.wires_on
    # ...but does not turn ON at 36°F from an off state
    assert not decide(w(36, depth=4.0), TH, False, None).wires_on


def test_low_temperature_hysteresis():
    # 6°F: below on-min (8) but above off-low (5) — stays on, won't start
    assert decide(w(6, depth=4.0), TH, True, 999).wires_on
    assert not decide(w(6, depth=4.0), TH, False, None).wires_on


def test_minimum_on_hold_delays_turn_off():
    # Snow stopped mattering, but wires only just came on
    d = decide(w(30), TH, True, 15)
    assert d.wires_on
    assert "holding" in d.reason


def test_minimum_on_hold_expires():
    assert not decide(w(30), TH, True, 90).wires_on


def test_hold_does_not_delay_turn_on():
    assert decide(w(28, recent=2.0), TH, False, None).wires_on


def test_hold_does_not_block_warm_shutoff():
    # Above off_temp_high the hold must not keep wires burning
    assert not decide(w(45), TH, True, 5).wires_on


def test_failsafe_on_in_winter_after_repeated_failures():
    d = decide_failsafe(1, 3, FS, currently_on=False)
    assert d.wires_on
    assert "FAILSAFE" in d.reason


def test_failsafe_off_in_summer():
    assert not decide_failsafe(7, 5, FS, currently_on=True).wires_on


def test_failsafe_keeps_last_state_below_threshold():
    assert decide_failsafe(1, 1, FS, currently_on=True).wires_on
    assert not decide_failsafe(1, 1, FS, currently_on=False).wires_on

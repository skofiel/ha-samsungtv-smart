"""Five sensors that can only ever read 0 should not be created at all.

SmartThings' powerConsumptionReport dict carries a start/end window for the
period it covers. A set that has never metered anything publishes the whole
structure zeroed with `start` at the Unix epoch — the field's "never
initialised" value — and never updates it again.

Measured on a 55" Frame (LS03D): every field 0, start 1970-01-01T00:00:00Z, and
the attribute's own timestamp a day old while the TV was otherwise talking to
SmartThings normally. The previous check only asked whether the capability key
was present, so those TVs got five sensors that read "unknown" until a restart
and 0 after it — and `energy`, carrying SensorDeviceClass.ENERGY and
TOTAL_INCREASING, would join the Energy dashboard as a meter reading nothing.
"""

from unittest.mock import MagicMock

from custom_components.samsungtv_smart.sensor import _power_report_is_metered

# Verbatim from the diagnostics of a 55" Frame that does not meter.
UNMETERED = {
    "energy": 0,
    "deltaEnergy": 0,
    "power": 0,
    "powerEnergy": 0,
    "persistedEnergy": 0,
    "energySaved": 0,
    "persistedSavedEnergy": 0,
    "start": "1970-01-01T00:00:00Z",
    "end": "2026-09-17T15:00:12Z",
}

METERED = {
    "energy": 41234,
    "deltaEnergy": 12,
    "power": 95,
    "powerEnergy": 34,
    "energySaved": 5,
    "start": "2026-09-18T14:00:00Z",
    "end": "2026-09-18T15:00:00Z",
}


def _status(value):
    report = MagicMock()
    report.value = value
    return {"main": {"powerConsumptionReport": {"powerConsumption": report}}}


def test_a_tv_that_meters_gets_its_sensors():
    assert _power_report_is_metered(_status(METERED)) is True


def test_an_epoch_start_means_the_counter_never_ran():
    assert _power_report_is_metered(_status(UNMETERED)) is False


def test_a_freshly_reset_but_running_meter_still_counts():
    """Zeroes alone are not the signal — a real window is."""
    fresh = dict(UNMETERED, start="2026-09-18T15:00:00Z")

    assert _power_report_is_metered(_status(fresh)) is True


def test_a_missing_start_is_not_a_meter():
    assert _power_report_is_metered(_status({"energy": 0, "power": 0})) is False


def test_an_empty_payload_is_not_a_meter():
    assert _power_report_is_metered(_status({})) is False


def test_a_null_payload_is_not_a_meter():
    assert _power_report_is_metered(_status(None)) is False


def test_an_absent_capability_is_not_a_meter():
    assert _power_report_is_metered({"main": {}}) is False
    assert _power_report_is_metered({}) is False

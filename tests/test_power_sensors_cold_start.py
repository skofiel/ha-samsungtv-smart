"""The power/energy sensors must get a first reading even with the TV off.

The coordinator skips its SmartThings poll while the TV is truly off, because
the local WebSocket is the primary power source and there is nothing worth a
cloud call during standby. That is right once there is something to keep — but
it also skipped the *first* refresh, leaving `self.data` empty with nothing to
refill it until the TV was switched on. All five sensors then read "unknown"
indefinitely: a restart with the TV off, or a set that spends most of its life
off, never got a first reading at all.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.samsungtv_smart.sensor import SmartThingsPowerCoordinator

PAYLOAD = {
    "power": 95,
    "energy": 41234,
    "deltaEnergy": 12,
    "powerEnergy": 34,
    "energySaved": 5,
}


def _coordinator(hass=None):
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.title = "The Frame"
    entry.options = {}
    entry.data = {}
    with patch(
        "custom_components.samsungtv_smart.sensor.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = SmartThingsPowerCoordinator.__new__(SmartThingsPowerCoordinator)
    coordinator.hass = hass or MagicMock()
    coordinator._entry = entry
    coordinator._session = MagicMock()
    coordinator.device_id = "dev-1"
    coordinator._device_name = "The Frame"
    coordinator._st_last_poll = 0.0
    coordinator._warned_empty = False
    coordinator.data = None
    coordinator.logger = MagicMock()
    return coordinator


def _client_returning(payload):
    report = MagicMock()
    report.value = payload
    client = AsyncMock()
    client.get_device_status.return_value = {
        "main": {"powerConsumptionReport": {"powerConsumption": report}}
    }
    return client


async def test_the_first_refresh_polls_even_though_the_tv_is_off():
    """The regression: this used to return {} and never be retried."""
    coordinator = _coordinator()
    client = _client_returning(PAYLOAD)
    coordinator._get_st_client = AsyncMock(return_value=client)

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=True
    ):
        data = await coordinator._async_update_data()

    client.get_device_status.assert_awaited_once()
    assert data["energy"] == PAYLOAD["energy"]


async def test_a_first_reading_taken_in_standby_reports_no_instantaneous_draw():
    """The counters are real; the wattage the cloud last saw is not."""
    coordinator = _coordinator()
    coordinator._get_st_client = AsyncMock(return_value=_client_returning(PAYLOAD))

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=True
    ):
        data = await coordinator._async_update_data()

    assert data["power"] == 0
    assert data["energySaved"] == PAYLOAD["energySaved"]


async def test_later_refreshes_with_the_tv_off_skip_the_cloud_call():
    """Once there is something to keep, standby costs no SmartThings quota."""
    coordinator = _coordinator()
    coordinator.data = dict(PAYLOAD)
    client = _client_returning(PAYLOAD)
    coordinator._get_st_client = AsyncMock(return_value=client)

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=True
    ):
        data = await coordinator._async_update_data()

    client.get_device_status.assert_not_awaited()
    assert data["power"] == 0
    assert data["energy"] == PAYLOAD["energy"]


async def test_a_running_tv_is_polled_normally():
    coordinator = _coordinator()
    client = _client_returning(PAYLOAD)
    coordinator._get_st_client = AsyncMock(return_value=client)

    with (
        patch(
            "custom_components.samsungtv_smart.sensor._tv_powered_off",
            return_value=False,
        ),
        patch(
            "custom_components.samsungtv_smart.sensor._tv_in_art_mode",
            return_value=False,
        ),
    ):
        data = await coordinator._async_update_data()

    client.get_device_status.assert_awaited_once()
    assert data["power"] == PAYLOAD["power"]


@pytest.mark.parametrize("failure", [Exception("cloud hiccup")])
async def test_a_failed_first_fetch_leaves_room_for_a_retry(failure):
    """Returning {} is fine here: the next cycle tries again."""
    coordinator = _coordinator()
    client = AsyncMock()
    client.get_device_status.side_effect = failure
    coordinator._get_st_client = AsyncMock(return_value=client)

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=True
    ):
        data = await coordinator._async_update_data()

    assert data == {}


async def test_an_advertised_but_empty_capability_is_reported_once():
    """Five sensors reading "unknown" for ever must not look like our fault.

    The sensors only exist because powerConsumptionReport was present at setup,
    so a permanently empty payload means the TV advertises the capability and
    publishes nothing under it. Not every Samsung model populates it.
    """
    coordinator = _coordinator()
    coordinator._get_st_client = AsyncMock(return_value=_client_returning(None))

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=False
    ), patch(
        "custom_components.samsungtv_smart.sensor._tv_in_art_mode", return_value=False
    ):
        assert await coordinator._async_update_data() == {}
        assert await coordinator._async_update_data() == {}

    assert coordinator.logger.warning.call_count == 1
    message = str(coordinator.logger.warning.call_args)
    assert "powerConsumptionReport" in message


async def test_an_empty_dict_counts_as_no_data():
    coordinator = _coordinator()
    coordinator._get_st_client = AsyncMock(return_value=_client_returning({}))

    with patch(
        "custom_components.samsungtv_smart.sensor._tv_powered_off", return_value=False
    ), patch(
        "custom_components.samsungtv_smart.sensor._tv_in_art_mode", return_value=False
    ):
        assert await coordinator._async_update_data() == {}

    assert coordinator.logger.warning.call_count == 1

"""Behavioural pins for how the entity decides it is on or off.

Two things are pinned here that automations depend on and that nothing covered:

* ``state`` deliberately lies for POWER_OFF_DELAY seconds after a power-off
  command, so the UI reacts before the TV has dropped off the network. Anyone
  polling the entity straight after calling turn_off is reading that lie, and
  it is worth having it stated in a test rather than discovered.
* ``_check_status`` has a branch that gates the result on
  ``self._ws.artmode_status``. It cannot fire in any install running the async
  Art API, because ``disable_art_thread()`` pins that attribute at
  ``Unsupported``. The test below states that plainly, so the next person to
  read the branch does not assume it does something.
"""

from unittest.mock import AsyncMock, MagicMock

from custom_components.samsungtv_smart.const import CONF_EXT_POWER_ENTITY
from homeassistant.const import STATE_OFF
from tests.helpers import ArtModeStatus, MediaPlayerState, STStatus, make_device

# --------------------------------------------------------------------------
# The optimistic power-off window
# --------------------------------------------------------------------------


def test_state_reports_off_while_a_power_off_is_in_flight():
    """POWER_OFF_DELAY seconds of deliberate optimism, for UI responsiveness."""
    device = make_device(state=MediaPlayerState.ON)
    device._power_off_in_progress = MagicMock(return_value=True)

    assert device.state == MediaPlayerState.OFF


def test_state_reports_the_real_value_once_the_window_closes():
    device = make_device(state=MediaPlayerState.ON)
    device._power_off_in_progress = MagicMock(return_value=False)

    assert device.state == MediaPlayerState.ON


# --------------------------------------------------------------------------
# The REST PowerState probe, when device_info carries one
# --------------------------------------------------------------------------


async def test_power_state_on_means_the_tv_is_on():
    device = make_device(power_state="on")
    device._async_load_device_info = AsyncMock(
        return_value={"device": {"PowerState": "on"}}
    )

    assert await device._check_status() is True


async def test_power_state_standby_means_the_tv_is_off():
    """A Frame in Art Mode reports 'on' here — standby is genuinely off."""
    device = make_device(power_state="on")
    device._async_load_device_info = AsyncMock(
        return_value={"device": {"PowerState": "standby"}}
    )

    assert await device._check_status() is False


async def test_an_unreachable_probe_means_the_tv_is_off():
    device = make_device(power_state="on")
    device._async_load_device_info = AsyncMock(return_value=None)

    assert await device._check_status() is False


async def test_a_tv_believed_off_gets_the_short_probe_timeout():
    """Otherwise the probe's own timeout overruns the scan interval.

    13 TVs produced 557 "update took longer than the scan interval" warnings in
    84 minutes, 96% of them from the two that were simply asleep.
    """
    device = make_device(state=MediaPlayerState.OFF, power_state="on")
    device._async_load_device_info = AsyncMock(return_value=None)

    await device._check_status()

    _, kwargs = device._async_load_device_info.call_args
    assert kwargs["timeout"] is not None


async def test_a_tv_believed_on_keeps_the_full_probe_timeout():
    device = make_device(state=MediaPlayerState.ON, power_state="on")
    device._async_load_device_info = AsyncMock(
        return_value={"device": {"PowerState": "on"}}
    )

    await device._check_status()

    _, kwargs = device._async_load_device_info.call_args
    assert kwargs["timeout"] is None


# --------------------------------------------------------------------------
# The WebSocket fallback, for TVs whose device_info has no PowerState
# --------------------------------------------------------------------------


async def test_without_power_state_the_websocket_connection_decides():
    device = make_device(power_state=None, frame_tv_support=False)
    device._ws.is_connected = True

    assert await device._check_status() is True


async def test_a_disconnected_websocket_means_off():
    device = make_device(power_state=None, frame_tv_support=False)
    device._ws.is_connected = False

    assert await device._check_status() is False


async def test_a_fresh_smartthings_power_off_overrides_a_live_socket():
    """The cloud saw the set go off before the socket noticed."""
    device = make_device(
        state=MediaPlayerState.ON,
        power_state=None,
        frame_tv_support=False,
        st_state=STStatus.STATE_OFF,
    )
    device._ws.is_connected = True
    device._st.prev_state = STStatus.STATE_ON
    device._use_st_status = True

    assert await device._check_status() is False


async def test_an_external_power_entity_can_veto_a_live_socket():
    """A smart plug reporting no draw means the set is off, socket or not."""
    device = make_device(
        power_state=None,
        frame_tv_support=False,
        options={CONF_EXT_POWER_ENTITY: "binary_sensor.tv_power"},
    )
    device._ws.is_connected = True
    device.hass.states.is_state = MagicMock(return_value=True)  # it *is* off

    assert await device._check_status() is False
    device.hass.states.is_state.assert_called_once_with(
        "binary_sensor.tv_power", STATE_OFF
    )


async def test_the_legacy_artmode_gate_is_inert_in_a_normal_install():
    """_check_status forces "off" when the legacy art thread reports Art Mode.

    That thread is stopped by disable_art_thread() as soon as the async Art API
    is active, which is every normal install, so artmode_status stays
    ``Unsupported`` and this gate never fires. Pinned as dead on purpose: the
    identical assumption in _turn_off is what left Frames sitting in Art Mode.
    """
    device = make_device(
        power_state=None,
        frame_tv_support=False,
        ws_artmode=ArtModeStatus.Unsupported,
        panel_art=True,  # the panel really is showing art
    )
    device._ws.is_connected = True

    # Art is on screen, yet the gate does not fire: the entity still reads "on".
    assert await device._check_status() is True


async def test_the_legacy_artmode_gate_still_works_where_the_thread_runs():
    device = make_device(
        power_state=None,
        frame_tv_support=False,
        ws_artmode=ArtModeStatus.On,
    )
    device._ws.is_connected = True

    assert await device._check_status() is False

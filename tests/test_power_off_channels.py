"""The power-off chain must reach a channel that can actually power a Frame off.

Two faults combined to leave a Frame TV on (usually sitting in Art Mode) when an
automation called ``media_player.turn_off``:

* ``async_turn_off`` only knew two channels — SmartThings, then the WebSocket
  power key. IP Control, the one local channel whose ``powerControl powerOff``
  works from Art Mode, was wired into the Power *switch* but not into the media
  player, so a lapsed cloud token dropped straight through to a WebSocket
  KEY_POWER that, on a Frame, only toggles viewing <-> Art Mode.
* ``_turn_off`` decided whether the set was in Art Mode from
  ``self._ws.artmode_status``. That attribute is only maintained by the legacy
  SamsungArt WebSocket thread, which ``disable_art_thread()`` stops as soon as
  the async Art API is active — the normal case — leaving it pinned at
  ``Unsupported`` forever. The Art Mode branch therefore never fired and a TV
  sitting in Art Mode was sent no command at all.

These are behavioural tests: they drive ``async_turn_off`` and assert which
channel was used, so a future refactor that reintroduces either fault fails here
rather than on someone's TV.
"""

from unittest.mock import AsyncMock, MagicMock

from custom_components.samsungtv_smart.api.ipcontrol import (
    SamsungIPControlAuthError,
    SamsungIPControlError,
)
from custom_components.samsungtv_smart.api.samsungws import ArtModeStatus
from custom_components.samsungtv_smart.media_player import (
    ArtModeSupport,
    SamsungTVDevice,
)
from homeassistant.components.media_player import MediaPlayerState

ENTRY_ID = "entry-1"


def _device(*, ip_client=None, smartthings=None, frame=True, is_frame_persisted=False):
    """Build the minimum SamsungTVDevice these unit tests drive."""
    device = object.__new__(SamsungTVDevice)

    device._state = MediaPlayerState.ON
    device._entry_id = ENTRY_ID
    device._end_of_power_off = None
    device._log = MagicMock()
    device.entity_id = "media_player.frame"

    # The legacy art thread is disabled whenever art.py is active, which pins
    # this at Unsupported. Reproduce that here: it is the real-world default.
    device._ws = MagicMock()
    device._ws.artmode_status = ArtModeStatus.Unsupported

    # FrameTVSupport comes from a live REST probe, so it is absent for a TV that
    # is off or unreachable; is_frame_persisted covers that case instead.
    device._device_info = (
        {"device": {"FrameTVSupport": "true" if frame else "false"}} if frame else None
    )

    entry = MagicMock()
    entry.data = {"is_frame_tv": is_frame_persisted}
    device.hass = MagicMock()
    device.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    async def _executor_job(func, *args):
        return func(*args)

    device.hass.async_add_executor_job = _executor_job

    device._st = smartthings
    device._get_ip_control_client = MagicMock(return_value=ip_client)
    device._async_switch_entity = AsyncMock()
    device._art_mode_is_on = MagicMock(return_value=False)
    device.send_command = MagicMock()
    device._power_off_in_progress = MagicMock(return_value=False)

    return device


# --------------------------------------------------------------------------
# Channel selection
# --------------------------------------------------------------------------


async def test_ip_control_is_preferred_over_smartthings_and_the_power_key():
    """A paired local channel wins: no cloud call, no WebSocket key."""
    ip_client = AsyncMock()
    smartthings = AsyncMock()
    device = _device(ip_client=ip_client, smartthings=smartthings)

    await device.async_turn_off()

    ip_client.async_power_off.assert_awaited_once_with()
    smartthings.async_turn_off.assert_not_awaited()
    device.send_command.assert_not_called()
    device._async_switch_entity.assert_awaited_once_with(False)


async def test_a_failed_ip_control_falls_through_to_smartthings():
    """A transport error on the local channel must not end the attempt."""
    ip_client = AsyncMock()
    ip_client.async_power_off.side_effect = SamsungIPControlError("timeout")
    smartthings = AsyncMock()
    device = _device(ip_client=ip_client, smartthings=smartthings)

    await device.async_turn_off()

    smartthings.async_turn_off.assert_awaited_once_with()
    device.send_command.assert_not_called()


async def test_a_rejected_ip_control_token_falls_through_and_warns():
    """A stale token is actionable, so it must not be logged at debug."""
    ip_client = AsyncMock()
    ip_client.async_power_off.side_effect = SamsungIPControlAuthError("401")
    smartthings = AsyncMock()
    device = _device(ip_client=ip_client, smartthings=smartthings)

    await device.async_turn_off()

    smartthings.async_turn_off.assert_awaited_once_with()
    assert device._log.warning.called


async def test_smartthings_is_used_when_ip_control_is_unpaired():
    """Installs without IP Control keep their existing cloud path."""
    smartthings = AsyncMock()
    device = _device(ip_client=None, smartthings=smartthings)

    await device.async_turn_off()

    smartthings.async_turn_off.assert_awaited_once_with()
    device.send_command.assert_not_called()


async def test_a_failed_smartthings_warns_instead_of_failing_silently():
    """The old code logged this at debug, so a lapsed token looked like a no-op."""
    smartthings = AsyncMock()
    smartthings.async_turn_off.side_effect = RuntimeError("token expired")
    device = _device(ip_client=None, smartthings=smartthings)

    await device.async_turn_off()

    assert device._log.warning.called
    warnings = " ".join(str(call) for call in device._log.warning.call_args_list)
    assert "token expired" in warnings
    # And it still tries the last-resort key rather than giving up.
    device.send_command.assert_called_once_with("KEY_POWER,3000")


async def test_a_frame_with_no_reliable_channel_says_so():
    """Reaching the power key on a Frame cannot power it off — warn, don't be silent."""
    device = _device(ip_client=None, smartthings=None)

    await device.async_turn_off()

    warnings = " ".join(str(call) for call in device._log.warning.call_args_list)
    assert "IP Control" in warnings


# --------------------------------------------------------------------------
# _turn_off: the Art Mode branch that never fired
# --------------------------------------------------------------------------


async def test_a_tv_in_art_mode_is_sent_the_power_key_hold():
    """The regression: state is not ON, art mode is on, so a hold must be sent."""
    device = _device(ip_client=None, smartthings=None)
    device._state = MediaPlayerState.OFF

    assert device._turn_off(art_mode_on=True) is True
    device.send_command.assert_called_once_with("KEY_POWER,3000")


async def test_a_tv_that_is_off_and_not_in_art_mode_sends_nothing():
    """Nothing to do for a set that is genuinely off — and say so to the caller."""
    device = _device(ip_client=None, smartthings=None)
    device._state = MediaPlayerState.OFF

    assert device._turn_off(art_mode_on=False) is False
    device.send_command.assert_not_called()


async def test_turn_off_no_longer_consults_the_pinned_ws_artmode_status():
    """_ws.artmode_status is Unsupported for the life of the entity; ignore it."""
    device = _device(ip_client=None, smartthings=None)
    device._state = MediaPlayerState.OFF
    device._ws.artmode_status = ArtModeStatus.Unsupported

    # The caller resolved the real art state; _turn_off must trust that.
    assert device._turn_off(art_mode_on=True) is True
    device.send_command.assert_called_once_with("KEY_POWER,3000")


async def test_a_non_frame_gets_a_short_press():
    """Only Frames need the hold; a normal set powers off on a plain KEY_POWER."""
    device = _device(ip_client=None, smartthings=None, frame=False)
    device._state = MediaPlayerState.ON

    assert device._turn_off(art_mode_on=None) is True
    device.send_command.assert_called_once_with("KEY_POWER")


# --------------------------------------------------------------------------
# support_art_mode must survive an unreachable TV
# --------------------------------------------------------------------------


def test_frame_support_survives_a_missing_device_info():
    """An off/asleep Frame has no FrameTVSupport, but is still a Frame.

    Without the persisted flag this returned UNSUPPORTED, and async_turn_off
    then skipped its SmartThings tier entirely for exactly the TV that needed it.
    """
    device = _device(frame=False, is_frame_persisted=True)

    assert device.support_art_mode == ArtModeSupport.PARTIAL


def test_a_genuine_non_frame_stays_unsupported():
    """The persisted flag is only ever set after a TV confirmed Frame support."""
    device = _device(frame=False, is_frame_persisted=False)

    assert device.support_art_mode == ArtModeSupport.UNSUPPORTED


def test_smartthings_is_skipped_for_a_confirmed_non_frame():
    """A non-Frame has no Art Mode to get stuck in; the plain key is correct."""
    device = _device(frame=False, is_frame_persisted=False)

    assert device.support_art_mode == ArtModeSupport.UNSUPPORTED

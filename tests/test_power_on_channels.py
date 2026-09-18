"""Behavioural pins for _async_power_on(), which currently works.

Power-on is the one path a user confirmed working on real hardware, so it is
pinned here *before* anything else in this file's neighbourhood is refactored.
Two of its branches are dead in any normal install — they test
``self._ws.artmode_status``, which ``disable_art_thread()`` leaves at
``Unsupported`` for the life of the entity once the async Art API is active —
but dead is not the same as wrong, and an install still running the legacy
SamsungArt thread reaches them. They are pinned as they stand so that reviving
them later is a deliberate, visible change rather than a side effect.

The previous test for this path (test_power_on_auth_blocked_fallback.py)
asserts on the source text of media_player.py: it checks that the string
``"if not self._ws.auth_blocked:"`` appears before another string. That passes
whether or not the code works. These drive the method.
"""

from unittest.mock import AsyncMock, MagicMock

from custom_components.samsungtv_smart.api.ipcontrol import SamsungIPControlError
from custom_components.samsungtv_smart.const import CONF_POWER_ON_METHOD, PowerOnMethod
from tests.helpers import ArtModeStatus, MediaPlayerState, STStatus, make_device

# --------------------------------------------------------------------------
# The legacy art-thread branches
# --------------------------------------------------------------------------


async def test_art_mode_from_a_running_tv_sends_the_power_key():
    """Only reachable while the legacy SamsungArt thread maintains the status."""
    device = make_device(ws_artmode=ArtModeStatus.Off)

    assert await device._async_power_on(set_art_mode=True) is True
    device.async_send_command.assert_awaited_once_with("KEY_POWER")
    assert device._state == MediaPlayerState.OFF


async def test_powering_on_out_of_art_mode_sends_the_power_key():
    device = make_device(ws_artmode=ArtModeStatus.On)

    assert await device._async_power_on() is True
    device.async_send_command.assert_awaited_once_with("KEY_POWER")


async def test_asking_for_art_mode_while_already_in_art_mode_is_a_no_op():
    device = make_device(ws_artmode=ArtModeStatus.On)

    assert await device._async_power_on(set_art_mode=True) is False
    device.async_send_command.assert_not_awaited()


# --------------------------------------------------------------------------
# The live path: a TV believed to be off
# --------------------------------------------------------------------------


async def test_a_tv_believed_on_is_left_alone():
    device = make_device(state=MediaPlayerState.ON)

    assert await device._async_power_on() is False
    device.async_send_command.assert_not_awaited()


async def test_a_successful_power_key_skips_the_wake_method():
    device = make_device(state=MediaPlayerState.OFF)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True

    device.async_send_command.assert_awaited_once_with("KEY_POWER")
    device._send_wol_packet.assert_not_called()
    device._ws.set_power_on_request.assert_called_once_with(False)


async def test_an_auth_blocked_channel_skips_the_futile_key_and_wakes_instead():
    """KEY_POWER reports "sent" even when the TV answers ms.channel.unauthorized.

    On some 2020 Frames the remote channel can never authorize, so the key was
    reported as sent, the wake method was never reached, and the set stayed off
    ("TV is not reachable" every automation cycle).
    """
    device = make_device(state=MediaPlayerState.OFF)
    device._ws.auth_blocked = True
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True

    device.async_send_command.assert_not_awaited()
    device._send_wol_packet.assert_called_once()


async def test_a_power_key_that_reports_not_sent_falls_through_to_the_wake_method():
    device = make_device(state=MediaPlayerState.OFF)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True
    device._send_wol_packet.assert_called_once()


# --------------------------------------------------------------------------
# Wake methods
# --------------------------------------------------------------------------


async def test_the_smartthings_wake_method_is_used_when_configured():
    device = make_device(
        state=MediaPlayerState.OFF,
        st_state=STStatus.STATE_OFF,
        options={CONF_POWER_ON_METHOD: PowerOnMethod.SmartThings.value},
    )
    device._st.async_turn_on = AsyncMock()
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True

    device._st.async_turn_on.assert_awaited_once_with()
    device._send_wol_packet.assert_not_called()


async def test_the_ip_control_wake_method_is_used_when_configured():
    device = make_device(
        state=MediaPlayerState.OFF,
        options={CONF_POWER_ON_METHOD: PowerOnMethod.IPControl.value},
    )
    client = AsyncMock()
    device._get_ip_control_client = MagicMock(return_value=client)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True

    client.async_power_on.assert_awaited_once_with()
    device._send_wol_packet.assert_not_called()


async def test_a_failed_ip_control_wake_falls_back_to_wol():
    device = make_device(
        state=MediaPlayerState.OFF,
        options={CONF_POWER_ON_METHOD: PowerOnMethod.IPControl.value},
    )
    client = AsyncMock()
    client.async_power_on.side_effect = SamsungIPControlError("unreachable")
    device._get_ip_control_client = MagicMock(return_value=client)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True
    device._send_wol_packet.assert_called_once()


async def test_an_unpaired_ip_control_wake_falls_back_to_wol():
    device = make_device(
        state=MediaPlayerState.OFF,
        options={CONF_POWER_ON_METHOD: PowerOnMethod.IPControl.value},
    )
    device._get_ip_control_client = MagicMock(return_value=None)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True
    device._send_wol_packet.assert_called_once()


async def test_wol_is_the_default_wake_method():
    device = make_device(state=MediaPlayerState.OFF)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=True)

    assert await device._async_power_on() is True
    device._send_wol_packet.assert_called_once()


async def test_a_failed_wake_reports_failure_and_arms_nothing():
    device = make_device(state=MediaPlayerState.OFF)
    device.async_send_command = AsyncMock(return_value=False)
    device._send_wol_packet = MagicMock(return_value=False)

    assert await device._async_power_on() is False
    device._ws.set_power_on_request.assert_not_called()

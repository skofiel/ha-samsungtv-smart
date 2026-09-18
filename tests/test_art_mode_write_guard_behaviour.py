"""A suppressed Art Mode write must end the switch's retry loop at once.

The guard exists to stop the switch hammering a TV that is ignoring the write.
Its retry loop catches ArtModeWriteSuppressed and returns; if that ever ended up
behind a broader handler, the suppression would be swallowed and the loop would
retry — the exact behaviour the guard was added to prevent.

Replaces the RetryLoopsStopTest class of test_art_mode_write_guard.py, which
asserted that the string "except ArtModeWriteSuppressed" appeared before the
string "except Exception as ex" in switch.py. Adding an unrelated, correctly
nested `except Exception` for a *read* inside the same method broke it while the
behaviour was untouched.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.samsungtv_smart.art_mode_guard import ArtModeWriteSuppressed
from custom_components.samsungtv_smart.switch import FrameArtModeSwitch


def _switch():
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {}
    entry.options = {}

    switch = FrameArtModeSwitch(
        hass, entry, AsyncMock(), "The Frame", "192.0.2.10", "uid"
    )
    switch.async_write_ha_state = MagicMock()
    switch.entity_id = "switch.the_frame_art_mode"
    # Resolved from the entity registry in real use; a unit test has none.
    switch._get_media_player_entity_id = MagicMock(
        return_value="media_player.the_frame"
    )
    return switch


@pytest.mark.parametrize("action", ["async_turn_on", "async_turn_off"])
async def test_a_suppressed_write_stops_the_loop_without_retrying(action):
    switch = _switch()
    switch._set_artmode = AsyncMock(
        side_effect=ArtModeWriteSuppressed(turn_on=True, since=2.0)
    )

    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await getattr(switch, action)()

    # One attempt, and no backoff sleep: the loop ended rather than retried.
    assert switch._set_artmode.await_count == 1
    assert sleep.await_count == 0


@pytest.mark.parametrize("action", ["async_turn_on", "async_turn_off"])
async def test_a_suppressed_write_says_so_once(action):
    switch = _switch()
    switch._set_artmode = AsyncMock(
        side_effect=ArtModeWriteSuppressed(turn_on=True, since=2.0)
    )
    switch._log = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        await getattr(switch, action)()

    assert switch._log.warning.call_count == 1


@pytest.mark.parametrize("action", ["async_turn_on", "async_turn_off"])
async def test_an_ordinary_failure_still_retries(action):
    """The suppression is special; a transient error is not."""
    switch = _switch()
    switch._set_artmode = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("asyncio.sleep", new=AsyncMock()):
        await getattr(switch, action)()

    assert switch._set_artmode.await_count > 1

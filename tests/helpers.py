"""A SamsungTVDevice built from plain values, for behavioural unit tests.

Roughly half of this repository's tests assert on the *source text* of
media_player.py (``assertIn("if not self._ws.auth_blocked:", source)``). Those
break on an innocent rename, pass while the branch they pin is dead at runtime,
and caught none of the faults that shipped — the Art Mode branch of _turn_off
had such a test while `self._ws.artmode_status` was pinned at ``Unsupported``
for the life of the entity, so the branch could never run.

This factory exists so a test can instead say what the world looks like and
assert what the entity *does*. Every knob maps to one input of the state
resolution, which keeps the test names readable as a description of the
behaviour rather than of the implementation.

``SamsungTVDevice.__init__`` opens sockets and threads, so the object is built
with ``object.__new__`` and only the attributes under test are populated — the
same approach the existing IP Control tests use.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.samsungtv_smart.api.samsungws import ArtModeStatus
from custom_components.samsungtv_smart.api.smartthings import STStatus
from custom_components.samsungtv_smart.const import DATA_ART_API, DATA_OPTIONS, DOMAIN
from custom_components.samsungtv_smart.media_player import DEFAULT_APP, SamsungTVDevice
from homeassistant.components.media_player import MediaPlayerState

ENTRY_ID = "entry-test"
HOST = "192.0.2.10"

#: Distinguishes "caller said None" from "caller said nothing" on tri-state
#: knobs, where None is itself a meaningful value ("unknown").
UNSET = object()


def make_device(
    *,
    state: MediaPlayerState = MediaPlayerState.ON,
    running_app: str | None = DEFAULT_APP,
    ip_art_mode: bool | None = None,
    panel_art: bool | None = None,
    power_state: str | None = None,
    frame_tv_support: bool = True,
    is_frame_persisted: bool = False,
    st_state: object = UNSET,
    st_channel_name: str | None = None,
    art_api_art_mode: object = UNSET,
    art_connected: bool = True,
    ws_artmode: ArtModeStatus = ArtModeStatus.Unsupported,
    options: dict | None = None,
    coordinator: object = UNSET,
) -> SamsungTVDevice:
    """Build a SamsungTVDevice whose state inputs are exactly as described.

    Args:
        state: the entity's own ``_state`` (what the last poll concluded).
        running_app: ``DEFAULT_APP`` when nothing is in the foreground, or an
            app id while one is genuinely visible.
        ip_art_mode: the ``artModeControl`` cache, populated only when the
            "IP Control Art Mode" option is on. None means the option is off.
        panel_art: what ``getTVStates.pictureMode`` says — True for 'Ambient'.
            None when there is no snapshot or the panel is asleep.
        power_state: ``device_info.device.PowerState`` ('on' / 'standby').
        frame_tv_support: whether ``device_info`` reports FrameTVSupport.
        is_frame_persisted: the ``is_frame_tv`` flag stored in entry.data.
        st_state: SmartThings power state; UNSET means no SmartThings at all.
        st_channel_name: SmartThings' running-app name ('art' while showing art).
        art_api_art_mode: the async Art API's cached flag; UNSET means the API
            is not registered in hass.data.
        art_connected: whether that API's WebSocket is live. Its art_mode is
            only maintained while it is, so a False here is a cached value that
            nothing is updating.
        ws_artmode: the legacy WebSocket art thread's status. Pinned at
            ``Unsupported`` in real installs — see disable_art_thread().
        options: config entry options.
        coordinator: the shared getTVStates coordinator. Pass one to exercise
            the real _ip_control_panel_art_cached instead of the panel_art stub.
    """
    device = object.__new__(SamsungTVDevice)

    device._state = state
    device._running_app = running_app
    device._ip_art_mode = ip_art_mode
    device._entry_id = ENTRY_ID
    device._host = HOST
    device._end_of_power_off = None
    device._log = MagicMock()
    device.entity_id = "media_player.frame"

    device._ws = MagicMock()
    device._ws.artmode_status = ws_artmode

    device._device_info = {"device": {}}
    if power_state is not None:
        device._device_info["device"]["PowerState"] = power_state
    if frame_tv_support:
        device._device_info["device"]["FrameTVSupport"] = "true"

    device._ws.auth_blocked = False
    device._mac = "aa:bb:cc:dd:ee:ff"
    device._broadcast = None

    entry = MagicMock()
    entry.data = {"is_frame_tv": is_frame_persisted}
    entry.options = options or {}

    # _get_option reads options out of hass.data, not off the entry.
    device._entry_data = {DATA_OPTIONS: dict(options or {})}

    device.hass = MagicMock()
    device.hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    art_api = None
    if art_api_art_mode is not UNSET:
        art_api = MagicMock()
        art_api.art_mode = art_api_art_mode
        art_api.is_connected = art_connected
    device.hass.data = {DOMAIN: {ENTRY_ID: {DATA_ART_API: art_api} if art_api else {}}}

    if st_state is UNSET:
        device._st = None
    else:
        device._st = MagicMock()
        device._st.state = st_state
        device._st.channel_name = st_channel_name

    # Cached-only read of the shared getTVStates snapshot. Most tests only care
    # what the panel says, so the read is stubbed; pass `coordinator` to drive
    # the real one.
    if coordinator is UNSET:
        device._ip_control_panel_art_cached = MagicMock(return_value=panel_art)
    else:
        device._get_ip_control_state_coordinator = MagicMock(return_value=coordinator)

    device._get_ip_control_client = MagicMock(return_value=None)
    device._async_switch_entity = AsyncMock()
    device.send_command = MagicMock()
    device.async_send_command = AsyncMock(return_value=True)
    device._power_off_in_progress = MagicMock(return_value=False)

    async def _executor_job(func, *args):
        return func(*args)

    device.hass.async_add_executor_job = _executor_job

    return device


__all__ = [
    "DEFAULT_APP",
    "ENTRY_ID",
    "HOST",
    "UNSET",
    "ArtModeStatus",
    "MediaPlayerState",
    "STStatus",
    "make_device",
]

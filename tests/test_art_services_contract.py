"""Every Art Mode service must answer with a dict, never raise.

The 22 ``async_art_*`` methods are registered as Home Assistant services that
return a response, and they all follow the same shape: refuse politely when the
TV is not a Frame, and turn any failure into ``{"error": ...}``. A service that
raises instead fails the caller's script with a traceback, which is a much worse
outcome than a result carrying an error.

That contract had no tests at all — 932 lines of service code, the densest
remaining concentration of `except Exception` in the integration. These sweep
every service rather than naming them one by one, so a service added later is
covered the day it is written, and one that quietly starts raising is caught.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.samsungtv_smart.media_player import SamsungTVDevice
from tests.helpers import make_device

# Arguments that have no default, so a call cannot be made without them. The
# values are only shaped to be plausible; nothing here reaches a real TV.
REQUIRED_ARGS = {
    "async_art_set_artmode": {"enabled": True},
    "async_art_select_image": {"content_id": "MY_F0001"},
    "async_art_upload": {"file_path": "/nonexistent/painting.jpg"},
    "async_art_upload_batch": {"folder": "/nonexistent/folder"},
    "async_art_delete": {"content_id": "MY_F0001"},
    "async_art_get_thumbnail": {"content_id": "MY_F0001"},
    "async_art_set_brightness": {"brightness": 50},
    "async_art_set_color_temperature": {"color_temperature": 5},
    "async_art_change_matte": {"content_id": "MY_F0001", "matte_id": "none"},
    "async_art_set_photo_filter": {"content_id": "MY_F0001", "filter_id": "none"},
    "async_art_set_favourite": {"content_id": "MY_F0001"},
    "async_art_set_slideshow": {"duration": "10"},
    "async_art_set_auto_rotation": {"duration": "10"},
}


def _service_names() -> list[str]:
    return sorted(
        name
        for name in dir(SamsungTVDevice)
        if name.startswith("async_art_")
        and inspect.iscoroutinefunction(getattr(SamsungTVDevice, name))
    )


SERVICES = _service_names()


def _art_device(*, is_frame: bool, api_error: Exception | None = None):
    """A device whose Art API either answers with mocks or fails on everything."""
    from custom_components.samsungtv_smart.api.art import SamsungTVAsyncArt

    device = make_device()
    device._art_api = AsyncMock(spec=SamsungTVAsyncArt)
    if api_error is not None:
        # Aimed at the real class's coroutine methods, not at dir() of the mock:
        # AsyncMock creates its children on first access, so a fresh one lists
        # none of them and a loop over it would arm nothing.
        for attr in dir(SamsungTVAsyncArt):
            if attr.startswith("_"):
                continue
            if inspect.iscoroutinefunction(getattr(SamsungTVAsyncArt, attr, None)):
                getattr(device._art_api, attr).side_effect = api_error

    # Awaiting an AsyncMock hands back another AsyncMock, so a service that
    # then does `result.get(...)` builds a coroutine nobody awaits. Give the
    # readers a real payload instead: closer to a live TV, and it keeps the
    # suite free of RuntimeWarnings that point at production line numbers
    # while meaning nothing.
    device._art_api.get_current.return_value = {"content_id": "MY_F0001"}
    device._art_api.get_artmode.return_value = "off"
    device._art_api.available.return_value = []
    device._art_api.get_matte_list.return_value = []
    device._art_api.get_photo_filter_list.return_value = []
    device._art_api.get_brightness.return_value = {"value": 5}
    device._art_api.get_color_temperature.return_value = {"value": 0}

    device._ensure_frame_tv_check = AsyncMock(return_value=is_frame)
    device._frame_tv_supported = is_frame
    device._frame_art_last_result = None
    device.async_write_ha_state = MagicMock()

    # Helpers that would otherwise talk to a TV, a coordinator or the disk.
    device._ensure_art_mode_ready = AsyncMock(return_value=True)
    device._ensure_tv_awake_for_art = AsyncMock(return_value=True)
    device._panel_shows_art = AsyncMock(return_value=True)
    device._validate_matte_id = AsyncMock(return_value="none")
    device._cleanup_orphan_thumbnails = AsyncMock(return_value=0)
    device._retry_new_thumbnail = AsyncMock()
    device._art_panel_size = MagicMock(return_value=(3840, 2160))
    device._get_active_slideshow_api = MagicMock(return_value="slideshow")
    # The one mocked helper that stands in for the Art API rather than guarding
    # the way to it: the slideshow services reach the TV through it, so it has
    # to fail when the API is meant to be failing.
    device._set_slideshow_via_active_api = AsyncMock(
        return_value={}, side_effect=api_error
    )
    device._get_ip_control_client = MagicMock(return_value=None)
    device.async_send_command = AsyncMock(return_value=True)
    return device


async def _call(device, name):
    """Call one service with plausible arguments.

    art_identify is the only service that does not start with the Frame check,
    and it hands off to art_identify.async_identify_for_entry — a separate
    module with its own reverse-search and LLM concerns. Stubbed so this file
    stays about the service contract.
    """
    with patch(
        "custom_components.samsungtv_smart.art_identify.async_identify_for_entry",
        new=AsyncMock(return_value={"error": "identification unavailable"}),
    ):
        return await getattr(device, name)(**REQUIRED_ARGS.get(name, {}))


def test_the_sweep_actually_found_the_services():
    """Guards the introspection: a rename must not silently empty this file."""
    assert len(SERVICES) >= 20


@pytest.mark.parametrize("name", SERVICES)
async def test_a_non_frame_tv_is_refused_with_a_result_not_an_exception(name):
    device = _art_device(is_frame=False)

    result = await _call(device, name)

    assert isinstance(result, dict), f"{name} did not return a dict"
    assert "error" in result, f"{name} did not report an error: {result}"


@pytest.mark.parametrize("name", SERVICES)
async def test_a_failing_art_api_becomes_an_error_result(name):
    """A TV that drops the art channel mid-call must not raise into a script."""
    device = _art_device(is_frame=True, api_error=RuntimeError("art channel closed"))

    result = await _call(device, name)

    assert isinstance(result, dict), f"{name} did not return a dict"
    assert "error" in result, f"{name} swallowed the failure silently: {result}"


@pytest.mark.parametrize("name", SERVICES)
def test_every_service_is_declared_to_return_a_dict(name):
    """The service schemas advertise a response; the annotation must agree."""
    annotation = inspect.signature(getattr(SamsungTVDevice, name)).return_annotation

    assert annotation is not inspect.Signature.empty, f"{name} has no return type"
    assert "dict" in str(annotation), f"{name} returns {annotation!r}, not a dict"

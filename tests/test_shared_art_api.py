"""There must be exactly one Art API client per entry.

The TV's com.samsung.art-app channel tolerates a single client: with more than
one it routes d2d_service_message responses unpredictably and eventually stops
handshaking new connections, so art mode detection silently dies.

Three platforms each carried their own "create one on a miss" fallback. The
sensor's and the switch's at least stored what they built; media_player's did
not, so a miss produced a second, invisible client — and it sat in an else
branch that skipped disable_art_thread(), leaving the legacy WebSocket art
thread running as a third contender on the same channel.
"""

from unittest.mock import MagicMock, patch

from custom_components.samsungtv_smart import get_or_create_art_api
from custom_components.samsungtv_smart.const import DATA_ART_API, DATA_CFG, DOMAIN

ENTRY_ID = "entry-1"


def _hass(store=None):
    hass = MagicMock()
    hass.data = {DOMAIN: {ENTRY_ID: store if store is not None else {}}}
    return hass


def _entry():
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = {"host": "192.0.2.10"}
    return entry


def test_an_existing_instance_is_handed_straight_back():
    existing = object()
    hass = _hass({DATA_ART_API: existing})

    assert get_or_create_art_api(hass, _entry()) is existing


def test_repeated_calls_never_build_a_second_client():
    hass = _hass({DATA_CFG: {"host": "192.0.2.10"}})

    with patch(
        "custom_components.samsungtv_smart.async_get_clientsession",
        return_value=MagicMock(),
    ):
        first = get_or_create_art_api(hass, _entry())
        second = get_or_create_art_api(hass, _entry())

    assert first is second


def test_what_it_builds_is_registered_for_everyone_else():
    """The media_player fallback used to keep its instance private."""
    store = {DATA_CFG: {"host": "192.0.2.10"}}
    hass = _hass(store)

    with patch(
        "custom_components.samsungtv_smart.async_get_clientsession",
        return_value=MagicMock(),
    ):
        created = get_or_create_art_api(hass, _entry())

    assert store[DATA_ART_API] is created


def test_it_works_before_the_entry_store_exists():
    hass = MagicMock()
    hass.data = {}

    with patch(
        "custom_components.samsungtv_smart.async_get_clientsession",
        return_value=MagicMock(),
    ):
        created = get_or_create_art_api(hass, _entry())

    assert hass.data[DOMAIN][ENTRY_ID][DATA_ART_API] is created

"""A malformed UPnP reply must not fail the whole entity update.

async_get_volume / async_get_mute parsed the SOAP body with no guard, so a
malformed or non-UTF-8 reply raised out of them, up through
_update_volume_info and _async_update, and failed the entity's update cycle —
for an optional volume read. Every caller already treats None as "could not
read", so that is what an unparseable body now produces.
"""

from unittest.mock import AsyncMock

from custom_components.samsungtv_smart.upnp import (
    MAX_RESPONSE_BYTES,
    SamsungUPnP,
    _first_tag_text,
)


def _body(tag: str, value: str) -> bytes:
    return (
        '<?xml version="1.0"?><s:Envelope '
        'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        f"<{tag}>{value}</{tag}></s:Body></s:Envelope>"
    ).encode()


def test_a_well_formed_reply_is_read():
    assert _first_tag_text(_body("CurrentVolume", "17"), "CurrentVolume") == "17"


def test_a_truncated_reply_is_unreadable_rather_than_fatal():
    assert _first_tag_text(b"<s:Envelope><CurrentVolume>17", "CurrentVolume") is None


def test_a_non_xml_reply_is_unreadable_rather_than_fatal():
    assert _first_tag_text(b"503 Service Unavailable", "CurrentVolume") is None


def test_a_non_utf8_reply_is_unreadable_rather_than_fatal():
    assert _first_tag_text(b"\xff\xfe<CurrentVolume>1", "CurrentVolume") is None


def test_a_missing_tag_is_unreadable():
    assert _first_tag_text(_body("SomethingElse", "17"), "CurrentVolume") is None


async def test_get_volume_survives_a_malformed_reply():
    upnp = SamsungUPnP("192.0.2.10", session=AsyncMock())
    upnp._soap_request = AsyncMock(return_value=b"not xml at all")

    assert await upnp.async_get_volume() is None


async def test_get_mute_survives_a_malformed_reply():
    upnp = SamsungUPnP("192.0.2.10", session=AsyncMock())
    upnp._soap_request = AsyncMock(return_value=b"not xml at all")

    assert await upnp.async_get_mute() is None


async def test_get_mute_survives_a_non_numeric_value():
    """The TV answering 'true' instead of '1' used to raise ValueError."""
    upnp = SamsungUPnP("192.0.2.10", session=AsyncMock())
    upnp._soap_request = AsyncMock(return_value=_body("CurrentMute", "true"))

    assert await upnp.async_get_mute() is None


async def test_mute_is_read_normally():
    upnp = SamsungUPnP("192.0.2.10", session=AsyncMock())
    upnp._soap_request = AsyncMock(return_value=_body("CurrentMute", "1"))

    assert await upnp.async_get_mute() is True


def test_the_response_read_is_bounded():
    """Anything answering on the TV's unauthenticated UPnP port is untrusted."""
    assert MAX_RESPONSE_BYTES <= 1024 * 1024

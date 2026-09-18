"""Smartthings TV integration UPnP implementation."""

import logging
import xml.etree.ElementTree as ET

from aiohttp import ClientSession
import async_timeout

DEFAULT_TIMEOUT = 0.2

# A SOAP reply carrying one integer is a few hundred bytes. Reading without
# a bound lets anything answering on the TV's UPnP port — the responses are
# unauthenticated plain HTTP on the LAN — hand us an arbitrarily large body
# to buffer and then parse.
MAX_RESPONSE_BYTES = 64 * 1024

_LOGGER = logging.getLogger(__name__)


class SamsungUPnP:
    """UPnP implementation for Samsung TV."""

    def __init__(self, host, session: ClientSession | None = None):
        """Initialize the class."""
        self._host = host
        self._connected = False
        if session:
            self._session = session
            self._managed_session = False
        else:
            self._session = ClientSession()
            self._managed_session = True

    async def _soap_request(
        self, action, arguments, protocole, *, timeout=DEFAULT_TIMEOUT
    ):
        """Send a SOAP request to the TV."""
        headers = {
            "SOAPAction": f'"urn:schemas-upnp-org:service:{protocole}:1#{action}"',
            "content-type": "text/xml",
        }
        body = f"""<?xml version="1.0" encoding="utf-8"?>
                <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                    <s:Body>
                    <u:{action} xmlns:u="urn:schemas-upnp-org:service:{protocole}:1">
                        <InstanceID>0</InstanceID>
                        {arguments}
                    </u:{action}>
                    </s:Body>
                </s:Envelope>"""
        try:
            async with async_timeout.timeout(timeout), self._session.post(
                f"http://{self._host}:9197/upnp/control/{protocole}1",
                headers=headers,
                data=body,
                raise_for_status=True,
            ) as resp:
                response = await resp.content.read(MAX_RESPONSE_BYTES)
                self._connected = True
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug(exc)
            self._connected = False
            return None

        return response

    @property
    def connected(self):
        """Return if connected to Samsung TV."""
        return self._connected

    async def async_disconnect(self):
        """Disconnect from TV and close session."""
        if self._managed_session:
            await self._session.close()

    async def async_get_volume(self):
        """Return volume status."""
        response = await self._soap_request(
            "GetVolume", "<Channel>Master</Channel>", "RenderingControl"
        )
        if response is None:
            return None

        return _first_tag_text(response, "CurrentVolume")

    async def async_set_volume(self, volume):
        """Set the volume level."""
        await self._soap_request(
            "SetVolume",
            f"<Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>",
            "RenderingControl",
        )

    async def async_get_mute(self):
        """Return mute status."""
        response = await self._soap_request(
            "GetMute", "<Channel>Master</Channel>", "RenderingControl"
        )
        if response is None:
            return None

        mute = _first_tag_text(response, "CurrentMute")
        if mute is None:
            return None
        try:
            return int(mute) != 0
        except ValueError:
            _LOGGER.debug("UPnP: non-numeric CurrentMute %r", mute)
            return None

    async def async_set_current_media(self, url):
        """Set media to playback and play it."""

        if (
            await self._soap_request(
                "SetAVTransportURI",
                f"<CurrentURI>{url}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>",
                "AVTransport",
                timeout=2.0,
            )
            is None
        ):
            return False

        await self._soap_request("Play", "<Speed>1</Speed>", "AVTransport")
        return True

    async def async_play(self):
        """Play media that was already set as current."""
        await self._soap_request("Play", "<Speed>1</Speed>", "AVTransport")


def _first_tag_text(response: bytes, tag: str) -> str | None:
    """Return the text of the first ``tag`` element, or None if unreadable.

    Every caller already treats None as "could not read", and none of them
    guarded the parse: a malformed or non-UTF-8 reply raised out of
    async_get_volume / async_get_mute, up through _update_volume_info and
    _async_update, and failed the whole entity update rather than just the
    optional volume read it came from.
    """
    try:
        tree = ET.fromstring(response.decode("utf8"))
    except (ET.ParseError, UnicodeDecodeError) as exc:
        _LOGGER.debug("UPnP: could not parse the %s reply: %s", tag, exc)
        return None

    text = None
    for elem in tree.iter(tag=tag):
        text = elem.text
    return text

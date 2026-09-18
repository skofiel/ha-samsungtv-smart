"""Diagnostics support for Samsung TV Smart."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_ID, CONF_MAC, CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ART_LLM_API_KEY,
    CONF_ART_VISION_API_KEY,
    CONF_DEVICE_ID,
    CONF_IP_CONTROL_TOKEN,
    CONF_OAUTH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Diagnostics must never hang the UI on a slow or unreachable cloud.
SMARTTHINGS_TIMEOUT = 15

# Diagnostics are routinely attached to GitHub issues, so every credential in
# entry.data has to be listed here — anything missing is published in clear.
# CONF_API_KEY is the SmartThings PAT; the two art keys are the user's own
# OpenAI/Gemini and Google Vision keys, which are billable and were leaking.
TO_REDACT = {
    CONF_API_KEY,
    CONF_ART_LLM_API_KEY,
    CONF_ART_VISION_API_KEY,
    CONF_IP_CONTROL_TOKEN,
    CONF_MAC,
    CONF_OAUTH_TOKEN,
    CONF_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    diag_data = {"entry": async_redact_data(entry.as_dict(), TO_REDACT)}

    yaml_data = hass.data[DOMAIN].get(entry.unique_id, {})
    if yaml_data:
        diag_data["config_data"] = async_redact_data(yaml_data, TO_REDACT)

    device_id = entry.data.get(CONF_ID, entry.entry_id)
    hass_data = _async_device_ha_info(hass, device_id)
    if hass_data:
        diag_data["device"] = hass_data

    diag_data["smartthings"] = await _async_smartthings_status(hass, entry)

    return diag_data


async def _async_smartthings_status(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return what SmartThings currently reports for the TV and its children.

    The cloud sensors (illuminance, relative brightness, the five
    powerConsumptionReport fields) are pass-throughs: the integration reports
    what SmartThings hands it and adds nothing. So when one of them looks wrong
    — a constant illuminance, five permanently "unknown" energy sensors — the
    question is whether the cloud is publishing anything at all, and that is not
    answerable from Home Assistant's side.

    Every attribute is dumped with its SmartThings ``timestamp``, which settles
    it directly: a reading whose timestamp is days old is frozen at the source,
    not mis-parsed here.
    """
    from . import async_get_samsungtv_api_key  # noqa: PLC0415 - avoids a cycle

    st_device_id = entry.data.get(CONF_DEVICE_ID)
    if not st_device_id:
        return {"configured": False}

    try:
        api_key = await async_get_samsungtv_api_key(hass, entry)
        if not api_key:
            return {"configured": True, "error": "no SmartThings token available"}

        from pysmartthings import SmartThings  # noqa: PLC0415

        client = SmartThings(session=async_get_clientsession(hass))
        client.authenticate(api_key)

        async with asyncio.timeout(SMARTTHINGS_TIMEOUT):
            result: dict[str, Any] = {
                "configured": True,
                "devices": {
                    "tv": await _async_device_status(client, st_device_id),
                },
            }
            for device in await client.get_devices():
                if device.parent_device_id != st_device_id:
                    continue
                result["devices"][f"child:{device.label}"] = await _async_device_status(
                    client, device.device_id
                )
        return result
    except Exception as ex:  # noqa: BLE001 - diagnostics must always return
        _LOGGER.debug("SmartThings diagnostics collection failed: %s", ex)
        return {"configured": True, "error": f"{type(ex).__name__}: {ex}"}


async def _async_device_status(client, device_id: str) -> dict[str, Any]:
    """Flatten one device's status into plain JSON, timestamps included."""
    try:
        components = await client.get_device_status(device_id)
    except Exception as ex:  # noqa: BLE001 - one bad device must not hide the rest
        return {"error": f"{type(ex).__name__}: {ex}"}

    out: dict[str, Any] = {}
    for component, capabilities in components.items():
        for capability, attributes in capabilities.items():
            for attribute, status in attributes.items():
                timestamp = getattr(status, "timestamp", None)
                out[f"{component}.{capability}.{attribute}"] = {
                    "value": getattr(status, "value", None),
                    "unit": getattr(status, "unit", None),
                    # The age of this reading is the whole point: a value that
                    # never changes has a timestamp that never moves.
                    "timestamp": timestamp.isoformat() if timestamp else None,
                }
    return out


@callback
def _async_device_ha_info(hass: HomeAssistant, device_id: str) -> dict | None:
    """Gather information how this TV device is represented in Home Assistant."""

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    hass_device = device_registry.async_get_device(identifiers={(DOMAIN, device_id)})
    if not hass_device:
        return None

    data = {
        "name": hass_device.name,
        "name_by_user": hass_device.name_by_user,
        "model": hass_device.model,
        "manufacturer": hass_device.manufacturer,
        "sw_version": hass_device.sw_version,
        "disabled": hass_device.disabled,
        "disabled_by": hass_device.disabled_by,
        "entities": {},
    }

    hass_entities = er.async_entries_for_device(
        entity_registry,
        device_id=hass_device.id,
        include_disabled_entities=True,
    )

    for entity_entry in hass_entities:
        if entity_entry.platform != DOMAIN:
            continue
        state = hass.states.get(entity_entry.entity_id)
        state_dict = None
        if state:
            state_dict = dict(state.as_dict())
            # The entity_id is already provided at root level.
            state_dict.pop("entity_id", None)
            # The context doesn't provide useful information in this case.
            state_dict.pop("context", None)
            # Redact the `entity_picture` attribute as it contains a token.
            if "entity_picture" in state_dict["attributes"]:
                state_dict["attributes"] = {
                    **state_dict["attributes"],
                    "entity_picture": REDACTED,
                }

        data["entities"][entity_entry.entity_id] = {
            "name": entity_entry.name,
            "original_name": entity_entry.original_name,
            "disabled": entity_entry.disabled,
            "disabled_by": entity_entry.disabled_by,
            "entity_category": entity_entry.entity_category,
            "device_class": entity_entry.device_class,
            "original_device_class": entity_entry.original_device_class,
            "icon": entity_entry.icon,
            "original_icon": entity_entry.original_icon,
            "unit_of_measurement": entity_entry.unit_of_measurement,
            "state": state_dict,
        }

    return data

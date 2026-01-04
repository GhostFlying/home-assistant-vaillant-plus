from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VaillantClient
from .const import CONF_DID, DISPATCHERS, DOMAIN, EVT_DEVICE_CONNECTED, API_CLIENT
from .entity import VaillantEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][entry.entry_id]

    added = False

    @callback
    def async_new_entities(device_attrs: dict[str, Any]):
        nonlocal added
        if added:
            return
        try:
            # 仅管理员设备提供天气曲线开关
            if client.device is not None and client.device.is_manager:
                if device_attrs.get("Weather_compensation") is not None:
                    async_add_entities([VaillantWeatherCurveSwitch(client)])
                    added = True
                else:
                    _LOGGER.debug("No Weather_compensation attr, skip adding switch")
            else:
                _LOGGER.debug("Device is not manager, skip adding weather curve switch")
        except Exception as e:
            _LOGGER.error("Failed to add weather curve switch: %s", e)

    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_entities
    )
    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)

    return True


class VaillantWeatherCurveSwitch(VaillantEntity, SwitchEntity):
    def __init__(self, client: VaillantClient):
        super().__init__(client)
        self._attr_name = "天气曲线开关"

    @property
    def unique_id(self) -> str | None:
        return f"{self.device.id}_weather_curve"

    @property
    def is_on(self) -> bool:
        try:
            value = self.get_device_attr("Weather_compensation")
            return value == 1 or value is True
        except Exception:
            return False

    async def async_turn_on(self, **kwargs):
        try:
            ok = await self._client.enable_weather_curve(True)
            if ok:
                self.set_device_attr("Weather_compensation", 1)
        except Exception as e:
            _LOGGER.error("Failed to enable weather curve: %s", e)

    async def async_turn_off(self, **kwargs):
        try:
            ok = await self._client.enable_weather_curve(False)
            if ok:
                self.set_device_attr("Weather_compensation", 0)
        except Exception as e:
            _LOGGER.error("Failed to disable weather curve: %s", e)


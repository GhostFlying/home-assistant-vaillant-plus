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


def _is_weather_curve_enabled(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    if iv in (0, 1):
        return iv == 0
    return bool(iv)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][entry.entry_id]

    added_entities: list[str] = []

    @callback
    def async_new_switch(device_attrs: dict[str, Any]):
        new_entities = []
        managed = getattr(client.device, "is_manager", True)
        if not managed:
            return
        if (
            "Weather_compensation" in device_attrs
            and "weather_curve_switch" not in added_entities
        ):
            new_entities.append(VaillantWeatherCurveSwitch(client))
            added_entities.append("weather_curve_switch")
        if len(new_entities) > 0:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_switch
    )
    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)
    return True


class VaillantWeatherCurveSwitch(VaillantEntity, SwitchEntity):
    def __init__(self, client: VaillantClient):
        super().__init__(client)
        self._attr_available = False

    @property
    def unique_id(self) -> str | None:
        return f"{self.device.id}_weather_curve"

    @property
    def name(self) -> str | None:
        return "气候补偿"

    @property
    def is_on(self) -> bool | None:
        return _is_weather_curve_enabled(self.get_device_attr("Weather_compensation"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.enable_weather_curve(True)
        self.set_device_attr("Weather_compensation", 0)
        self._client.broadcast_local_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.enable_weather_curve(False)
        self.set_device_attr("Weather_compensation", 1)
        self._client.broadcast_local_update()

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        if "Weather_compensation" in data:
            value = data.get("Weather_compensation")
            enabled = _is_weather_curve_enabled(value)
            _LOGGER.warning(
                "Weather_compensation update raw=%s enabled=%s", value, enabled
            )
            self._attr_available = enabled
            self.async_schedule_update_ha_state(True)

"""Vaillant number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VaillantClient
from .const import CONF_DID, DISPATCHERS, DOMAIN, EVT_DEVICE_CONNECTED, EVT_DEVICE_UPDATED, API_CLIENT
from .entity import VaillantEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
class VaillantNumberEntityDescription(NumberEntityDescription):
    """A class that describes Vaillant number entities."""
    
    entity_class: type[NumberEntity] | None = None

NUMBER_DESCRIPTIONS = (
    VaillantNumberEntityDescription(
        key="temp_offset",
        name="室温偏移（设置温度 - 实际室温）",
        entity_class="VaillantTempOffsetNumber",
    ),
    VaillantNumberEntityDescription(
        key="Heating_Curve",
        name="供暖曲线",
        entity_class="VaillantHeatingCurveNumber",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up Vaillant number entities."""
    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][entry.entry_id]

    added_entities: list[str] = []

    @callback
    def async_new_entities(device_attrs: dict[str, Any]):
        new_entities = []
        for description in NUMBER_DESCRIPTIONS:
            if (client.device is not None and client.device.is_manager and 
                description.key not in added_entities and 
                description.entity_class is not None):
                # Handle string class references
                if isinstance(description.entity_class, str):
                    entity_class = globals()[description.entity_class]
                else:
                    entity_class = description.entity_class
                new_entities.append(entity_class(client, description))
                added_entities.append(description.key)
        if len(new_entities) > 0:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_entities
    )
    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)

    return True


class VaillantTempOffsetNumber(VaillantEntity, NumberEntity):
    """Define a Vaillant temp offset number entity."""

    _attr_native_min_value = -7
    _attr_native_max_value = 7
    _attr_native_step = 1

    def __init__(
        self,
        client: VaillantClient,
        description: NumberEntityDescription,
    ):
        super().__init__(client)
        self.entity_description = description

    @property
    def unique_id(self) -> str | None:
        return f"{self.device.id}_{self.entity_description.key}_number"

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        if self.entity_description.key in data:
            value = data.get(self.entity_description.key)
            self._attr_native_value = value
            self._attr_available = value is not None
            self.async_schedule_update_ha_state(True)

    async def async_set_native_value(self, value: float) -> None:
        await self._client.update_device_config({"tempOffset": int(value)})


class VaillantHeatingCurveNumber(VaillantEntity, NumberEntity):
    """Define a Vaillant heating curve number entity."""

    _attr_native_min_value = 0.2
    _attr_native_max_value = 4.0
    _attr_native_step = 0.1

    def __init__(
        self,
        client: VaillantClient,
        description: NumberEntityDescription,
    ):
        super().__init__(client)
        self.entity_description = description

    @property
    def unique_id(self) -> str | None:
        return f"{self.device.id}_{self.entity_description.key}_number"

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        if self.entity_description.key in data:
            value = data.get(self.entity_description.key)
            self._attr_native_value = value
            self._attr_available = value is not None
            self.async_schedule_update_ha_state(True)

    async def async_set_native_value(self, value: float) -> None:
        await self._client.control_device({"Heating_Curve": value})

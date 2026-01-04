"""Vaillant vSMART entity classes."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import Entity, DeviceInfo
from vaillant_plus_cn_api import Device

from .client import VaillantClient
from .const import DOMAIN, EVT_DEVICE_UPDATED

UPDATE_INTERVAL = timedelta(seconds=30)

_LOGGER: logging.Logger = logging.getLogger(__package__)


class VaillantEntity(Entity):
    """Base class for Vaillant entities."""

    def __init__(
        self,
        client: VaillantClient,
    ):
        """Initialize."""
        self._client = client

    @property
    def device_attrs(self) -> dict[str, Any]:
        return self._client.device_attrs

    @property
    def device(self) -> Device:
        return self._client.device

    def get_device_attr(self, attr) -> Any:
        if self._client.device_attrs.get(attr) is not None:
            return self._client.device_attrs.get(attr)
        return None
        
    def set_device_attr(self, attr, value):
        """
        Set the value of a device attribute.
        If the attribute does not exist, add it to the device attributes.
        """
        if attr not in self._client.device_attrs:
            self._client.device_attrs[attr] = value  # 动态添加属性
        else:
            self._client.device_attrs[attr] = value  # 更新属性值

        data = self._client.device_attrs.copy()

        logging.warning("set_device_attr %s %s", attr, value)

        self.update_from_latest_data(data)
        self.async_write_ha_state()

        if self.hass is not None and self.device is not None:
            async_dispatcher_send(
                self.hass,
                EVT_DEVICE_UPDATED.format(self.device.id),
                data,
            )
            
    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        @callback
        def update(data: dict[str, Any]) -> None:
            """Update the state."""
            _LOGGER.debug("write ha state: %s", data)
            self.update_from_latest_data(data)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, EVT_DEVICE_UPDATED.format(self.device.id), update
            )
        )

        if len(self.device_attrs) > 0:
            self.update_from_latest_data(self.device_attrs)

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def device_info(self) -> DeviceInfo:
        """Return all device info available for this entity."""

        return DeviceInfo(
            identifiers={(DOMAIN, self.device.id)},
            name=self.device.product_name,
            model=self.device.model,
            # sw_version=self.device.mcu_soft_version,
            # hw_version=self.device.mcu_hard_version,
            manufacturer="Vaillant",
        )

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        """Update the entity from the latest data."""
        # _LOGGER.warning("VaillantEntity update_from_latest_data %s",data)
        # self.async_schedule_update_ha_state()

    async def send_command(self, attr: str, value: Any) -> None:
        """Send operations to cloud."""
        await self._client.control_device({
            f"{attr}": value
        })

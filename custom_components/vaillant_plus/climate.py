"""The Vaillant Plus climate platform."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
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
        return iv == 1
    return bool(iv)

DEFAULT_TEMPERATURE_INCREASE = 0.5

PRESET_FLOW_TEMPERATURE = "出水温度模式"
PRESET_INDOOR_TEMPERATURE = "室温模式"

SUPPORTED_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.PRESET_MODE
)
SUPPORTED_HVAC_MODES = [HVACMode.HEAT, HVACMode.OFF]
SUPPORTED_PRESET_MODES = [PRESET_FLOW_TEMPERATURE, PRESET_INDOOR_TEMPERATURE]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
) -> bool:
    """Set up Vaillant devices from a config entry."""

    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][
        entry.entry_id
    ]

    added_entities = []

    @callback
    def async_new_climate(device_attrs: dict[str, Any]):
        _LOGGER.debug("New climate found device_attrs == %s", device_attrs)

        new_devices: list[ClimateEntity] = []
        if "boiler_climate" not in added_entities:
            new_devices.append(VaillantBoilerClimate(client))
            added_entities.append("boiler_climate")
        if len(new_devices) > 0:
            async_add_devices(new_devices)


    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_climate
    )

    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)

    return True


class VaillantBoilerClimate(VaillantEntity, ClimateEntity):
    def __init__(self, client: VaillantClient):
        super().__init__(client)
        self._cache: dict[str, Any] = {}

    @property
    def unique_id(self) -> str:
        return f"{self.device.id}_climate"

    @property
    def name(self) -> str | None:
        return "壁挂炉"

    @property
    def supported_features(self) -> int:
        return SUPPORTED_FEATURES

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self) -> float | None:
        return DEFAULT_TEMPERATURE_INCREASE

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return SUPPORTED_HVAC_MODES

    def _get_cached_value(self, attr_name: str, default: Any = None) -> Any:
        try:
            value = self.get_device_attr(attr_name)
            if value is not None:
                self._cache[attr_name] = value
        except (AttributeError, KeyError) as err:
            _LOGGER.debug("Failed to get device attribute %s: %s", attr_name, err)
            value = None
        if value is None and attr_name in self._cache:
            return self._cache[attr_name]
        return value if value is not None else default

    def _weather_curve_enabled(self) -> bool | None:
        return _is_weather_curve_enabled(self._get_cached_value("Weather_compensation"))

    def _current_preset_mode(self) -> str:
        enabled = self._weather_curve_enabled()
        if enabled is True:
            self._cache["preset_mode"] = PRESET_INDOOR_TEMPERATURE
        elif enabled is False:
            self._cache["preset_mode"] = PRESET_FLOW_TEMPERATURE
        return self._cache.get("preset_mode", PRESET_FLOW_TEMPERATURE)

    async def _ensure_weather_curve(self, enabled: bool) -> bool:
        current = self._weather_curve_enabled()
        if current is not None and current == enabled:
            return True
        try:
            await self._client.enable_weather_curve(enabled)
        except Exception as err:
            _LOGGER.error("Failed to set weather curve to %s: %s", enabled, err)
            return False
        self._client.device_attrs["Weather_compensation"] = 1 if enabled else 0
        self._client.broadcast_local_update()
        return True

    @property
    def preset_modes(self) -> list[str]:
        return SUPPORTED_PRESET_MODES

    @property
    def preset_mode(self) -> str:
        return self._current_preset_mode()

    @property
    def hvac_mode(self) -> HVACMode:
        enable = _is_weather_curve_enabled(self._get_cached_value("Heating_Enable", default=0))
        if enable is True:
            self._cache["hvac_mode"] = HVACMode.HEAT
        elif enable is False:
            self._cache["hvac_mode"] = HVACMode.OFF
        return self._cache.get("hvac_mode", HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        enable = _is_weather_curve_enabled(self._get_cached_value("Heating_Enable", default=0))
        if enable is False:
            self._cache["hvac_action"] = HVACAction.OFF
        elif enable is True:
            self._cache["hvac_action"] = HVACAction.HEATING
        return self._cache.get("hvac_action", HVACAction.IDLE)

    @property
    def current_temperature(self) -> float | None:
        if self.preset_mode == PRESET_INDOOR_TEMPERATURE:
            return self._get_cached_value("indoor_temperature")
        return self._get_cached_value("Flow_Temperature_Setpoint", default=35.0)

    @property
    def target_temperature(self) -> float | None:
        if self.preset_mode == PRESET_INDOOR_TEMPERATURE:
            return self._get_cached_value("indoor_temperature")
        return self._get_cached_value("Flow_Temperature_Setpoint", default=35.0)

    @property
    def min_temp(self) -> float | None:
        if self.preset_mode == PRESET_INDOOR_TEMPERATURE:
            return 5.0
        return self._get_cached_value("Lower_Limitation_of_CH_Setpoint", default=30.0)

    @property
    def max_temp(self) -> float | None:
        if self.preset_mode == PRESET_INDOOR_TEMPERATURE:
            return 30.0
        return self._get_cached_value("Upper_Limitation_of_CH_Setpoint", default=75.0)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if not self.device.is_manager:
            _LOGGER.error("Current user do not have permission to set preset mode")
            raise ServiceValidationError
        if preset_mode not in SUPPORTED_PRESET_MODES:
            return
        if preset_mode == PRESET_INDOOR_TEMPERATURE:
            ok = await self._ensure_weather_curve(True)
        else:
            ok = await self._ensure_weather_curve(False)
        if ok:
            self._cache["preset_mode"] = preset_mode
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.debug("Setting HVAC mode to: %s", hvac_mode)
        try:
            if hvac_mode == HVACMode.OFF:
                await self._client.control_device({"Heating_Enable": False})
                self.set_device_attr("Heating_Enable", False)
                self._cache["hvac_mode"] = HVACMode.OFF
                self._cache["hvac_action"] = HVACAction.OFF
            elif hvac_mode == HVACMode.HEAT:
                await self._client.control_device({"Heating_Enable": True})
                self.set_device_attr("Heating_Enable", True)
                self._cache["hvac_mode"] = HVACMode.HEAT
                self._cache["hvac_action"] = HVACAction.HEATING
        except Exception as err:
            _LOGGER.error("Failed to set HVAC mode: %s", err)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs) -> None:
        new_temperature = kwargs.get(ATTR_TEMPERATURE)
        if new_temperature is None:
            return

        if self.preset_mode == PRESET_INDOOR_TEMPERATURE:
            if not await self._ensure_weather_curve(True):
                return
            await self._client.control_device({"indoor_temperature": new_temperature})
            self._cache["indoor_temperature"] = new_temperature
            self.set_device_attr("indoor_temperature", new_temperature)
            return

        if not await self._ensure_weather_curve(False):
            return
        await self._client.control_device({"Flow_Temperature_Setpoint": new_temperature})
        self._cache["Flow_Temperature_Setpoint"] = new_temperature
        self.set_device_attr("Flow_Temperature_Setpoint", new_temperature)

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        enabled = _is_weather_curve_enabled(data.get("Weather_compensation"))
        if enabled is True:
            self._cache["preset_mode"] = PRESET_INDOOR_TEMPERATURE
        elif enabled is False:
            self._cache["preset_mode"] = PRESET_FLOW_TEMPERATURE
        self.async_schedule_update_ha_state(True)

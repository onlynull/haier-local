"""燃气热水器实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, STATE_ON, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .devices import WATER_HEATER
from .entity import HaierLocalEntity
from .mappings import WATER_HEATER_EXTRAS, selected_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinators"][WATER_HEATER.key]
    async_add_entities([HaierWaterHeater(coordinator)])


class HaierWaterHeater(HaierLocalEntity, WaterHeaterEntity):
    """开关、目标温度和常用运行状态。"""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_operation_list = [STATE_ON, STATE_OFF]
    _attr_min_temp = 32
    _attr_max_temp = 60
    _attr_precision = 1
    _attr_name = None
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, WATER_HEATER, "water_heater")

    @property
    def current_operation(self) -> str | None:
        value = self._values().get("onOffStatus")
        if value is None:
            return None
        return STATE_ON if value else STATE_OFF

    @property
    def current_temperature(self) -> float | None:
        value = self._values().get("outWaterTemp")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        value = self._values().get("targetTemp")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return selected_attributes(self._values(), WATER_HEATER_EXTRAS)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.async_set_field("targetTemp", int(round(float(temperature))))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self.coordinator.async_set_field("onOffStatus", operation_mode == STATE_ON)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field("onOffStatus", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field("onOffStatus", False)

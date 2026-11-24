"""冰箱冷藏、冷冻、变温室气候实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity
from .mappings import FRIDGE_CLIMATES, ClimateSpec


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities = []
    for spec in FRIDGE_CLIMATES:
        coordinator = coordinators[spec.device.key]
        entities.append(HaierClimate(coordinator, spec))
    async_add_entities(entities)


class HaierClimate(HaierLocalEntity, ClimateEntity):
    """按官方档位换算后的温区控制。"""

    _attr_hvac_modes = [HVACMode.COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = HVACMode.COOL

    def __init__(self, coordinator, spec: ClimateSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_min_temp = spec.min_temp
        self._attr_max_temp = spec.max_temp
        self._attr_target_temperature_step = spec.step

    @property
    def available(self) -> bool:
        values = self._values()
        return super().available and self._spec.target_key in values

    @property
    def current_temperature(self) -> float | None:
        value = self._values().get(self._spec.current_key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        value = self._values().get(self._spec.target_key)
        try:
            return float(self._spec.to_display(int(value)))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values = self._values()
        attrs: dict[str, Any] = {}
        if self._spec.target_key in values:
            attrs["原始档位"] = values[self._spec.target_key]
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        level = self._spec.to_level(float(temperature))
        await self.coordinator.async_set_field(self._spec.target_key, level)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = HVACMode.COOL

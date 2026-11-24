"""数值调节实体。"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import NUMBERS, NumberSpec


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        HaierNumber(coordinators[item.device.key], item) for item in NUMBERS
    )


class HaierNumber(HaierLocalEntity, NumberEntity):
    def __init__(self, coordinator, spec: NumberSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def native_value(self) -> float | None:
        value = self._values().get(self._key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        payload: int | float = int(round(value)) if float(self._spec.step).is_integer() else value
        await self.coordinator.async_set_field(self._key, payload)

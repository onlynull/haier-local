"""可写字符串，例如夜间模式时段。"""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import TEXTS, TextSpec


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        HaierText(coordinators[item.device.key], item) for item in TEXTS
    )


class HaierText(HaierLocalEntity, TextEntity):
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0

    def __init__(self, coordinator, spec: TextSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_native_max = spec.max_length
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def native_value(self) -> str | None:
        value = self._values().get(self._key)
        if value is None:
            return None
        return str(value)

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_set_field(self._key, value)

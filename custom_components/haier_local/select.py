"""模式选择实体。"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import SELECTS, SelectSpec, option_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        HaierSelect(coordinators[item.device.key], item) for item in SELECTS
    )


class HaierSelect(HaierLocalEntity, SelectEntity):
    def __init__(self, coordinator, spec: SelectSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_options = list(spec.options.values())
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def current_option(self) -> str | None:
        value = self._values().get(self._key)
        if value is None:
            return None
        try:
            return self._spec.options.get(int(value), self._spec.options.get(value))
        except (TypeError, ValueError):
            return self._spec.options.get(value)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_field(self._key, option_value(self._spec, option))

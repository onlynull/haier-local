"""可写字符串，例如夜间模式时段。"""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import TEXTS, TextSpec, format_hour_text, hours_from_values


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
        super().__init__(coordinator, spec.device, spec.key, unique_key=spec.unique_key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_native_max = spec.max_length
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        if self._spec.control:
            return super().available
        return super().available and self._key in self._values()

    @property
    def native_value(self) -> str | None:
        if self._spec.control == "zcw_hours":
            return format_hour_text(hours_from_values(self._values()))
        value = self._values().get(self._key)
        if value is None:
            return None
        return str(value)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self._spec.control != "zcw_hours":
            return None
        return {"填写格式": "7-9,18-22"}

    async def async_set_value(self, value: str) -> None:
        if self._spec.control == "zcw_hours":
            await self.coordinator.async_set_zcw_hours(value)
            return
        await self.coordinator.async_set_field(self._key, value)

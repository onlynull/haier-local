"""常用开关实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import SWITCHES, SwitchSpec, _display_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        HaierSwitch(coordinators[item.device.key], item) for item in SWITCHES
    )


def _same_switch_value(value: Any, expected: Any) -> bool:
    if value == expected or value is expected:
        return True
    if expected is True or expected is False:
        return False
    try:
        return int(value) == int(expected)
    except (TypeError, ValueError):
        return False


class HaierSwitch(HaierLocalEntity, SwitchEntity):
    def __init__(self, coordinator, spec: SwitchSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key, unique_key=spec.unique_key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def is_on(self) -> bool | None:
        value = self._values().get(self._key)
        if value is None:
            return None
        if value is True and self._spec.on_value is True:
            return True
        return _same_switch_value(value, self._spec.on_value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        values = self._values()
        if self._key == "nightMode":
            return {
                "夜间模式开始时间": values.get("lightModeStartTime"),
                "夜间模式结束时间": values.get("lightModeStopTime"),
            }
        if self._key == "daypartingElectricityStatus":
            return {
                "分时节电开始时间": values.get("sharingElectricityStartTime"),
                "分时节电结束时间": values.get("sharingElectricityEndTime"),
            }
        if self._key == "zeroColdWaterMode":
            return {
                "当前模式": _display_value("zeroColdWaterMode", values.get(self._key)),
                "零冷水状态": values.get("zeroColdWaterStatus"),
            }
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field(self._key, self._spec.on_value)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field(self._key, self._spec.off_value)

"""门、燃烧状态和故障二进制传感器。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .devices import DEVICES
from .entity import HaierLocalEntity, entity_category
from .mappings import BINARY_SENSORS, BinarySpec, alarm_attributes

_DEVICE_CLASS = {
    "door": BinarySensorDeviceClass.DOOR,
    "problem": BinarySensorDeviceClass.PROBLEM,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities: list[BinarySensorEntity] = [
        HaierBinarySensor(coordinators[item.device.key], item) for item in BINARY_SENSORS
    ]
    entities.extend(
        HaierProblemSensor(coordinators[spec.key], spec) for spec in DEVICES
    )
    async_add_entities(entities)


class HaierBinarySensor(HaierLocalEntity, BinarySensorEntity):
    def __init__(self, coordinator, spec: BinarySpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_device_class = _DEVICE_CLASS.get(spec.device_class or "")
        self._attr_entity_category = entity_category(spec.category)

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def is_on(self) -> bool | None:
        value = self._values().get(self._key)
        if value is None:
            return None
        return value == self._spec.on_value or bool(value)


class HaierProblemSensor(HaierLocalEntity, BinarySensorEntity):
    _attr_name = "故障"
    _attr_icon = "mdi:alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = entity_category("diagnostic")

    def __init__(self, coordinator, spec) -> None:
        super().__init__(coordinator, spec, "problem")

    @property
    def is_on(self) -> bool | None:
        values = self._values()
        if "_has_alarm" in values:
            return bool(values.get("_has_alarm"))
        alarms = values.get("_alarms")
        if isinstance(alarms, dict):
            return any(alarms.values())
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return alarm_attributes(self._values())

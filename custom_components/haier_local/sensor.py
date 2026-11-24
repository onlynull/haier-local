"""传感器与诊断属性实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .devices import DEVICES
from .entity import HaierLocalEntity, entity_category
from .mappings import HALF_PIPE_STATUS, SENSORS, SensorSpec, remaining_attributes

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "duration": SensorDeviceClass.DURATION,
    "carbon_monoxide": SensorDeviceClass.CO,
    "power_factor": SensorDeviceClass.POWER_FACTOR,
}

_STATE_CLASS = {
    "measurement": SensorStateClass.MEASUREMENT,
}

_UNITS = {
    "°C": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "min": UnitOfTime.MINUTES,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities: list[SensorEntity] = [
        HaierSensor(coordinators[item.device.key], item) for item in SENSORS
    ]
    entities.extend(
        HaierDetailSensor(coordinators[spec.key], spec) for spec in DEVICES
    )
    async_add_entities(entities)


class HaierSensor(HaierLocalEntity, SensorEntity):
    def __init__(self, coordinator, spec: SensorSpec) -> None:
        super().__init__(coordinator, spec.device, spec.key)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_icon = spec.icon
        self._attr_device_class = _DEVICE_CLASS.get(spec.device_class or "")
        self._attr_state_class = _STATE_CLASS.get(spec.state_class or "")
        self._attr_native_unit_of_measurement = _UNITS.get(spec.unit or "", spec.unit)
        self._attr_entity_category = entity_category(spec.category)
        if spec.precision is not None:
            self._attr_suggested_display_precision = spec.precision

    @property
    def available(self) -> bool:
        return super().available and self._key in self._values()

    @property
    def native_value(self) -> Any:
        value = self._values().get(self._key)
        if self._key == "halfPipeLearningStatus":
            try:
                return HALF_PIPE_STATUS.get(int(value), value)
            except (TypeError, ValueError):
                return value
        return value


class HaierDetailSensor(HaierLocalEntity, SensorEntity):
    """把未单独建实体的字段收进诊断传感器属性。"""

    _attr_icon = "mdi:text-box-outline"
    _attr_name = "详细状态"
    _attr_entity_category = entity_category("diagnostic")

    def __init__(self, coordinator, spec) -> None:
        super().__init__(coordinator, spec, "detail")
        self._device_key = spec.key

    @property
    def native_value(self) -> str:
        extras = remaining_attributes(self._device_key, self._values())
        return f"{len(extras)} 项"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return remaining_attributes(self._device_key, self._values())

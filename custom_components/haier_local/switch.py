"""常用开关实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import HaierLocalEntity, entity_category
from .mappings import (
    SWITCHES,
    SwitchSpec,
    _display_value,
    format_hour_text,
    hours_from_values,
    zero_cold_single_on,
    zero_cold_timing_on,
    zero_cold_water_on,
)


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
        if self._spec.control:
            return super().available
        return super().available and self._key in self._values()

    @property
    def is_on(self) -> bool | None:
        values = self._values()
        control = self._spec.control
        if control == "zcw_single":
            return zero_cold_single_on(values)
        if control == "zcw_water":
            return zero_cold_water_on(values)
        if control == "zcw_timing":
            return zero_cold_timing_on(values)
        value = values.get(self._key)
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
        if self._spec.control in {"zcw_single", "zcw_water", "zcw_timing"}:
            attrs = {
                "当前模式": _display_value("zeroColdWaterMode", values.get("zeroColdWaterMode")),
                "零冷水状态": values.get("zeroColdWaterStatus"),
                "循环泵": values.get("internalCirculationPumpStatus"),
                "安全锁": values.get("safetyLockStatus"),
                "用水时段": format_hour_text(hours_from_values(values)),
            }
            if self._spec.control == "zcw_single":
                attrs["说明"] = "点击后立即预热，仅本次有效"
                attrs["单次时长"] = values.get("singleResnTime")
            elif self._spec.control == "zcw_water":
                attrs["说明"] = "开启水龙头并调向热水侧，2-6秒内关闭即可启动预热"
            else:
                attrs["说明"] = "设定用水时段后，到点自动循环预热"
                attrs["定时循环"] = values.get("zcwTimingCycleStatus")
            return attrs
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._spec.control:
            await self.coordinator.async_set_zero_cold(self._spec.control.replace("zcw_", ""), True)
            return
        await self.coordinator.async_set_field(self._key, self._spec.on_value)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._spec.control:
            await self.coordinator.async_set_zero_cold(self._spec.control.replace("zcw_", ""), False)
            return
        await self.coordinator.async_set_field(self._key, self._spec.off_value)

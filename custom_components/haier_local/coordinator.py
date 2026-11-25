"""Home Assistant 与局域网长连接之间的状态协调器。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DeviceState, HaierClient, HaierError
from .devices import DeviceSpec

_LOGGER = logging.getLogger(__name__)


class HaierLocalCoordinator(DataUpdateCoordinator[DeviceState | None]):
    """把单台设备的本地推送转换成 Home Assistant 状态。"""

    def __init__(self, hass: HomeAssistant, client: HaierClient, spec: DeviceSpec) -> None:
        super().__init__(hass, _LOGGER, name=spec.name)
        self.client = client
        self.spec = spec
        self._remove_api_listener = None
        self._start_task: asyncio.Task | None = None

    async def async_start(self) -> None:
        loop = self.hass.loop

        def receive(state: DeviceState) -> None:
            loop.call_soon_threadsafe(self._receive_in_hass, state)

        self._remove_api_listener = self.client.add_listener(receive)
        self._start_task = self.hass.async_create_task(self._async_connect())

    async def _async_connect(self) -> None:
        delay = 30.0
        while True:
            try:
                await self.client.async_start()
            except HaierError as exc:
                _LOGGER.warning("%s 凭据或连接准备失败，%.0f 秒后重试：%s", self.spec.name, delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300.0)
                continue
            try:
                state = await self.client.async_get_status(timeout=15.0)
            except HaierError as exc:
                _LOGGER.warning("%s 暂时不可达，%.0f 秒后重试：%s", self.spec.name, delay, exc)
                await self.client.async_stop()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300.0)
                continue
            self.async_set_updated_data(state)
            return

    def _receive_in_hass(self, state: DeviceState) -> None:
        self.async_set_updated_data(state)

    def _merge_values(self, updates: dict[str, Any]) -> None:
        state = self.data
        if state is None or not updates:
            return
        values = dict(state.values)
        values.update(updates)
        self.async_set_updated_data(
            DeviceState(
                device_id=state.device_id,
                available=state.available,
                values=values,
                raw=state.raw,
            )
        )

    async def async_set_field(self, name: str, value: Any) -> None:
        await self.client.async_set(name, value)
        self._merge_values({name: value})

    async def async_set_operation(self, name: str, fields: dict[str, Any] | None = None) -> None:
        payload = dict(fields or {})
        await self.client.async_set_operation(name, payload)
        self._merge_values(payload)

    async def async_set_zero_cold(self, action: str, on: bool) -> None:
        values = dict(self.data.values) if self.data else {}
        if action == "single":
            try:
                minutes = int(values.get("singleResnTime") or 0)
            except (TypeError, ValueError):
                minutes = 0
            if minutes <= 0:
                minutes = 20
            await self.async_set_operation(
                "grSetSingleResn",
                {"zeroColdWaterStatus": 1 if on else 0, "singleResnTime": minutes},
            )
            try:
                await self.async_set_field("zeroColdWaterStatus", 1 if on else 0)
            except Exception as exc:
                _LOGGER.debug("单次零冷水状态字段写入失败：%s", exc)
            self._merge_values({"zeroColdWaterStatus": 1 if on else 0, "singleResnTime": minutes})
            return
        if action == "water":
            await self.async_set_field("zeroColdWaterMode", 6 if on else 4)
            self._merge_values({"cycFuncSelect": 1 if on else 0, "zeroColdWaterMode": 6 if on else 4})
            return
        if action == "timing":
            temp = values.get("zeroColdWaterTargetTemp")
            if temp in (None, ""):
                temp = values.get("targetTemp") or 0
            try:
                temp = int(temp)
            except (TypeError, ValueError):
                temp = 0
            await self.async_set_operation(
                "zcwTimingCycle",
                {
                    "zeroColdWaterStatus": 1 if on else 0,
                    "timingCMTargetTemperature": temp,
                    "timingCycleStartDate": 0,
                    "timingCycleStartTime": 0,
                    "timingCycleEndDate": 0,
                    "timingCycleEndTime": 0,
                },
            )
            self._merge_values({"zcwTimingCycleStatus": on, "zeroColdWaterStatus": 1 if on else 0})
            return
        raise ValueError(f"未知零冷水动作: {action}")

    async def async_set_zcw_hours(self, text: str) -> None:
        from .mappings import hour_fields_from_text, parse_hour_text

        fields = hour_fields_from_text(text)
        await self.async_set_operation("grSetCycResnAll", fields)
        selected = set(parse_hour_text(text))
        updates = {
            name: (1 if int(name.rsplit("Hour", 1)[-1]) in selected else 0)
            for name in fields
        }
        self._merge_values(updates)

    async def async_stop(self) -> None:
        if self._remove_api_listener:
            self._remove_api_listener()
            self._remove_api_listener = None
        if self._start_task and not self._start_task.done():
            self._start_task.cancel()
            try:
                await self._start_task
            except asyncio.CancelledError:
                pass
        self._start_task = None
        await self.client.async_stop()

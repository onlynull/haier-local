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
                _LOGGER.warning("%s 暂时不可达，将在后台重连：%s", self.spec.name, exc)
            else:
                self.async_set_updated_data(state)
            return

    def _receive_in_hass(self, state: DeviceState) -> None:
        self.async_set_updated_data(state)

    async def async_set_field(self, name: str, value: Any) -> None:
        await self.client.async_set(name, value)

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

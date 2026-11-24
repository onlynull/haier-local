"""通过局域网 haismart 0x2714 EPP 写指令控制设备。"""

from __future__ import annotations

import asyncio
from typing import Any

from .errors import ControlError, TransportError
from .profile_decoder import HaierProfileDecoder


_TRUE = {True, 1, "1", "true", "on", "开", "开启"}
_FALSE = {False, 0, "0", "false", "off", "关", "关闭"}


class DeviceController:
    """把 profile 字段写入已建立的局域网长连接。"""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._decoder: HaierProfileDecoder | None = None

    def _profile(self) -> HaierProfileDecoder:
        if self._decoder is None:
            self._decoder = HaierProfileDecoder.from_file(self._client.config.profile_path)
        return self._decoder

    def _normalize(self, name: str, value: Any) -> Any:
        definition = self._profile().property_definition(name)
        data_type = definition.get("dataType")
        if data_type == "bool":
            if isinstance(value, str):
                raw = value.strip()
                lowered = raw.lower()
                if lowered in {"1", "true", "on"} or raw in {"开", "开启"}:
                    return True
                if lowered in {"0", "false", "off"} or raw in {"关", "关闭"}:
                    return False
            elif value in _TRUE:
                return True
            elif value in _FALSE:
                return False
        return value

    def set(self, name: str, value: Any, timeout: float = 10.0) -> dict[str, Any]:
        """按 profile 字段名写入；值为 WSS/profile 的 stdValue，不是显示温度。"""
        try:
            normalized = self._normalize(name, value)
            self._profile().encode_epp_write(name, normalized)
        except KeyError as exc:
            raise ControlError(str(exc)) from exc
        except ValueError as exc:
            raise ControlError(str(exc)) from exc
        if not self._client.transport.running:
            raise TransportError("局域网连接未运行，无法发送控制指令")
        return self._client.transport.send_attr_write(name, normalized, timeout=timeout)

    async def async_set(self, name: str, value: Any, timeout: float = 10.0) -> dict[str, Any]:
        return await asyncio.to_thread(self.set, name, value, timeout)

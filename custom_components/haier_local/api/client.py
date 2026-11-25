"""Home Assistant 使用的高层持续连接接口。"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .cache import CacheStore
from .cloud import CloudService
from .config import PACKAGE_DIR, HaierConfig
from .control import DeviceController
from .errors import TransportError
from .models import DeviceState
from .profile import flatten_status
from .transport import LanTransport

StateListener = Callable[[DeviceState], None]


class HaierClient:
    """维护单条长连接，并向调用方提供最新内存状态。"""

    def __init__(self, config: HaierConfig | None = None, *,
                 config_path: str | Path | None = None,
                 cache_path: str | Path | None = None) -> None:
        self.config = config or HaierConfig.load(config_path)
        self.cache = CacheStore(cache_path or PACKAGE_DIR / "data" / "cache.json")
        self.cloud = CloudService(self.config, self.cache)
        self.transport = LanTransport(self.config)
        self.control = DeviceController(self)
        self._last_state: DeviceState | None = None
        self._connection_detail: dict[str, Any] = {}
        self._condition = threading.Condition()
        self._listeners: set[StateListener] = set()
        self._recovery_lock = threading.Lock()
        self._stopping = False

    @property
    def state(self) -> DeviceState | None:
        """立即返回最近状态，不执行网络访问。"""
        with self._condition:
            return self._last_state

    @property
    def running(self) -> bool:
        return self.transport.running

    @property
    def connection_detail(self) -> dict[str, Any]:
        """返回当前连接或恢复阶段，供诊断界面显示。"""
        with self._condition:
            return dict(self._connection_detail)

    def add_listener(self, listener: StateListener) -> Callable[[], None]:
        """注册状态推送回调，并返回取消注册函数。"""
        self._listeners.add(listener)

        def remove() -> None:
            self._listeners.discard(listener)
        return remove

    def start(self) -> None:
        """读取本地凭据并启动持续连接。"""
        if not self.transport.running:
            # profile 是随包资源，缺失时必须立即报告，禁止隐式联网下载。
            self.config.profile_path
            self._stopping = False
            self.transport.start(
                self.cloud.credentials(), self._handle_state, self._handle_connection
            )

    async def async_start(self) -> None:
        await asyncio.to_thread(self.start)

    def stop(self) -> None:
        self._stopping = True
        self.transport.stop()

    async def async_stop(self) -> None:
        await asyncio.to_thread(self.stop)

    def get_status(self, timeout: float = 15.0) -> DeviceState:
        """返回最新状态；尚无状态时等待首个推送。"""
        self.start()
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._last_state is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError(f"等待设备状态超时: {self._connection_detail}")
                self._condition.wait(remaining)
            return self._last_state

    async def async_get_status(self, timeout: float = 15.0) -> DeviceState:
        """返回缓存状态，首次调用会自动启动长连接。"""
        return await asyncio.to_thread(self.get_status, timeout)

    def set(self, name: str, value: Any, timeout: float = 10.0):
        """写入一个 profile 字段，值为协议 stdValue。"""
        return self.control.set(name, value, timeout)

    async def async_set(self, name: str, value: Any, timeout: float = 10.0):
        """异步写入一个 profile 字段。"""
        return await self.control.async_set(name, value, timeout)

    def set_operation(self, name: str, fields: dict[str, Any] | None = None, timeout: float = 10.0):
        """写入一条 profile Operation。"""
        return self.control.set_operation(name, fields, timeout)

    async def async_set_operation(self, name: str, fields: dict[str, Any] | None = None, timeout: float = 10.0):
        """异步写入一条 profile Operation。"""
        return await self.control.async_set_operation(name, fields, timeout)

    async def async_refresh_credentials(self) -> None:
        """刷新凭据后重建连接。"""
        await self.async_stop()
        await asyncio.to_thread(self.cloud.refresh)
        await self.async_start()

    def _handle_state(self, parsed: dict[str, Any]) -> None:
        with self._condition:
            previous = dict(self._last_state.values) if self._last_state else {}
        values = dict(previous)
        kind = parsed.get("kind")
        if kind == "change_status":
            for change in parsed.get("changes") or ():
                name = change.get("name")
                if name:
                    values[str(name)] = change.get("value")
        elif kind == "alarm_bitmap":
            alarm = parsed.get("alarm") or {}
            mapped = alarm.get("profile_alarm_map") or {}
            active = {
                str(item.get("name")): True
                for item in mapped.get("active") or ()
                if item.get("name")
            }
            values["_alarms"] = active
            values["_has_alarm"] = bool(mapped.get("has_alarm") or active)
            if mapped.get("raw_hex"):
                values["_alarm_raw"] = mapped.get("raw_hex")
        else:
            flat = flatten_status(parsed)
            if flat:
                values.update(flat)
        state = DeviceState(
            device_id=self.config.device_id, available=True,
            values=values,
            raw={"connection": self._connection_detail, "parsed": parsed},
        )
        with self._condition:
            self._last_state = state
            self._condition.notify_all()
        for listener in tuple(self._listeners):
            try:
                listener(state)
            except Exception:
                continue

    def _handle_connection(self, connected: bool, detail: dict[str, Any]) -> None:
        unavailable: DeviceState | None = None
        with self._condition:
            self._connection_detail = detail
            if not connected and self._last_state is not None:
                unavailable = DeviceState(
                    device_id=self.config.device_id, available=False,
                    values=self._last_state.values, raw={"connection": detail},
                )
                self._last_state = unavailable
            self._condition.notify_all()
        if unavailable:
            for listener in tuple(self._listeners):
                try:
                    listener(unavailable)
                except Exception:
                    continue
        if detail.get("stage") in {
            "key_version_mismatch", "hello_rejected", "local_key_invalid",
        }:
            threading.Thread(
                target=self._recover_credentials,
                name=f"haier-credential-recovery-{self.config.device_id}",
                daemon=True,
            ).start()

    def _recover_credentials(self) -> None:
        """LocalKey 被设备拒绝时只启动一个云端恢复流程。"""
        if self._stopping or not self._recovery_lock.acquire(blocking=False):
            return
        try:
            self._handle_connection(False, {"stage": "refreshing_credentials"})
            credentials = self.cloud.refresh()
            if self._stopping:
                return
            self.transport.stop()
            self.transport.start(
                credentials, self._handle_state, self._handle_connection
            )
        except Exception as exc:
            self._handle_connection(False, {
                "stage": "credential_refresh_failed",
                "error": str(exc),
            })
        finally:
            self._recovery_lock.release()

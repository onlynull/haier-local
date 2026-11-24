"""局域网持续连接与自动重连。"""

from __future__ import annotations

import queue
import random
import threading
import time
from typing import Any, Callable

from .config import HaierConfig
from .errors import ControlError, TransportError

StateCallback = Callable[[dict[str, Any]], None]
ConnectionCallback = Callable[[bool, dict[str, Any]], None]


class LanTransport:
    """在后台线程中维持唯一连接，并持续接收设备推送。"""

    def __init__(self, config: HaierConfig) -> None:
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._credentials: dict[str, Any] = {}
        self._on_state: StateCallback | None = None
        self._on_connection: ConnectionCallback | None = None
        self._session_received_state = False
        self._failure_count = 0
        self._command_queue: queue.Queue[dict[str, Any]] = queue.Queue()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, credentials: dict[str, Any], on_state: StateCallback,
              on_connection: ConnectionCallback) -> None:
        """启动后台监听；重复调用不会建立第二条连接。"""
        if self.running:
            return
        self._credentials = dict(credentials)
        self._on_state = on_state
        self._on_connection = on_connection
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"haier-lan-{self.config.device_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """通知接收循环退出，并等待 socket 关闭。"""
        self._stop_event.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        if not thread or not thread.is_alive():
            self._thread = None
        self._fail_queued_commands("连接已关闭")

    def send_attr_write(self, name: str, value: str, timeout: float = 10.0) -> dict[str, Any]:
        """在已有长连接上发送一条 EPP 写指令，并等待状态确认。"""
        if not self.running:
            raise TransportError("局域网连接未运行，无法发送控制指令")
        command = {
            "kind": "attr_write",
            "name": name,
            "value": value,
            "done": threading.Event(),
            "result": {},
        }
        self._command_queue.put(command)
        if not command["done"].wait(timeout):
            raise TransportError(f"等待 {name} 控制应答超时")
        result = dict(command.get("result") or {})
        if not result.get("ok"):
            raise ControlError(str(result.get("error") or f"{name} 控制失败"))
        return result

    def _fail_queued_commands(self, reason: str) -> None:
        while True:
            try:
                command = self._command_queue.get_nowait()
            except queue.Empty:
                return
            if not command.get("done") or command["done"].is_set():
                continue
            command["result"] = {"ok": False, "error": reason}
            command["done"].set()

    def _run(self) -> None:
        from . import _legacy_v22 as legacy

        decoder = legacy.HaierProfileDecoder.from_file(self.config.profile_path)
        legacy.set_thread_profile(decoder, self.config.profile_path)
        credentials = self._credentials
        ip = str(credentials.get("device_ip") or self.config.device_ip)
        while not self._stop_event.is_set():
            if not ip:
                self._notify_connection(False, {"stage": "missing_device_ip"})
                return
            session_started = time.monotonic()
            self._session_received_state = False
            try:
                result = legacy.probe_local_56800(
                    ip, self.config.device_id, str(credentials["local_key"]),
                    credentials.get("local_key_version"), port=self.config.port,
                    collect_seconds=365 * 24 * 60 * 60, snapshot_log=None,
                    show_complete_raw=False,
                    heartbeat_interval=self.config.heartbeat_interval,
                    debug_raw=False, coap_read_console=False,
                    stop_event=self._stop_event, on_state=self._notify_state,
                    liveness_timeout=self.config.liveness_timeout,
                    command_queue=self._command_queue,
                )
                if self._stop_event.is_set():
                    break
                if result.get("stage") in {
                    "key_version_mismatch", "hello_rejected", "local_key_invalid",
                }:
                    self._notify_connection(False, result)
                    return
            except Exception as exc:
                result = {
                    "stage": "listener_exception", "error": repr(exc),
                }

            session_age = time.monotonic() - session_started
            if self._session_received_state and session_age >= self.config.stable_connection_seconds:
                self._failure_count = 0
            delay = self._next_retry_delay()
            detail = dict(result)
            detail.update({
                "failure_count": self._failure_count,
                "retry_in": round(delay, 3),
                "session_age": round(session_age, 3),
            })
            self._notify_connection(False, detail)
            self._stop_event.wait(delay)
        self._notify_connection(False, {"stage": "stopped"})

    def _notify_state(self, parsed: dict[str, Any]) -> None:
        self._session_received_state = True
        self._notify_connection(True, {"stage": "connected"})
        if self._on_state:
            self._on_state(parsed)

    def _notify_connection(self, connected: bool, detail: dict[str, Any]) -> None:
        if self._on_connection:
            self._on_connection(connected, detail)

    def _next_retry_delay(self) -> float:
        """计算有上限且带随机抖动的指数退避时间。"""
        base = min(
            self.config.reconnect_initial_delay
            * self.config.reconnect_multiplier ** self._failure_count,
            self.config.reconnect_max_delay,
        )
        self._failure_count += 1
        jitter = self.config.reconnect_jitter
        return max(0.1, base * random.uniform(1.0 - jitter, 1.0 + jitter))

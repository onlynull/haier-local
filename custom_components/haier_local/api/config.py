"""本地配置加载与路径规则。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(slots=True)
class HaierConfig:
    """客户端的稳定配置；通常无需在代码中逐项传参。"""

    device_id: str = ""
    device_ip: str = ""
    port: int = 56800
    profile: str = "haier_profile_2.0.46.json"
    collect_seconds: float = 6.0
    heartbeat_interval: float = 5.0
    liveness_timeout: float = 25.0
    reconnect_initial_delay: float = 2.0
    reconnect_max_delay: float = 300.0
    reconnect_multiplier: float = 2.0
    reconnect_jitter: float = 0.2
    stable_connection_seconds: float = 60.0
    gateway_host: str = "gw.haier.net"
    gateway_ip: str = "101.200.137.150"
    gateway_port: int = 56212
    gateway_insecure_tls: bool = True
    cache_ttl_seconds: int = 86400
    phone: str | None = None
    password: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "HaierConfig":
        """从一个固定 JSON 文件加载，并允许环境变量覆盖账号。"""
        source = Path(path) if path else PACKAGE_DIR / "config.json"
        try:
            data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"无法读取配置文件 {source}: {exc}") from exc
        allowed = {item.name for item in fields(cls)}
        config = cls(**{key: value for key, value in data.items() if key in allowed})
        config.phone = os.getenv("HAIER_PHONE", config.phone)
        config.password = os.getenv("HAIER_PASSWORD", config.password)
        if not config.device_id:
            raise ConfigurationError("config.json 缺少 device_id")
        if config.port <= 0 or config.heartbeat_interval <= 0:
            raise ConfigurationError("端口和心跳间隔必须大于零")
        if config.liveness_timeout <= config.heartbeat_interval:
            raise ConfigurationError("存活超时必须大于心跳间隔")
        if not 0 <= config.reconnect_jitter < 1:
            raise ConfigurationError("重连抖动必须在 0（含）到 1（不含）之间")
        if config.reconnect_initial_delay <= 0 or config.reconnect_max_delay <= 0:
            raise ConfigurationError("重连延时必须大于零")
        if config.reconnect_initial_delay > config.reconnect_max_delay:
            raise ConfigurationError("首次重连延时不能超过最大重连延时")
        if config.reconnect_multiplier < 1:
            raise ConfigurationError("重连倍率不能小于 1")
        return config

    @property
    def profile_path(self) -> Path:
        """优先读取包内 profile，缺失时下载一次并保存。"""
        from .profile_store import ensure_profile

        name = Path(self.profile).name
        return ensure_profile(PACKAGE_DIR / "profiles", name)

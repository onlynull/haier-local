"""与业务层交换的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DeviceState:
    """一次已经完成协议和 profile 解析的设备状态。"""

    device_id: str
    available: bool
    values: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get(self, name: str, default: Any = None) -> Any:
        """按字段名读取值，适合 Home Assistant 实体直接调用。"""
        return self.values.get(name, default)


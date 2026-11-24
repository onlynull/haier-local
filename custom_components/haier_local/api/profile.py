"""本地 profile 初始化与返回值扁平化。"""

from __future__ import annotations

from typing import Any, Mapping


def flatten_status(parsed: Mapping[str, Any]) -> dict[str, Any]:
    """将 v22 的带元数据字段转换为 Home Assistant 易用的普通字典。"""
    status = parsed.get("status")
    if not isinstance(status, Mapping):
        return {}
    fields = status.get("fields", status)
    if not isinstance(fields, Mapping):
        return {}
    result: dict[str, Any] = {}
    for name, item in fields.items():
        if isinstance(item, Mapping):
            result[str(name)] = item.get("value", item.get("raw_value"))
        else:
            result[str(name)] = item
    return result


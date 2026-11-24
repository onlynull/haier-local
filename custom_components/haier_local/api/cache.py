"""鉴权、LocalKey 和设备地址的统一持久化规则。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class CacheStore:
    """使用单个 JSON 文件保存可更新数据，不保存账号密码。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def update(self, **values: Any) -> None:
        data = self.read()
        data.update(values)
        data["updated_at"] = int(time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def fresh(self, seconds: int) -> bool:
        saved = self.read().get("updated_at", 0)
        return bool(saved and time.time() - int(saved) < seconds)


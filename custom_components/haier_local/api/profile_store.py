"""profile 本地缓存与缺失时的一次性下载。"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import requests

from .errors import ConfigurationError

_DOWNLOAD_LOCK = threading.Lock()
_MAX_PROFILE_BYTES = 2 * 1024 * 1024

_PROFILES = {
    "haier_profile_2.0.46.json": {
        "url": "https://resource.haigeek.com/ossdownload/resource/selfService/hardware/ugwfile/200861051c4085040121006180113450000000000000618012854d0000000040_20260724154640578.json",
        "sha256": "2634c8ee4f990df465b8d4f76a567b8976b6749dd8c599c3d235cb7e66e5e290",
    },
    "haier_profile_wh_2.0.0.json": {
        "url": "https://resource.haigeek.com/ossdownload/resource/selfService/hardware/ugwfile/201c120000118674181700418008670000000000000000000000000000000040_20230417192637153.json",
        "sha256": "174dc02e49bdeb88d7398fd0bf0a90dc98cd5d9d276c5f24434745f3772e1447",
    },
}


def ensure_profile(directory: Path, filename: str) -> Path:
    """返回本地文件；仅在缺失时下载并完成完整性校验。"""
    name = Path(filename).name
    target = (directory / name).resolve()
    if target.is_file():
        return target
    metadata = _PROFILES.get(name)
    if metadata is None:
        raise ConfigurationError(f"未知 profile，无法自动下载: {name}")

    with _DOWNLOAD_LOCK:
        if target.is_file():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = requests.get(metadata["url"], timeout=(8, 20))
            response.raise_for_status()
            content = response.content
        except requests.RequestException as exc:
            raise ConfigurationError(f"profile 下载失败: {exc}") from exc
        if not content or len(content) > _MAX_PROFILE_BYTES:
            raise ConfigurationError(f"profile 文件大小异常: {len(content)} 字节")
        actual = hashlib.sha256(content).hexdigest()
        if actual != metadata["sha256"]:
            raise ConfigurationError(
                f"profile 完整性校验失败: 期望 {metadata['sha256']}，实际 {actual}"
            )
        try:
            value = json.loads(content.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ConfigurationError(f"profile 不是有效 JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ConfigurationError("profile 根节点必须是 JSON 对象")

        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        except OSError as exc:
            raise ConfigurationError(f"无法保存 profile: {exc}") from exc
        return target

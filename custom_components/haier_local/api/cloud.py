"""云端刷新策略；业务层只通过此服务获取凭据和设备地址。"""

from __future__ import annotations

from typing import Any

from .cache import CacheStore
from .config import HaierConfig
from .errors import AuthenticationError


class CloudService:
    """优先使用缓存，仅在必要时登录并刷新。"""

    def __init__(self, config: HaierConfig, cache: CacheStore) -> None:
        self.config = config
        self.cache = cache

    def credentials(self) -> dict[str, Any]:
        data = self.cache.read()
        if data.get("local_key"):
            return data
        return self.refresh()

    def refresh(self) -> dict[str, Any]:
        from . import _legacy_v22 as legacy
        session = legacy.requests.Session()
        cached = self.cache.read()
        try:
            client_id, token, devices = self._authenticate(legacy, session, cached)
        except Exception as exc:
            raise AuthenticationError(f"海尔账号鉴权失败: {exc}") from exc
        selected = next((item for item in devices if item.get("deviceId") == self.config.device_id), None)
        ip = self._device_ip(selected or {}) or self.config.device_ip
        result = self._fetch_local_key(legacy, token, client_id)
        values = {
            "client_id": client_id,
            "token": token,
            "local_key": result["key"],
            "local_key_version": result.get("version"),
            "device_ip": ip,
        }
        self.cache.update(**values)
        return self.cache.read()

    def _authenticate(self, legacy: Any, session: Any,
                      cached: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
        """先验证缓存令牌，失效后才使用账号密码重新登录。"""
        client_id = cached.get("client_id")
        token = cached.get("token")
        if client_id and token:
            try:
                devices = legacy.device_list(
                    session, str(token), str(client_id), validate_auth=True
                )
                return str(client_id), str(token), devices
            except PermissionError:
                pass
        if not self.config.phone or not self.config.password:
            raise AuthenticationError("缓存登录令牌已失效，请重新配置海尔智家账号")
        client_id, token = legacy.login(
            session, self.config.phone, self.config.password
        )
        devices = legacy.device_list(
            session, token, client_id, validate_auth=True
        )
        return client_id, token, devices

    def _fetch_local_key(self, legacy: Any, token: str, client_id: str) -> dict[str, Any]:
        _, username, password = legacy.derive_gateway_auth()
        try:
            result = legacy.run_gateway(
                self.config.gateway_host,
                self.config.gateway_port,
                legacy.default_mqtt_client_id(client_id),
                username,
                password,
                token,
                self.config.device_id,
                12.0,
                connect_ip=self.config.gateway_ip,
                insecure_legacy_tls=self.config.gateway_insecure_tls,
            )
        except Exception as exc:
            raise AuthenticationError(f"LocalKey 网关通信失败: {exc}") from exc
        if result.get("stage") != "done" or not result.get("key"):
            raise AuthenticationError(f"无法刷新 LocalKey: {result.get('stage')}")
        return result

    @staticmethod
    def _device_ip(device: dict[str, Any]) -> str:
        for name in ("ip", "deviceIp", "lanIp", "localIp"):
            value = device.get(name)
            if value:
                return str(value)
        return ""

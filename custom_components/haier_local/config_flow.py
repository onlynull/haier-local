"""海尔本地配置流程：登录智家后按型号拉取模块号。"""

from __future__ import annotations

import contextlib
import io
import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api.errors import AuthenticationError, DeviceLookupError
from .const import (
    CONF_FRIDGE_IP,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_WATER_HEATER_IP,
    DOMAIN,
)
from .devices import DEVICES, pick_cloud_device_id

_LOGGER = logging.getLogger(__name__)


def _lan_ip(value: str) -> str:
    text = str(value).strip()
    try:
        address = ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise vol.Invalid("请填写有效的 IPv4 地址") from exc
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise vol.Invalid("请填写设备的局域网 IPv4 地址")
    return text


def _required(key: str, defaults: dict[str, Any]) -> Any:
    value = defaults.get(key)
    if value not in (None, ""):
        return vol.Required(key, default=value)
    return vol.Required(key)


def _schema(defaults: dict[str, Any] | None = None, *, include_account: bool) -> vol.Schema:
    defaults = defaults or {}
    fields: dict[Any, Any] = {}
    if include_account:
        fields[_required(CONF_PHONE, defaults)] = str
        fields[_required(CONF_PASSWORD, defaults)] = str
    fields[_required(CONF_FRIDGE_IP, defaults)] = str
    fields[_required(CONF_WATER_HEATER_IP, defaults)] = str
    return vol.Schema(fields)


def _validate_ips(user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    data = dict(user_input)
    for key in (CONF_FRIDGE_IP, CONF_WATER_HEATER_IP):
        try:
            data[key] = _lan_ip(data[key])
        except vol.Invalid:
            errors[key] = "invalid_ip"
    return data


def _resolve_device_ids(phone: str, password: str) -> dict[str, str]:
    from .api import _legacy_v22 as legacy

    session = legacy.requests.Session()
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            client_id, token = legacy.login(session, phone, password)
        except RuntimeError as exc:
            raise AuthenticationError("账号或密码不正确") from exc
        devices = legacy.device_list(
            session, token, client_id, validate_auth=True, quiet=True
        )
    resolved: dict[str, str] = {}
    for spec in DEVICES:
        resolved[spec.conf_id] = pick_cloud_device_id(spec, devices)
    return resolved


class HaierLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """安装时填写智家账号和两台设备的局域网地址。"""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _validate_ips(user_input, errors)
            if not errors:
                try:
                    device_ids = await self.hass.async_add_executor_job(
                        _resolve_device_ids,
                        user_input[CONF_PHONE],
                        user_input[CONF_PASSWORD],
                    )
                except PermissionError:
                    errors["base"] = "auth"
                except AuthenticationError:
                    errors["base"] = "auth"
                except DeviceLookupError as exc:
                    errors["base"] = f"{exc.spec_key}_not_found"
                except Exception:
                    _LOGGER.exception("海尔智家登录或匹配设备失败")
                    errors["base"] = "cannot_connect"
                else:
                    _LOGGER.debug("已从云端匹配冰箱和热水器模块号")
                    await self.async_set_unique_id(DOMAIN)
                    data = dict(user_input)
                    data.update(device_ids)
                    return self.async_create_entry(title="海尔本地", data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input, include_account=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return HaierLocalOptionsFlow()


class HaierLocalOptionsFlow(config_entries.OptionsFlow):
    """允许稍后更新两台设备的局域网地址。"""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self.config_entry
        if user_input is not None:
            errors: dict[str, str] = {}
            user_input = _validate_ips(user_input, errors)
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_schema({**entry.data, **user_input}, include_account=False),
                    errors=errors,
                )
            data = dict(entry.data)
            data.update(user_input)
            phone = data.get(CONF_PHONE)
            password = data.get(CONF_PASSWORD)
            if phone and password:
                try:
                    device_ids = await self.hass.async_add_executor_job(
                        _resolve_device_ids, phone, password
                    )
                except Exception:
                    _LOGGER.warning("更新局域网地址时未能刷新云端模块号，继续使用已保存的模块号")
                else:
                    data.update(device_ids)
            self.hass.config_entries.async_update_entry(entry, data=data)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(dict(entry.data), include_account=False),
        )

"""海尔本地配置流程：安装时登录智家账号获取 LocalKey。"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api.errors import AuthenticationError
from .const import (
    CONF_FRIDGE_ID,
    CONF_FRIDGE_IP,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_WATER_HEATER_ID,
    CONF_WATER_HEATER_IP,
    DOMAIN,
)
from .devices import normalize_device_id

_LOGGER = logging.getLogger(__name__)


def _device_id(value: str) -> str:
    try:
        return normalize_device_id(value)
    except ValueError as exc:
        raise vol.Invalid(str(exc)) from exc


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_FRIDGE_ID): _device_id,
        vol.Required(CONF_FRIDGE_IP): str,
        vol.Required(CONF_WATER_HEATER_ID): _device_id,
        vol.Required(CONF_WATER_HEATER_IP): str,
    }
)


def _validate_login(phone: str, password: str) -> None:
    import contextlib
    import io

    from .api import _legacy_v22 as legacy

    session = legacy.requests.Session()
    with contextlib.redirect_stdout(io.StringIO()):
        client_id, token = legacy.login(session, phone, password)
        legacy.device_list(session, token, client_id, validate_auth=True)


class HaierLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """安装时填写智家账号和两台设备的模块号、局域网地址。"""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    _validate_login,
                    user_input[CONF_PHONE],
                    user_input[CONF_PASSWORD],
                )
            except PermissionError:
                errors["base"] = "auth"
            except AuthenticationError:
                errors["base"] = "auth"
            except Exception:
                _LOGGER.exception("海尔智家登录失败")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                return self.async_create_entry(title="海尔本地", data=user_input)
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return HaierLocalOptionsFlow()


class HaierLocalOptionsFlow(config_entries.OptionsFlow):
    """允许稍后更新两台设备的模块号和局域网地址。"""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self.config_entry
        if user_input is not None:
            data = dict(entry.data)
            data.update(user_input)
            self.hass.config_entries.async_update_entry(entry, data=data)
            return self.async_create_entry(title="", data={})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FRIDGE_ID,
                    default=entry.data.get(CONF_FRIDGE_ID, ""),
                ): _device_id,
                vol.Required(
                    CONF_FRIDGE_IP,
                    default=entry.data.get(CONF_FRIDGE_IP, ""),
                ): str,
                vol.Required(
                    CONF_WATER_HEATER_ID,
                    default=entry.data.get(CONF_WATER_HEATER_ID, ""),
                ): _device_id,
                vol.Required(
                    CONF_WATER_HEATER_IP,
                    default=entry.data.get(CONF_WATER_HEATER_IP, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

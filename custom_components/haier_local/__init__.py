"""海尔本地控制 Home Assistant 集成。"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import HaierClient, HaierConfig
from .const import (
    CONF_FRIDGE_ID,
    CONF_FRIDGE_IP,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_WATER_HEATER_ID,
    CONF_WATER_HEATER_IP,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HaierLocalCoordinator
from .devices import DEVICES


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    required = (
        CONF_PHONE,
        CONF_PASSWORD,
        CONF_FRIDGE_ID,
        CONF_FRIDGE_IP,
        CONF_WATER_HEATER_ID,
        CONF_WATER_HEATER_IP,
    )
    if any(key not in entry.data for key in required):
        return False
    hass.data.setdefault(DOMAIN, {})
    coordinators: dict[str, HaierLocalCoordinator] = {}
    for spec in DEVICES:
        api_config = HaierConfig(
            device_id=entry.data[spec.conf_id],
            device_ip=entry.data[spec.conf_ip],
            profile=spec.profile,
            phone=entry.data[CONF_PHONE],
            password=entry.data[CONF_PASSWORD],
        )
        cache_path = hass.config.path(".storage", DOMAIN, f"{spec.key}.json")
        client = HaierClient(api_config, cache_path=cache_path)
        coordinator = HaierLocalCoordinator(hass, client, spec)
        coordinators[spec.key] = coordinator
        await coordinator.async_start()

    hass.data[DOMAIN][entry.entry_id] = {"coordinators": coordinators}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = hass.data[DOMAIN].pop(entry.entry_id)
    for coordinator in runtime["coordinators"].values():
        await coordinator.async_stop()
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

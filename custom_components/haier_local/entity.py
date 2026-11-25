"""海尔本地实体公共实现。"""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HaierLocalCoordinator
from .devices import DeviceSpec, format_mac


def entity_category(value: str | None) -> EntityCategory | None:
    if value == "config":
        return EntityCategory.CONFIG
    if value == "diagnostic":
        return EntityCategory.DIAGNOSTIC
    return None


class HaierLocalEntity(CoordinatorEntity[HaierLocalCoordinator]):
    """共享设备身份、可用性和唯一标识。"""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HaierLocalCoordinator,
        spec: DeviceSpec,
        key: str,
        unique_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._spec = spec
        device_id = coordinator.client.config.device_id
        self._attr_unique_id = f"{device_id}_{unique_key or key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(device_id))},
            name=spec.name,
            manufacturer=spec.manufacturer,
            model=spec.model,
            serial_number=device_id,
            hw_version=spec.hw_version,
            sw_version=spec.sw_version,
        )

    @property
    def available(self) -> bool:
        state = self.coordinator.data
        return bool(state and state.available)

    def _values(self) -> dict:
        state = self.coordinator.data
        if state is None:
            return {}
        return dict(state.values)

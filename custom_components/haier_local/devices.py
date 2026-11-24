"""固定接入的两台设备类型。模块号登录后按型号从云端匹配。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import (
    CONF_FRIDGE_ID,
    CONF_FRIDGE_IP,
    CONF_WATER_HEATER_ID,
    CONF_WATER_HEATER_IP,
    MANUFACTURER_CASARTE,
    MANUFACTURER_HAIER,
)


@dataclass(frozen=True, slots=True)
class DeviceSpec:
    """一台设备的产品信息和配置项名称。"""

    key: str
    conf_ip: str
    conf_id: str
    name: str
    manufacturer: str
    model: str
    hw_version: str
    sw_version: str
    profile: str
    icon: str


FRIDGE = DeviceSpec(
    key="fridge",
    conf_ip=CONF_FRIDGE_IP,
    conf_id=CONF_FRIDGE_ID,
    name="卡萨帝 501升十字对开门冰箱",
    manufacturer=MANUFACTURER_CASARTE,
    model="BCD-501WGCTDM4SSU1",
    hw_version="BC12L1000",
    sw_version="2.0.46",
    profile="haier_profile_2.0.46.json",
    icon="mdi:fridge-outline",
)

WATER_HEATER = DeviceSpec(
    key="water_heater",
    conf_ip=CONF_WATER_HEATER_IP,
    conf_id=CONF_WATER_HEATER_ID,
    name="云溪 16升双循环恒温燃气热水器",
    manufacturer=MANUFACTURER_HAIER,
    model="JSQ31-16KN7SFRAGU1",
    hw_version="GD0RAY004",
    sw_version="2.0.0",
    profile="haier_profile_wh_2.0.0.json",
    icon="mdi:water-boiler",
)

DEVICES = (FRIDGE, WATER_HEATER)
DEVICE_BY_KEY = {item.key: item for item in DEVICES}


def format_mac(device_id: str) -> str:
    """把 12 位 deviceId 格式化成 MAC。"""
    text = device_id.strip().lower().replace(":", "")
    if len(text) != 12:
        return device_id
    return ":".join(text[index:index + 2] for index in range(0, 12, 2))


def normalize_device_id(value: str) -> str:
    """安装配置里的模块号：12 位十六进制。"""
    text = str(value).strip().replace(":", "").replace("-", "").upper()
    if len(text) != 12 or any(char not in "0123456789ABCDEF" for char in text):
        raise ValueError("设备模块号应为 12 位十六进制")
    return text


def _cloud_text(value: Any) -> str:
    return str(value or "").strip().upper()


def cloud_device_matches(spec: DeviceSpec, device: Mapping[str, Any]) -> bool:
    """用官方型号或硬件型号匹配云端 deviceinfos 条目。"""
    model = spec.model.upper()
    hardware = spec.hw_version.upper()
    product_name = _cloud_text(device.get("productNameT"))
    product_code = _cloud_text(device.get("productCodeT"))
    wifi_type = _cloud_text(device.get("wifiType"))
    device_name = _cloud_text(device.get("deviceName"))
    identity = {product_name, product_code, wifi_type}
    return (
        model in identity
        or hardware in identity
        or model in product_name
        or model in device_name
        or hardware in product_name
    )


def pick_cloud_device_id(spec: DeviceSpec, devices: list[Mapping[str, Any]]) -> str:
    """从账号设备列表取出该产品的模块号；多台时优先在线设备。"""
    matches = [item for item in devices if cloud_device_matches(spec, item)]
    if not matches:
        from .api.errors import DeviceLookupError

        raise DeviceLookupError(spec.key)
    online = [item for item in matches if item.get("online")]
    chosen = (online or matches)[0]
    try:
        return normalize_device_id(str(chosen.get("deviceId") or ""))
    except ValueError as exc:
        from .api.errors import DeviceLookupError

        raise DeviceLookupError(spec.key) from exc

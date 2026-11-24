"""包内统一异常。"""


class HaierError(Exception):
    """所有海尔客户端异常的基类。"""


class ConfigurationError(HaierError):
    """本地配置无效。"""


class AuthenticationError(HaierError):
    """云端鉴权失败。"""


class DeviceLookupError(HaierError):
    """账号设备列表中找不到固定接入的产品。"""

    def __init__(self, spec_key: str) -> None:
        super().__init__(spec_key)
        self.spec_key = spec_key


class TransportError(HaierError):
    """局域网通信失败。"""


class ControlError(HaierError):
    """设备拒绝或无法完成控制指令。"""


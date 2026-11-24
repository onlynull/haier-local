"""协议层命名空间。

局域网状态推送仍由 transport 适配已验证的 v22 uSS/UWT 实现。
属性写入走 haismart 出站信封：CAE type 0x2714 + OLD-EPP 5Dxx，biz_sn 取自 HELLO_DONE_RESP。
"""

from .coap import build_cae_attr_write_coap, parse_coap_message
from .epp import build_cae_op_request, build_old_epp_frame, wrap_cae_epp_envelope

__all__ = [
    "build_cae_attr_write_coap",
    "build_cae_op_request",
    "build_old_epp_frame",
    "parse_coap_message",
    "wrap_cae_epp_envelope",
]


"""CAE/CoAP 属性读写组帧。

从 liball-in-one.so 的 cae_lc_enc_write_attr_shared（0x2d3cb8）还原：

- 读：CON GET  /cae/dev/<devId>/attr/r/?name=<name>
- 写：CON PUT  /cae/dev/<devId>/attr/w
      payload = {"devId":"...","name":"...","value":"..."}
- msgtype=0（CON），写指令 cmethod=3（PUT）
"""

from __future__ import annotations

import json
import struct
from typing import Any


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _coap_uint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative CoAP uint")
    if value == 0:
        return b""
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def _coap_option_header(delta: int, length: int) -> bytes:
    def nibble(v: int) -> tuple[int, bytes]:
        if v <= 12:
            return v, b""
        if v <= 268:
            return 13, bytes([v - 13])
        if v <= 65804:
            return 14, struct.pack(">H", v - 269)
        raise ValueError("CoAP option delta/length too large")

    dn, de = nibble(delta)
    ln, le = nibble(length)
    return bytes([(dn << 4) | ln]) + de + le


def encode_coap_options(options: list[tuple[int, bytes]]) -> bytes:
    out = bytearray()
    previous = 0
    for number, value in sorted(options, key=lambda item: item[0]):
        value = bytes(value)
        delta = int(number) - previous
        if delta < 0:
            raise ValueError("CoAP options not monotonic")
        out += _coap_option_header(delta, len(value))
        out += value
        previous = int(number)
    return bytes(out)


def build_coap_request(
    *,
    method: int,
    message_id: int,
    token: bytes,
    uri_port: int,
    path_segments,
    query: str | None = None,
    payload: bytes = b"",
) -> bytes:
    """RFC7252 CON PDU，与 SDK libcoap 路径一致。"""
    token = bytes(token)
    if len(token) > 8:
        raise ValueError("CoAP token > 8 bytes")
    if not 0 <= message_id <= 0xFFFF:
        raise ValueError("invalid CoAP message id")
    header = bytes([0x40 | len(token), method & 0xFF]) + struct.pack(">H", message_id)
    options: list[tuple[int, bytes]] = []
    if int(uri_port) != 5683:
        options.append((7, _coap_uint(int(uri_port))))
    for seg in path_segments:
        if seg != "":
            options.append((11, str(seg).encode("utf-8")))
    if query:
        options.append((15, str(query).encode("utf-8")))
    wire = header + token + encode_coap_options(options)
    if payload:
        wire += b"\xff" + bytes(payload)
    return wire


def parse_coap_message(data: bytes) -> dict[str, Any] | None:
    if len(data) < 4:
        return None
    first = data[0]
    if (first >> 6) != 1:
        return None
    typ = (first >> 4) & 0x03
    tkl = first & 0x0F
    if tkl > 8 or len(data) < 4 + tkl:
        return None
    code = data[1]
    mid = struct.unpack(">H", data[2:4])[0]
    token = data[4:4 + tkl]
    pos = 4 + tkl
    current = 0
    options: list[tuple[int, bytes]] = []

    def ext(nib: int, p: int) -> tuple[int, int]:
        if nib <= 12:
            return nib, p
        if nib == 13:
            if p >= len(data):
                raise ValueError
            return 13 + data[p], p + 1
        if nib == 14:
            if p + 2 > len(data):
                raise ValueError
            return 269 + struct.unpack(">H", data[p:p + 2])[0], p + 2
        raise ValueError

    try:
        while pos < len(data):
            if data[pos] == 0xFF:
                pos += 1
                break
            b = data[pos]
            pos += 1
            delta, pos = ext(b >> 4, pos)
            ln, pos = ext(b & 0x0F, pos)
            current += delta
            if pos + ln > len(data):
                return None
            value = data[pos:pos + ln]
            pos += ln
            options.append((current, value))
    except ValueError:
        return None
    return {
        "version": 1,
        "type": typ,
        "code": code,
        "code_class": code >> 5,
        "code_detail": code & 0x1F,
        "message_id": mid,
        "token": token,
        "options": options,
        "payload": data[pos:],
    }


def build_cae_attr_write_coap(
    device_id: str,
    attr_name: str,
    attr_value: str,
    *,
    local_port: int = 56800,
    token_seed: int = 10002,
    message_id: int = 1,
) -> tuple[bytes, dict[str, Any]]:
    """组一帧 SDK 本地写属性 CoAP PUT。"""
    token = str(int(token_seed)).encode("ascii")
    body = compact_json({
        "devId": str(device_id),
        "name": str(attr_name),
        "value": str(attr_value),
    }).encode("utf-8")
    pdu = build_coap_request(
        method=3,
        message_id=message_id,
        token=token,
        uri_port=local_port,
        path_segments=["cae", "dev", device_id, "attr", "w"],
        payload=body,
    )
    return pdu, {
        "attr": attr_name,
        "value": str(attr_value),
        "token": token.decode(),
        "message_id": message_id,
        "local_port": local_port,
        "path": f"/cae/dev/{device_id}/attr/w",
        "payload": body.decode("utf-8"),
    }

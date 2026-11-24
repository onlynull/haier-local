"""OLD-EPP 写帧与 CAE 信封。

入站状态推送是 type 0x2715 的 80 字节报告信封。
出站控制是 type 0x2714 的请求信封（enapt/haismart-local 在 SE-Asia 热水器 5D01 上确认）。
"""

from __future__ import annotations

import struct

CAE_OP_TYPE_REQUEST = 0x2714
CAE_OP_TYPE_REPORT = 0x2715
_SEPARATOR_BYTE = 0xFF
_SEPARATOR_POST_BYTE = 0x55


def build_old_epp_frame(frame_type: int, epp_cmd: str, data: bytes = b"") -> bytes:
    """FF FF | len | 00*6 | frameType | cmd(2) | data | checksum。"""
    cmd = bytes.fromhex(epp_cmd)
    if len(cmd) != 2:
        raise ValueError(f"EPP command must be 2 bytes, got {epp_cmd!r}")
    body = b"\x00" * 6 + bytes([frame_type & 0xFF]) + cmd + bytes(data)
    declared_len = len(body) + 1
    if declared_len > 0xFF:
        raise ValueError("OLD-EPP frame too large")
    wire = b"\xff\xff" + bytes([declared_len]) + body
    return wire + bytes([sum(wire[2:]) & 0xFF])


def stuff_epp(frame: bytes) -> bytes:
    """帧内 0xFF 转义为 FF 55；开头两个分隔字节不转义。"""
    frame = bytes(frame)
    if not frame.startswith(b"\xff\xff"):
        return frame
    out = bytearray(b"\xff\xff")
    for byte in frame[2:]:
        out.append(byte)
        if byte == _SEPARATOR_BYTE:
            out.append(_SEPARATOR_POST_BYTE)
    return bytes(out)


def wrap_cae_epp_envelope(epp_frame: bytes) -> bytes:
    """入站报告信封：80 字节 CAE 头 + EPP。头字段来自本机 6D01/0F5A 实测。"""
    epp_frame = bytes(epp_frame)
    if len(epp_frame) > 0xFF:
        raise ValueError("embedded EPP frame too large")
    hdr = bytearray(80)
    hdr[0:4] = bytes.fromhex("00002715")
    hdr[8:16] = bytes.fromhex("4e56010000030200")
    hdr[16:20] = bytes.fromhex("00040100")
    hdr[79] = len(epp_frame) & 0xFF
    return bytes(hdr) + epp_frame


def build_cae_op_request(epp_frame: bytes, device_id: str, counter: int) -> bytes:
    """出站控制信封：0x2714 + deviceId + counter + BE32 长度 + EPP。

    Layout::

        00 00 27 14 | 36 zero bytes | deviceId ASCII 右填充 32 字节
                    | counter(BE32) | len(epp)(BE32) | stuffed epp
    """
    did = str(device_id).encode("ascii")
    if len(did) > 32:
        raise ValueError("device_id too long for the 32-byte field")
    field = did + b"\x00" * (32 - len(did))
    wire = stuff_epp(bytes(epp_frame))
    return (
        struct.pack(">I", CAE_OP_TYPE_REQUEST)
        + b"\x00" * 36
        + field
        + struct.pack(">II", int(counter) & 0xFFFFFFFF, len(wire))
        + wire
    )

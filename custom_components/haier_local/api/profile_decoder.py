# ���� profile ��������
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

@dataclass
class DecodedField:
    name: str
    value: Any = None
    raw_value: Any = None
    raw_bytes: bytes = b''
    available: bool = True
    data_type: Optional[str] = None
    cae_type: Optional[int] = None
    status_cmd: Optional[str] = None
    start_word: Optional[int] = None
    start_bit: Optional[int] = None
    length: Optional[int] = None
    byte_offsets: List[int] = field(default_factory=list)
    unit: Optional[str] = None
    writable: Optional[bool] = None
    epp_cmd: Optional[str] = None
    note: Optional[str] = None
    definition: Dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> Dict[str, Any]:
        return {'name': self.name, 'value': self.value, 'raw_value': self.raw_value, 'raw_hex': self.raw_bytes.hex(), 'available': self.available, 'data_type': self.data_type, 'cae_type': self.cae_type, 'status_cmd': self.status_cmd, 'start_word': self.start_word, 'start_bit': self.start_bit, 'length': self.length, 'byte_offsets': self.byte_offsets, 'unit': self.unit, 'writable': self.writable, 'epp_cmd': self.epp_cmd, 'note': self.note}

@dataclass
class ProfileDecodedData:
    command: str
    raw_data: bytes
    fields: Dict[str, DecodedField]
    profile_version: Optional[str] = None
    profile_name: Optional[str] = None
    section_names: Tuple[str, ...] = ()

    def __getattr__(self, name: str) -> Any:
        f = self.fields.get(name)
        if f is None:
            raise AttributeError(name)
        return f.value

    def __getitem__(self, name: str) -> Any:
        return self.fields[name].value

    def __contains__(self, name: str) -> bool:
        return name in self.fields

    def field(self, name: str) -> Optional[DecodedField]:
        return self.fields.get(name)

    def values(self, include_unavailable: bool=False) -> Dict[str, Any]:
        return {name: f.value for name, f in self.fields.items() if include_unavailable or f.available}

    def as_dict(self, include_unavailable: bool=False, metadata: bool=False) -> Dict[str, Any]:
        selected = {name: f.as_dict() if metadata else f.value for name, f in self.fields.items() if include_unavailable or f.available}
        return {'command': self.command, 'profile_version': self.profile_version, 'profile_name': self.profile_name, 'raw_data_len': len(self.raw_data), 'raw_data_hex': self.raw_data.hex(), 'sections': list(self.section_names), 'fields': selected}

class HaierProfileDecoder:
    STATUS_SECTIONS = ('Property', 'Bigdata')

    def __init__(self, profile: Mapping[str, Any], source: Optional[str]=None):
        self.profile: Dict[str, Any] = dict(profile)
        self.source = source
        self.version = self.profile.get('Version')
        basic = self.profile.get('BasicInfo') or {}
        self.profile_name = basic.get('name')
        self.device_type = basic.get('deviceType')
        self._by_cmd: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for section in self.STATUS_SECTIONS:
            for definition in self.profile.get(section, []) or []:
                cmd = str(definition.get('statusCmd') or '').upper()
                if not cmd:
                    continue
                self._by_cmd.setdefault(cmd, []).append((section, definition))
        self.operations = {x.get('name'): x for x in self.profile.get('Operation') or [] if x.get('name')}
        self.change_parameters = {x.get('name'): x for x in self.profile.get('changeParas') or [] if x.get('name')}
        self.alarms = list(self.profile.get('Alarm') or [])
        self.properties = {x.get('name'): x for x in self.profile.get('Property') or [] if x.get('name')}

    @classmethod
    def from_file(cls, path: str | Path) -> 'HaierProfileDecoder':
        p = Path(path)
        with p.open('r', encoding='utf-8') as fh:
            profile = json.load(fh)
        return cls(profile, source=str(p))

    @classmethod
    def from_json(cls, text: str) -> 'HaierProfileDecoder':
        return cls(json.loads(text))

    def supports_command(self, command: str) -> bool:
        return str(command).upper() in self._by_cmd

    def definitions_for_command(self, command: str) -> List[Dict[str, Any]]:
        return [d for _section, d in self._by_cmd.get(str(command).upper(), [])]

    def decode_status(self, command: str, data: bytes) -> ProfileDecodedData:
        cmd = str(command).upper()
        defs = self._by_cmd.get(cmd, [])
        fields: Dict[str, DecodedField] = {}
        sections: List[str] = []
        for section, definition in defs:
            if section not in sections:
                sections.append(section)
            decoded = self._decode_definition(cmd, data, definition)
            fields[decoded.name] = decoded
        return ProfileDecodedData(command=cmd, raw_data=bytes(data), fields=fields, profile_version=self.version, profile_name=self.profile_name, section_names=tuple(sections))

    def decode_to_dict(self, command: str, data: bytes, *, metadata: bool=False) -> Dict[str, Any]:
        return self.decode_status(command, data).as_dict(metadata=metadata)

    @staticmethod
    def _word_base(start_word: int) -> int:
        return (int(start_word) - 1) * 2

    @classmethod
    def _byte_aligned_location(cls, definition: Mapping[str, Any]) -> Tuple[int, int, int]:
        sw = int(definition.get('startWord') or 1)
        sb = int(definition.get('startBit') or 0)
        ln = int(definition.get('length') or 0)
        base = cls._word_base(sw)
        if ln > 8:
            start_byte = base
            bit_in_byte = 0
            byte_len = math.ceil(ln / 8)
            return (start_byte, bit_in_byte, byte_len)
        if sb >= 8:
            return (base, sb - 8, max(1, math.ceil((sb - 8 + ln) / 8)))
        return (base + 1, sb, max(1, math.ceil((sb + ln) / 8)))

    @classmethod
    def _extract_raw(cls, data: bytes, definition: Mapping[str, Any]) -> Tuple[bool, Any, bytes, List[int], Optional[str]]:
        sw = definition.get('startWord')
        sb = definition.get('startBit')
        ln = definition.get('length')
        if sw is None or sb is None or ln is None:
            return (False, None, b'', [], 'profile field has no startWord/startBit/length')
        sw, sb, ln = (int(sw), int(sb), int(ln))
        if ln <= 0:
            return (False, None, b'', [], 'profile field has invalid length')
        start_byte, bit_in_byte, byte_len = cls._byte_aligned_location(definition)
        if start_byte < 0 or start_byte + byte_len > len(data):
            offsets = list(range(start_byte, start_byte + byte_len)) if start_byte >= 0 else []
            return (False, None, b'', offsets, f'payload too short ({len(data)}B)')
        raw_bytes = data[start_byte:start_byte + byte_len]
        offsets = list(range(start_byte, start_byte + byte_len))
        if ln <= 8:
            raw_int = int.from_bytes(raw_bytes, 'big')
            raw_int = raw_int >> bit_in_byte & (1 << ln) - 1
            return (True, raw_int, raw_bytes, offsets, None)
        cae_type = definition.get('caeType')
        if sb == 8 and cae_type in (1, 6):
            endian = 'little'
            note = 'multi-byte scalar decoded little-endian because startBit=8'
        else:
            endian = 'big'
            note = None
        raw_int = int.from_bytes(raw_bytes, endian)
        if ln % 8:
            raw_int &= (1 << ln) - 1
        return (True, raw_int, raw_bytes, offsets, note)

    def _decode_definition(self, command: str, data: bytes, definition: Mapping[str, Any]) -> DecodedField:
        name = str(definition.get('name') or 'unnamed')
        ok, raw, raw_bytes, offsets, note = self._extract_raw(data, definition)
        variants = definition.get('variants')
        dtype = definition.get('dataType')
        unit = None
        if isinstance(variants, dict):
            unit = variants.get('unit')
        out = DecodedField(name=name, raw_value=raw, raw_bytes=raw_bytes, available=ok, data_type=dtype, cae_type=definition.get('caeType'), status_cmd=command, start_word=definition.get('startWord'), start_bit=definition.get('startBit'), length=definition.get('length'), byte_offsets=offsets, unit=unit, writable=definition.get('writable'), epp_cmd=definition.get('eppCmd'), note=note, definition=dict(definition))
        if not ok:
            out.note = note
            return out
        if dtype == 'string' and isinstance(variants, list):
            parts: List[Any] = []
            part_raw: List[int] = []
            for sub in variants:
                sok, sraw, _sbytes, _soffsets, _snote = self._extract_raw(data, sub)
                if not sok:
                    out.available = False
                    out.value = None
                    out.note = 'composite field payload too short'
                    return out
                part_raw.append(int(sraw))
                parts.append(int(sraw))
            out.raw_value = part_raw
            if len(parts) == 2 and all((isinstance(x, int) for x in parts)):
                out.value = f'{parts[0]:02d}:{parts[1]:02d}'
            else:
                out.value = parts
            return out
        if isinstance(variants, list):
            mapped = None
            found = False
            for v in variants:
                if v.get('eppValue') == raw:
                    mapped = v.get('stdValue')
                    found = True
                    break
            out.value = mapped if found else raw
            if not found:
                extra = f'raw value {raw!r} absent from variants'
                out.note = f'{out.note}; {extra}' if out.note else extra
            return out
        if isinstance(variants, dict):
            k = variants.get('k', 1)
            c = variants.get('c', 0)
            try:
                out.value = raw * k + c
                if dtype == 'int' and isinstance(out.value, float) and out.value.is_integer():
                    out.value = int(out.value)
            except Exception:
                out.value = raw
                extra = 'failed to apply k/c transform'
                out.note = f'{out.note}; {extra}' if out.note else extra
            return out
        if dtype == 'bool':
            out.value = bool(raw)
        else:
            out.value = raw
        return out

    def property_definition(self, name: str) -> Dict[str, Any]:
        definition = self.properties.get(name)
        if definition is None:
            raise KeyError(f'profile 中没有属性 {name}')
        return definition

    def encode_write_value(self, name: str, std_value: Any) -> str:
        """把业务层 std 值编码成 SDK attr/w JSON 字符串。"""
        definition = self.property_definition(name)
        if not definition.get('writable'):
            raise ValueError(f'{name} 不可写')
        variants = definition.get('variants')
        data_type = definition.get('dataType')
        if data_type == 'string':
            if isinstance(std_value, (list, tuple)) and len(std_value) == 2:
                return f'{int(std_value[0]):02d}:{int(std_value[1]):02d}'
            text = str(std_value).strip()
            if not text:
                raise ValueError(f'{name} 字符串值不能为空')
            return text
        if isinstance(variants, list):
            matched = None
            for item in variants:
                sv = item.get('stdValue')
                if sv is std_value or sv == std_value:
                    matched = sv
                    break
                if isinstance(sv, bool) or isinstance(std_value, bool):
                    continue
                try:
                    if int(sv) == int(std_value):
                        matched = sv
                        break
                except (TypeError, ValueError):
                    continue
            if matched is None:
                allowed = [item.get('stdValue') for item in variants]
                raise ValueError(f'{name} 不允许值 {std_value!r}，可选 {allowed}')
            if isinstance(matched, bool):
                return 'true' if matched else 'false'
            return str(matched)
        if isinstance(variants, dict):
            try:
                number = float(std_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{name} 需要数值，得到 {std_value!r}') from exc
            minimum = variants.get('minValue')
            maximum = variants.get('maxValue')
            if minimum is not None and number < float(minimum):
                raise ValueError(f'{name} 低于最小值 {minimum}')
            if maximum is not None and number > float(maximum):
                raise ValueError(f'{name} 高于最大值 {maximum}')
            if data_type == 'int' or number.is_integer():
                return str(int(number))
            return str(number)
        if data_type == 'bool':
            return 'true' if bool(std_value) else 'false'
        return str(std_value)

    def encode_epp_write(self, name: str, std_value: Any) -> Dict[str, Any]:
        """把 std 值编成可发送的 OLD-EPP 参数。"""
        definition = self.property_definition(name)
        if not definition.get('writable'):
            raise ValueError(f'{name} 不可写')
        cmd = definition.get('eppCmd')
        frame_type = definition.get('frameType')
        param_len = definition.get('paramLen')
        if not cmd or frame_type is None or param_len is None:
            raise ValueError(f'{name} 缺少 eppCmd/frameType/paramLen，无法局域网写入')
        text = self.encode_write_value(name, std_value)
        variants = definition.get('variants')
        epp_value: Any = None
        if isinstance(variants, list):
            target: Any
            if text in ('true', 'false'):
                target = text == 'true'
            else:
                try:
                    target = int(text)
                except ValueError:
                    target = text
            for item in variants:
                sv = item.get('stdValue')
                if sv == target or sv is target:
                    epp_value = item.get('eppValue')
                    break
                try:
                    if not isinstance(sv, bool) and not isinstance(target, bool) and int(sv) == int(target):
                        epp_value = item.get('eppValue')
                        break
                except (TypeError, ValueError):
                    continue
            if epp_value is None:
                try:
                    epp_value = int(std_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'{name} 无法映射 EPP 值 {std_value!r}') from exc
        else:
            if text in ('true', 'false'):
                epp_value = 1 if text == 'true' else 0
            else:
                epp_value = int(text)
        if isinstance(epp_value, bool):
            epp_value = int(epp_value)
        epp_value = int(epp_value)
        width = int(param_len)
        if epp_value < 0 or epp_value >= (1 << (8 * width)):
            raise ValueError(f'{name} EPP 值 {epp_value} 超出 paramLen={width}')
        return {
            'name': name,
            'std_value': std_value,
            'epp_value': epp_value,
            'epp_cmd': str(cmd).upper(),
            'frame_type': int(frame_type),
            'param': epp_value.to_bytes(width, 'big'),
        }

    @staticmethod
    def _operation_int(value: Any) -> int:
        if value is True or value is False:
            return int(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {'true', 'on', '1'} or value.strip() in {'开', '开启'}:
                return 1
            if text in {'false', 'off', '0'} or value.strip() in {'关', '关闭'}:
                return 0
        return int(value)

    def encode_operation(self, name: str, fields: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        """把 Operation 多字段编成 frameType 96 的 OLD-EPP 参数。"""
        operation = self.operations.get(name)
        if operation is None:
            raise KeyError(f'profile 中没有操作 {name}')
        cmd = operation.get('eppCmd')
        frame_type = operation.get('frameType')
        if not cmd or frame_type is None:
            raise ValueError(f'{name} 缺少 eppCmd/frameType，无法局域网写入')
        variants = operation.get('variants') or []
        if not variants:
            raise ValueError(f'{name} 没有可编码字段')
        payload_fields = dict(fields or {})
        size = 0
        packed: List[Tuple[Dict[str, Any], int, int, int, int]] = []
        for variant in variants:
            field_name = variant.get('name')
            if not field_name:
                continue
            raw_value = self._operation_int(payload_fields[field_name]) if field_name in payload_fields else 0
            start_byte, bit_in_byte, byte_len = self._byte_aligned_location(variant)
            size = max(size, start_byte + byte_len)
            packed.append((variant, raw_value, start_byte, bit_in_byte, byte_len))
        buf = bytearray(size)
        for variant, raw_value, start_byte, bit_in_byte, byte_len in packed:
            length = int(variant.get('length') or 0)
            if length <= 0 or byte_len <= 0:
                continue
            mask = (1 << length) - 1
            value = int(raw_value) & mask
            if length <= 8:
                current = int.from_bytes(buf[start_byte:start_byte + byte_len], 'big')
                current &= ~(mask << bit_in_byte)
                current |= value << bit_in_byte
                buf[start_byte:start_byte + byte_len] = current.to_bytes(byte_len, 'big')
            else:
                buf[start_byte:start_byte + byte_len] = value.to_bytes(byte_len, 'big')
        return {
            'name': name,
            'epp_cmd': str(cmd).upper(),
            'frame_type': int(frame_type),
            'param': bytes(buf),
            'fields': payload_fields,
        }

    def decode_alarm_bitmap(self, data: bytes) -> Dict[str, Any]:
        value = int.from_bytes(data, 'big') if data else 0
        active_positions = [i for i in range(len(data) * 8) if value >> i & 1]
        names_by_pos = {int(x.get('pos')): x for x in self.alarms if x.get('pos') is not None}
        active = []
        for pos in active_positions:
            item = names_by_pos.get(pos)
            active.append({'pos': pos, 'name': item.get('name') if item else None, 'description': item.get('description') if item else None})
        return {'raw_hex': data.hex(), 'has_alarm': bool(value), 'active_positions': active_positions, 'active': active}

def choose_profile_file(explicit: Optional[str]=None, *, base_dir: Optional[str | Path]=None) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    roots = []
    if base_dir:
        roots.append(Path(base_dir))
    roots.extend([Path.cwd(), Path(__file__).resolve().parent])
    seen = set()
    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            pass
        if str(root) in seen:
            continue
        seen.add(str(root))
        preferred = root / 'haier_profile_2.0.46.json'
        if preferred.is_file():
            return preferred
    candidates: List[Tuple[Tuple[int, ...], Path]] = []
    for root_s in seen:
        root = Path(root_s)
        for p in root.glob('haier_profile_*.json'):
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
                version = str(d.get('Version') or '0')
                key = tuple((int(x) for x in version.split('.') if x.isdigit()))
                candidates.append((key, p))
            except Exception:
                continue
    return max(candidates, default=((), None), key=lambda x: x[0])[1]

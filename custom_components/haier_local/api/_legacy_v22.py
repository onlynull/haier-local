# ���ļ���װ����֤�� v22 �ײ�Э�飬�ⲿ������ʹ�� HaierClient��
from __future__ import annotations
import argparse
import getpass
import base64
import hashlib
import json
import queue
import threading
import random
import secrets
import socket
import ssl
import struct
import time
from urllib.parse import urlparse
from pathlib import Path
import requests
from .profile_decoder import HaierProfileDecoder, ProfileDecodedData, choose_profile_file
APP_ID = 'MB-UZHSH-0001'
APP_KEY = '5dfca8714eb26e3a776e58a8273c8752'
LOGIN_API = 'https://zj.haier.net/api-gw/oauthserver/account/v1/login'
DEVICES_API = 'https://uws.haier.net/uds/v1/protected/deviceinfos'
DEFAULT_HOST = 'gw.haier.net'
DEFAULT_PORT = 56811
DEFAULT_LOCAL_PORT = 56800
DEFAULT_KEY_CACHE = 'haier_localkey.json'
DEFAULT_AUTH_CACHE = 'haier_auth_cache.json'
DEFAULT_SNAPSHOT_LOG = 'haier_status_snapshots.jsonl'
DEFAULT_PROFILE_JSON = 'haier_profile_2.0.46.json'
PROFILE_DECODER = None
PROFILE_PATH = None
_TLS = threading.local()


def set_thread_profile(decoder, path=None):
    """每个局域网线程绑定自己的 profile，避免冰箱和热水器互相覆盖。"""
    _TLS.PROFILE_DECODER = decoder
    if path is not None:
        _TLS.PROFILE_PATH = path


def current_decoder():
    return getattr(_TLS, "PROFILE_DECODER", None) or PROFILE_DECODER


def current_profile_path():
    return getattr(_TLS, "PROFILE_PATH", None) or PROFILE_PATH

def compact(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':'))

def redact(s, keep=5):
    if not s:
        return ''
    s = str(s)
    return s if len(s) <= keep * 2 else s[:keep] + '...' + s[-keep:]

def sequence_id():
    return time.strftime('%Y%m%d%H%M%S') + str(random.randint(100000, 999999))

def sign(url, body, ts):
    path = urlparse(url).path
    body = body.replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '')
    raw = path + body + APP_ID + APP_KEY + ts
    return hashlib.sha256(raw.encode()).hexdigest()

def headers(url, token, client_id, body=''):
    ts = str(int(time.time() * 1000))
    return {'accessToken': token, 'appId': APP_ID, 'appKey': APP_KEY, 'clientId': client_id, 'sequenceId': sequence_id(), 'sign': sign(url, body, ts), 'timestamp': ts, 'timezone': '+8', 'language': 'zh-CN', 'Content-Type': 'application/json'}

def login(sess, phone, password):
    body_obj = {'username': phone, 'password': password}
    body = compact(body_obj)
    r = sess.post(LOGIN_API, data=body.encode(), headers=headers(LOGIN_API, '', phone, body), timeout=20)
    print(f'[*] login HTTP {r.status_code}')
    obj = r.json()
    print(f'    retCode={obj.get('retCode')} retInfo={obj.get('retInfo')}')
    if obj.get('retCode') != '00000':
        raise RuntimeError(obj)
    ti = obj['data']['tokenInfo']
    return (phone, ti['accountToken'])

def device_list(sess, token, client_id, *, validate_auth=False):
    r = sess.get(DEVICES_API, headers=headers(DEVICES_API, token, client_id), timeout=20)
    print(f'[*] device list HTTP {r.status_code}')
    try:
        obj = r.json()
    except Exception:
        if validate_auth:
            raise RuntimeError(f'device list returned non-JSON HTTP {r.status_code}')
        raise
    ret_code = obj.get('retCode')
    if r.status_code in (401, 403) or (ret_code is not None and ret_code != '00000'):
        msg = obj.get('retInfo') or obj.get('message') or obj.get('msg') or 'authentication failed'
        raise PermissionError(f'Haier token rejected: HTTP {r.status_code}, retCode={ret_code}, {msg}')
    devices = obj.get('deviceinfos')
    if devices is None and isinstance(obj.get('data'), dict):
        devices = obj['data'].get('deviceinfos')
    if devices is None:
        devices = []
    for d in devices:
        print(f'    {d.get('deviceId')}  {d.get('deviceName')}  {d.get('productNameT')}  online={d.get('online')}')
    return devices

def load_auth_cache(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'[!] auth cache read failed: {e}')
        return None
    token = obj.get('token')
    client_id = obj.get('client_id')
    if not token or not client_id:
        return None
    return {'token': str(token), 'client_id': str(client_id), 'phone': obj.get('phone'), 'saved_at': obj.get('saved_at')}

def save_auth_cache(path, client_id, token, phone=None):
    p = Path(path)
    obj = {'client_id': str(client_id), 'token': str(token), 'phone': str(phone or client_id), 'saved_at': int(time.time())}
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[+] Saved HTTP auth cache: {p}')

def clear_auth_cache(path):
    p = Path(path)
    try:
        if p.exists():
            p.unlink()
            print(f'[*] Removed invalid auth cache: {p}')
    except Exception as e:
        print(f'[!] could not remove invalid auth cache: {e}')

def interactive_login(sess, phone=None):
    if not sys.stdin.isatty():
        raise RuntimeError('Cached Haier token is invalid and no interactive terminal is available. Re-run with --phone and --password.')
    if not phone:
        phone = input('Haier account phone: ').strip()
    password = getpass.getpass('Haier account password: ')
    if not phone or not password:
        raise RuntimeError('phone/password cannot be empty')
    return login(sess, phone, password)

def derive_gateway_password(username_body: str, salt: bytes=b'haier_sdk') -> str:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        raise SystemExit('Missing cryptography: pip install cryptography')
    block = len(salt).to_bytes(2, 'big') + salt
    block += b'\x00' * (-len(block) % 16)
    key = hashlib.md5(username_body.encode()).digest()
    enc = Cipher(algorithms.AES(key), modes.CBC(b'\x00' * 16)).encryptor()
    return (enc.update(block) + enc.finalize()).hex()

def derive_gateway_auth(username_body=None):
    body = username_body or ''.join((str(secrets.randbelow(10)) for _ in range(8)))
    username = '01' + body
    password = derive_gateway_password(body)
    return (body, username, password)

def default_mqtt_client_id(client_id: str) -> str:
    return hashlib.md5(('haier_local_probe_' + client_id).encode()).hexdigest()

def enc_utf8(s: str) -> bytes:
    b = s.encode()
    return struct.pack('>H', len(b)) + b

def enc_remaining(n: int) -> bytes:
    out = bytearray()
    while True:
        d = n % 128
        n //= 128
        if n:
            d |= 128
        out.append(d)
        if not n:
            return bytes(out)

def packet(first: int, body: bytes) -> bytes:
    return bytes([first]) + enc_remaining(len(body)) + body

def recv_exact(s, n):
    b = bytearray()
    while len(b) < n:
        x = s.recv(n - len(b))
        if not x:
            raise EOFError('socket closed')
        b += x
    return bytes(b)

def recv_packet(s):
    first = recv_exact(s, 1)[0]
    rem = 0
    mul = 1
    for _ in range(4):
        d = recv_exact(s, 1)[0]
        rem += (d & 127) * mul
        if not d & 128:
            break
        mul *= 128
    return (first, recv_exact(s, rem))

def mqtt_connect(s, client_id, username, password):
    flags = 2 | 128 | 64
    vh = enc_utf8('MQTT') + bytes([4, flags]) + struct.pack('>H', 30)
    pl = enc_utf8(client_id) + enc_utf8(username) + enc_utf8(password)
    s.sendall(packet(16, vh + pl))
    first, body = recv_packet(s)
    print(f'[*] CONNACK raw: first=0x{first:02x} body={body.hex(' ')}')
    if first >> 4 != 2 or len(body) < 2:
        raise RuntimeError('not a valid CONNACK')
    rc = body[1]
    meanings = {0: 'accepted', 1: 'unacceptable protocol version', 2: 'identifier rejected', 3: 'server unavailable', 4: 'bad username/password', 5: 'not authorized'}
    print(f'[*] CONNACK rc={rc} ({meanings.get(rc, 'vendor/unknown')})')
    return rc

def mqtt_subscribe(s, topic, pid=1):
    body = struct.pack('>H', pid) + enc_utf8(topic) + b'\x00'
    s.sendall(packet(130, body))
    first, rsp = recv_packet(s)
    print(f'[*] SUBACK first=0x{first:02x} body={rsp.hex(' ')}')
    if first >> 4 != 9:
        raise RuntimeError('SUBACK expected')

def mqtt_publish(s, topic, payload):
    s.sendall(packet(48, enc_utf8(topic) + payload.encode()))

def parse_publish(first, body):
    ln = struct.unpack('>H', body[:2])[0]
    topic = body[2:2 + ln].decode(errors='replace')
    pos = 2 + ln
    qos = first >> 1 & 3
    if qos:
        pos += 2
    return (topic, body[pos:])

def make_localkey_request(device_id, token, sn):
    inner = compact({'sn': str(sn), 'dev': device_id, 'flag': 0})
    data = base64.b64encode(inner.encode()).decode()
    return compact({'type': 'devLocalkey', 'data': data, 'tokens': [token]})

def decode_localkey_message(payload: bytes, verbose: bool=True):
    try:
        outer = json.loads(payload.decode())
    except Exception:
        return None
    if verbose:
        print('[<] JSON:')
        print(json.dumps(outer, ensure_ascii=False, indent=2))
    if not isinstance(outer, dict):
        return None
    if outer.get('type') == 'devLocalkey' and isinstance(outer.get('data'), str):
        try:
            inner = json.loads(base64.b64decode(outer['data']).decode())
        except Exception as e:
            print(f'[!] devLocalkey data decode failed: {e}')
            return None
        if verbose:
            print('[<] devLocalkey inner:')
            print(json.dumps(inner, ensure_ascii=False, indent=2))
        return inner
    return None

def run_gateway(host, port, mqtt_client_id, username, password, token, device_id, timeout, connect_ip=None, legacy_tls=False, insecure_legacy_tls=False):
    target = connect_ip or host
    target_source = 'explicit --connect-ip' if connect_ip else 'DNS-resolved host'
    print(f'\n[*] Connecting TCP {target}:{port} (TLS SNI={host}, source={target_source})')
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addrs = sorted({x[4][0] for x in infos})
        print(f'[*] DNS {host} -> {', '.join(addrs)}')
    except Exception as e:
        print(f'[!] DNS lookup failed: {e!r}')
    t0 = time.monotonic()
    try:
        raw = socket.create_connection((target, port), timeout=10)
    except Exception as e:
        dt = time.monotonic() - t0
        print(f'[!] TCP connect failed after {dt:.2f}s: {type(e).__name__}: {e}')
        print('[!] This failed BEFORE TLS/MQTT. MQTT credentials were not tested.')
        return {'stage': 'tcp_connect', 'target': target, 'port': port, 'error': repr(e)}
    print(f'[+] TCP connected in {time.monotonic() - t0:.3f}s')
    ctx = ssl.create_default_context()
    auto_legacy_tls = port == 56811
    if legacy_tls or insecure_legacy_tls or auto_legacy_tls:
        try:
            ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
            why = 'automatic for port 56811' if auto_legacy_tls and (not (legacy_tls or insecure_legacy_tls)) else 'requested'
            print(f'[i] legacy TLS compatibility enabled ({why}): OpenSSL security level lowered to 0; certificate verification remains enabled')
        except ssl.SSLError as e:
            print(f'[!] could not lower TLS security level: {e}')
    if insecure_legacy_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        print('[i] insecure legacy TLS enabled: certificate-chain verification disabled')
    s = ctx.wrap_socket(raw, server_hostname=host)
    s.settimeout(max(5.0, timeout))
    try:
        print(f'[+] TLS: {s.version()} cipher={s.cipher()}')
        der = s.getpeercert(binary_form=True)
        if der:
            fp = hashlib.sha256(der).hexdigest()
            print(f'[+] peer cert SHA256={fp}')
        cert = s.getpeercert()
        if cert:
            print(f'[+] peer subject={cert.get('subject')}')
        rc = mqtt_connect(s, mqtt_client_id, username, password)
        if rc != 0:
            return {'stage': 'mqtt_connect', 'rc': rc}
        down = f'Client/{mqtt_client_id}/Business/Down'
        up = f'Client/{mqtt_client_id}/Business/Up'
        mqtt_subscribe(s, down)
        sn = str(int(time.time() * 1000) % 1000000000)
        req = make_localkey_request(device_id, token, sn)
        safe = json.loads(req)
        safe['tokens'] = [redact(token)]
        print('[>] request:')
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        mqtt_publish(s, up, req)
        s.settimeout(min(2.0, max(0.5, timeout)))
        print(f'[+] published to {up}')
        print(f'[*] waiting {timeout:.1f}s for Business/Down')
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                first, body = recv_packet(s)
            except socket.timeout:
                continue
            typ = first >> 4
            if typ == 3:
                topic, payload = parse_publish(first, body)
                print(f'\n[<] PUBLISH {topic} ({len(payload)} bytes)')
                inner = decode_localkey_message(payload, verbose=False)
                if inner:
                    rsp_sn = str(inner.get('sn', ''))
                    if rsp_sn and rsp_sn != sn:
                        print(f'[i] unrelated sn={rsp_sn}, ours={sn}')
                        continue
                    err = inner.get('errNo')
                    key = inner.get('key') or inner.get('localKey') or inner.get('localkey')
                    vers = inner.get('vers') or inner.get('version') or inner.get('localKeyVers')
                    if err not in (None, 0, '0'):
                        print(f'[!] gateway errNo={err}')
                        return {'stage': 'localkey', 'errNo': err, 'inner': inner}
                    if key:
                        print('\n' + '=' * 70)
                        print('[+] LOCALKEY FOUND')
                        print(f'    device : {device_id}')
                        print(f'    key    : {redact(key, 4)}')
                        print(f'    version: {vers}')
                        print('=' * 70)
                        return {'stage': 'done', 'key': key, 'version': vers, 'inner': inner}
            elif typ == 13:
                print('[<] PINGRESP')
            else:
                print(f'[<] MQTT type={typ} len={len(body)} raw={body[:80].hex(' ')}')
        print('[!] no matching LocalKey response')
        return {'stage': 'timeout'}
    finally:
        try:
            s.close()
        except Exception:
            pass
USS_INFO_HELLO = 0
USS_INFO_HELLO_RESP = 1
USS_INFO_HELLO_DONE = 2
USS_INFO_HELLO_DONE_RESP = 3
USS_TYPE_BYTE = {2: 1, 3: 110}
USS_ZERO_IV = b'\x00' * 16
USS_INFO_DATA_CODE = 60100
SDK_HEARTBEAT_INTERVAL = 5.0
SDK_HEARTBEAT_LOSS_TIMEOUT = 20.0
UWT_HEARTBEAT_CMD = 24050

def uss_encode_info_code(info_code, sn, payload=b'', *, type_byte=1, flag=0, session=0):
    return struct.pack('>IHBBIHH', info_code & 4294967295, len(payload) + 10, type_byte & 255, flag & 255, sn & 4294967295, 0, session & 65535) + payload

def _sdk_numeric_nonce(n: int) -> bytes:
    return ''.join((str(secrets.randbelow(10)) for _ in range(n))).encode('ascii')

def build_uwt_heartbeat(device_id: str, seq: int) -> bytes:
    dev = device_id.encode('ascii', 'strict')[:15]
    out = bytearray(64)
    struct.pack_into('>I', out, 0, UWT_HEARTBEAT_CMD)
    struct.pack_into('>I', out, 8, seq & 4294967295)
    struct.pack_into('>I', out, 12, 48)
    out[48:48 + len(dev)] = dev
    return bytes(out)

def session_sequence_base(payload: bytes, local_key: str) -> int:
    """HELLO_DONE_RESP 明文前 4 字节是本会话出站 biz_sn。错 sn 会直接被模块踢线。"""
    _crypto_sn, plain = biz_decrypt(payload, local_key)
    if len(plain) >= 4:
        return int.from_bytes(plain[:4], 'big')
    return int(_crypto_sn)


def biz_encrypt(plaintext_data: bytes, local_key: str, biz_sn: int, *, md5_nonce4: bytes | None=None, tail_nonce5: bytes | None=None) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        raise RuntimeError('Missing cryptography: pip install cryptography')
    data = bytes(plaintext_data)
    if len(data) > 57344:
        raise ValueError('business data too large')
    nonce4 = bytes(md5_nonce4) if md5_nonce4 is not None else _sdk_numeric_nonce(4)
    tail5 = bytes(tail_nonce5) if tail_nonce5 is not None else _sdk_numeric_nonce(5)
    if len(nonce4) != 4:
        raise ValueError('md5_nonce4 must be exactly 4 bytes')
    if len(tail5) != 5:
        raise ValueError('tail_nonce5 must be exactly 5 bytes')
    rawlen = len(data) + 40
    aes_len = (len(data) + 42 + 15) // 16 * 16
    pt = bytearray(aes_len)
    struct.pack_into('>H', pt, 0, rawlen)
    struct.pack_into('>I', pt, 2, biz_sn & 4294967295)
    pt[38:42] = nonce4
    pt[42:42 + len(data)] = data
    pt[6:22] = hashlib.md5(pt[38:42 + len(data)]).digest()
    key = localkey_aes_key(local_key)
    enc = Cipher(algorithms.AES(key), modes.CBC(USS_ZERO_IV)).encryptor()
    ciphertext = enc.update(bytes(pt)) + enc.finalize()
    return ciphertext + tail5

def build_uss_heartbeat(device_id: str, *, uwt_seq: int, session: int, type_byte: int) -> tuple[bytes, bytes]:
    inner = build_uwt_heartbeat(device_id, uwt_seq)
    outer = uss_encode_info_code(USS_INFO_DATA_CODE, 0, inner, type_byte=type_byte, flag=0, session=session)
    return (outer, inner)

def uss_encode_message(info_type, sn, payload=b'', *, type_byte=1, flag=0, session=0):
    return struct.pack('>IHBBIHH', 60000 + info_type, len(payload) + 10, type_byte & 255, flag & 255, sn & 4294967295, 0, session & 65535) + payload

def uss_decode_message(buf: bytes):
    if len(buf) < 16:
        raise ValueError(f'short uSS message: {len(buf)} B')
    info_code, length, type_byte, flag, sn, code2, session = struct.unpack('>IHBBIHH', buf[:16])
    total = 6 + length
    if total > len(buf):
        raise ValueError(f'incomplete uSS message: need {total}, got {len(buf)}')
    return {'info_type': info_code - 60000, 'info_code': info_code, 'declared_length': length, 'type_byte': type_byte, 'flag': flag, 'sn': sn, 'code2': code2, 'session': session, 'payload': buf[16:total], 'raw': buf[:total]}

def uss_recv_one(sock: socket.socket, timeout: float):
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < 6:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError('peer closed before uSS header')
        buf += chunk
    declared = struct.unpack('>H', buf[4:6])[0]
    total = 6 + declared
    if total < 16:
        raise ValueError(f'invalid uSS declared length {declared}')
    while len(buf) < total:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError(f'peer closed at {len(buf)}/{total} bytes')
        buf += chunk
    msg = uss_decode_message(bytes(buf[:total]))
    extra = bytes(buf[total:])
    return (msg, extra)

def uss_hello(device_id: str, sn=1, pro_ver=2):
    if pro_ver not in USS_TYPE_BYTE:
        raise ValueError('pro_ver must be 2 or 3')
    dev = device_id.encode('ascii').ljust(32, b'\x00')[:32]
    payload = dev if pro_ver == 2 else dev + struct.pack('>II', 0, 0)
    return uss_encode_message(USS_INFO_HELLO, sn, payload, type_byte=USS_TYPE_BYTE[pro_ver])

def uss_hello_done(sn: int, session: int, type_byte: int):
    return uss_encode_message(USS_INFO_HELLO_DONE, sn, b'', type_byte=type_byte, session=session)

def localkey_aes_key(local_key: str) -> bytes:
    return hashlib.md5(local_key.encode('ascii')).digest()

def destuff_epp(blob: bytes) -> bytes:
    at = blob.find(b'\xff\xff')
    if at < 0:
        return blob
    body = blob[at + 2:]
    if b'\xffU' not in body:
        return blob
    out = bytearray()
    i = 0
    while i < len(body):
        b = body[i]
        out.append(b)
        i += 1
        if b == 255 and i < len(body) and (body[i] == 85):
            i += 1
    return blob[:at + 2] + bytes(out)

def biz_decrypt(ciphertext: bytes, local_key: str):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        raise RuntimeError('Missing cryptography: pip install cryptography')
    n = len(ciphertext) // 16 * 16
    if n < 48:
        raise ValueError(f'biz ciphertext too short: {len(ciphertext)} B')
    key = localkey_aes_key(local_key)
    dec = Cipher(algorithms.AES(key), modes.CBC(USS_ZERO_IV)).decryptor()
    pt = dec.update(ciphertext[:n]) + dec.finalize()
    rawlen = struct.unpack('>H', pt[0:2])[0]
    biz_sn = struct.unpack('>I', pt[2:6])[0]
    datalen = rawlen - 40
    if not 40 < rawlen <= min(len(ciphertext) - 2, 57384):
        raise ValueError(f'bad rawlen {rawlen} (payload={len(ciphertext)} decrypted={len(pt)})')
    if datalen < 0 or 42 + datalen > len(pt):
        raise ValueError(f'bad datalen {datalen}')
    expected = pt[6:22]
    actual = hashlib.md5(pt[38:38 + datalen + 4]).digest()
    if expected != actual:
        raise ValueError('biz integrity MD5 failed (wrong/stale LocalKey or different framing)')
    data = destuff_epp(pt[42:42 + datalen])
    return (biz_sn, data)

def epp_summary(blob: bytes):
    at = blob.find(b'\xff\xff')
    if at < 0:
        return None
    if len(blob) < at + 12:
        return {'offset': at, 'note': 'short EPP frame'}
    frame_type = blob[at + 9]
    cmd = blob[at + 10:at + 12].hex()
    return {'offset': at, 'frame_type': frame_type, 'command': cmd, 'length': len(blob) - at}

def parse_epp_frame(blob: bytes):
    at = blob.find(b'\xff\xff')
    if at < 0:
        return None
    frame = blob[at:]
    if len(frame) < 13:
        return {'offset': at, 'raw_length': len(frame), 'error': 'short EPP frame'}
    declared = frame[2]
    expected_total = declared + 3
    wire = frame[:expected_total] if len(frame) >= expected_total else frame
    frame_type = wire[9] if len(wire) > 9 else None
    cmd = wire[10:12] if len(wire) >= 12 else b''
    data = wire[12:-1] if len(wire) >= 13 else b''
    checksum = wire[-1] if len(wire) >= 1 else None
    calc = None
    checksum_ok = None
    if len(wire) >= 4 and checksum is not None:
        calc = sum(wire[2:-1]) & 255
        checksum_ok = calc == checksum
    return {'offset': at, 'declared_len': declared, 'expected_total': expected_total, 'actual_total': len(wire), 'frame_type': frame_type, 'command': cmd.hex(), 'data': data, 'checksum': checksum, 'checksum_calc': calc, 'checksum_ok': checksum_ok, 'raw': wire}

def _bool01(v):
    if v == 0:
        return False
    if v == 1:
        return True
    return None

def parse_bc12l1000_status(epp_data: bytes):
    out = {'profile': 'BC12L1000 / BCD-501WGCTDM4SSU1', 'raw_data_len': len(epp_data), 'fields': {}, 'unknown_nonzero': []}
    f = out['fields']
    if len(epp_data) > 2:
        f['refrigeratorActualTemperatureC'] = {'value_c': epp_data[0] - 38, 'raw': epp_data[0], 'offset': 0, 'confidence': 'confirmed_by_physical_test'}
        f['freezerActualTemperatureC'] = {'value_c': epp_data[1] - 38, 'raw': epp_data[1], 'offset': 1, 'confidence': 'confirmed_by_physical_test'}
        f['vtRoomActualTemperatureC'] = {'value_c': epp_data[2] - 38, 'raw': epp_data[2], 'offset': 2, 'confidence': 'confirmed_by_physical_test'}
    if len(epp_data) > 9:
        ref_level = epp_data[6]
        freezer_level = epp_data[7]
        vt_level = epp_data[8]
        vt2_level = epp_data[9]
        f['refrigeratorTargetTempLevel'] = {'raw': ref_level, 'display_c': ref_level - 1 if 2 <= ref_level <= 10 else None, 'offset': 6, 'confidence': 'strong_match+confirmed_model_transform'}
        f['freezerTargetTempLevel'] = {'raw': freezer_level, 'display_c': freezer_level - 30 if 6 <= freezer_level <= 16 else None, 'offset': 7, 'confidence': 'strong_match+confirmed_model_transform'}
        f['vtRoomTargetTempLevel'] = {'raw': vt_level, 'display_c': vt_level - 31 if 11 <= vt_level <= 36 else None, 'offset': 8, 'confidence': 'strong_match+confirmed_model_transform'}
        vt2_names = {31: '0�㱣��', 33: '����', 35: '��Ʒ', 37: 'ĸӤ'}
        f['vtRoom2TargetTempLevel'] = {'raw': vt2_level, 'display': vt2_names.get(vt2_level), 'offset': 9, 'confidence': 'strong_match+confirmed_model_transform'}
    if len(epp_data) > 17:
        door_flags_main = epp_data[15]
        door_flags_aux = epp_data[17]
        f['rightRefrigeratorDoor'] = {'open': bool(door_flags_aux & 2), 'raw_flags': door_flags_aux, 'mask': 2, 'offset': 17, 'confidence': 'confirmed_by_physical_test'}
        f['leftRefrigeratorDoor'] = {'open': bool(door_flags_main & 1), 'raw_flags': door_flags_main, 'mask': 1, 'offset': 15, 'confidence': 'confirmed_by_physical_test'}
        f['rightFreezerDoor'] = {'open': bool(door_flags_main & 4), 'raw_flags': door_flags_main, 'mask': 4, 'offset': 15, 'confidence': 'confirmed_by_physical_test'}
        f['leftFreezerDoor'] = {'open': bool(door_flags_main & 2), 'raw_flags': door_flags_main, 'mask': 2, 'offset': 15, 'confidence': 'confirmed_by_physical_test'}
        f['doorFlagsMainRaw'] = {'value': door_flags_main, 'hex': f'0x{door_flags_main:02x}', 'offset': 15, 'confidence': 'raw'}
        f['doorFlagsAuxRaw'] = {'value': door_flags_aux, 'hex': f'0x{door_flags_aux:02x}', 'offset': 17, 'confidence': 'raw'}
    if len(epp_data) > 18:
        f['refrigeratorTemperatureC'] = {'value_c': epp_data[18], 'raw': epp_data[18], 'offset': 18, 'confidence': 'provisional'}
    if len(epp_data) > 38:
        f['sterilizationTime'] = {'value': epp_data[38], 'raw': epp_data[38], 'offset': 38, 'confidence': 'provisional'}
        f['unknownDynamic38'] = {'value': epp_data[38], 'raw': epp_data[38], 'offset': 38, 'confidence': 'unknown_dynamic'}
    if len(epp_data) >= 69:
        stop_h, stop_m = (epp_data[62], epp_data[63])
        start_h, start_m = (epp_data[64], epp_data[65])
        mode_b_wire, bright_wire, night_wire = (epp_data[66], epp_data[67], epp_data[68])
        f['lightModeStopTime'] = {'value': f'{stop_h:02d}:{stop_m:02d}', 'raw': [stop_h, stop_m], 'offset': [62, 63], 'confidence': 'strong_match'}
        f['lightModeStartTime'] = {'value': f'{start_h:02d}:{start_m:02d}', 'raw': [start_h, start_m], 'offset': [64, 65], 'confidence': 'strong_match'}
        f['modeBrightness'] = {'value': mode_b_wire + 1, 'raw': mode_b_wire, 'offset': 66, 'confidence': 'strong_match_provisional_transform'}
        f['brightness'] = {'value': bright_wire + 1, 'raw': bright_wire, 'offset': 67, 'confidence': 'strong_match_provisional_transform'}
        f['nightMode'] = {'value': _bool01(night_wire), 'raw': night_wire, 'offset': 68, 'confidence': 'strong_match'}
    claimed = set()
    for item in f.values():
        off = item.get('offset')
        if isinstance(off, int):
            claimed.add(off)
        elif isinstance(off, list):
            claimed.update((x for x in off if isinstance(x, int)))
    for i, v in enumerate(epp_data):
        if v and i not in claimed:
            out['unknown_nonzero'].append({'offset': i, 'hex': f'{v:02x}', 'dec': v})
    out['byte_table'] = [{'offset': i, 'hex': f'{v:02x}', 'dec': v} for i, v in enumerate(epp_data)]
    return out

def parse_alarm_0f5a(epp_data: bytes):
    value = int.from_bytes(epp_data, 'big') if epp_data else 0
    active = []
    bit = 0
    tmp = value
    while tmp:
        if tmp & 1:
            active.append(bit)
        tmp >>= 1
        bit += 1
    return {'raw_len': len(epp_data), 'raw_hex': epp_data.hex(), 'bitmap_hex': f'0x{value:0{len(epp_data) * 2}x}' if epp_data else '0x0', 'active_fault_bits': active, 'has_alarm': bool(value), 'note': 'fault names are model-specific; v8 reports bit numbers only'}

def _profile_frame_to_status(frame: ProfileDecodedData):
    fields = {}
    claimed = set()
    for name, fld in frame.fields.items():
        if not fld.available:
            continue
        item = {'value': fld.value, 'raw': fld.raw_value, 'raw_hex': fld.raw_bytes.hex(), 'offset': fld.byte_offsets[0] if len(fld.byte_offsets) == 1 else list(fld.byte_offsets), 'offsets': list(fld.byte_offsets), 'unit': fld.unit, 'data_type': fld.data_type, 'cae_type': fld.cae_type, 'writable': fld.writable, 'epp_cmd': fld.epp_cmd, 'profile_start_word': fld.start_word, 'profile_start_bit': fld.start_bit, 'profile_length': fld.length, 'source': 'profile_json'}
        if fld.note:
            item['note'] = fld.note
        fields[name] = item
        claimed.update(fld.byte_offsets)
    unknown_nonzero = [{'offset': i, 'hex': f'{v:02x}', 'dec': v} for i, v in enumerate(frame.raw_data) if v and i not in claimed]
    path = current_profile_path()
    return {'profile': frame.profile_name, 'profile_version': frame.profile_version, 'profile_source': str(path) if path else None, 'command': frame.command, 'raw_data_len': len(frame.raw_data), 'fields': fields, 'unavailable_fields': [{'name': name, 'offsets': list(fld.byte_offsets), 'note': fld.note} for name, fld in frame.fields.items() if not fld.available], 'unknown_nonzero': unknown_nonzero, 'byte_table': [{'offset': i, 'hex': f'{v:02x}', 'dec': v} for i, v in enumerate(frame.raw_data)]}

def _coap_uint(value: int) -> bytes:
    if value < 0:
        raise ValueError('negative CoAP uint')
    if value == 0:
        return b''
    return value.to_bytes((value.bit_length() + 7) // 8, 'big')

def _coap_option_header(delta: int, length: int) -> bytes:

    def nibble(v):
        if v <= 12:
            return (v, b'')
        if v <= 268:
            return (13, bytes([v - 13]))
        if v <= 65804:
            return (14, struct.pack('>H', v - 269))
        raise ValueError('CoAP option delta/length too large')
    dn, de = nibble(delta)
    ln, le = nibble(length)
    return bytes([dn << 4 | ln]) + de + le

def encode_coap_options(options):
    out = bytearray()
    previous = 0
    for number, value in sorted(options, key=lambda x: x[0]):
        value = bytes(value)
        delta = int(number) - previous
        if delta < 0:
            raise ValueError('CoAP options not monotonic')
        out += _coap_option_header(delta, len(value))
        out += value
        previous = int(number)
    return bytes(out)

def build_coap_request(*, method: int, message_id: int, token: bytes, uri_port: int, path_segments, query=None, payload: bytes=b'') -> bytes:
    token = bytes(token)
    if len(token) > 8:
        raise ValueError('CoAP token > 8 bytes')
    if not 0 <= message_id <= 65535:
        raise ValueError('invalid CoAP message id')
    header = bytes([64 | len(token), method & 255]) + struct.pack('>H', message_id)
    options = []
    if int(uri_port) != 5683:
        options.append((7, _coap_uint(int(uri_port))))
    for seg in path_segments:
        if seg != '':
            options.append((11, str(seg).encode('utf-8')))
    if query:
        options.append((15, str(query).encode('utf-8')))
    wire = header + token + encode_coap_options(options)
    if payload:
        wire += b'\xff' + bytes(payload)
    return wire

def parse_coap_message(data: bytes):
    if len(data) < 4:
        return None
    first = data[0]
    if first >> 6 != 1:
        return None
    typ = first >> 4 & 3
    tkl = first & 15
    if tkl > 8 or len(data) < 4 + tkl:
        return None
    code = data[1]
    mid = struct.unpack('>H', data[2:4])[0]
    token = data[4:4 + tkl]
    pos = 4 + tkl
    current = 0
    options = []

    def ext(nib, p):
        if nib <= 12:
            return (nib, p)
        if nib == 13:
            if p >= len(data):
                raise ValueError
            return (13 + data[p], p + 1)
        if nib == 14:
            if p + 2 > len(data):
                raise ValueError
            return (269 + struct.unpack('>H', data[p:p + 2])[0], p + 2)
        raise ValueError
    try:
        while pos < len(data):
            if data[pos] == 255:
                pos += 1
                break
            b = data[pos]
            pos += 1
            delta, pos = ext(b >> 4, pos)
            ln, pos = ext(b & 15, pos)
            current += delta
            if pos + ln > len(data):
                return None
            value = data[pos:pos + ln]
            pos += ln
            options.append((current, value))
    except ValueError:
        return None
    return {'version': 1, 'type': typ, 'code': code, 'code_class': code >> 5, 'code_detail': code & 31, 'message_id': mid, 'token': token, 'options': options, 'payload': data[pos:]}

def build_cae_attr_read_coap(device_id: str, attr_name: str, *, local_port: int=56800, token_seed: int=10002, message_id: int=1):
    token = str(int(token_seed)).encode('ascii')
    pdu = build_coap_request(method=1, message_id=message_id, token=token, uri_port=local_port, path_segments=['cae', 'dev', device_id, 'attr', 'r'], query=f'name={attr_name}')
    return (pdu, {'attr': attr_name, 'token': token.decode(), 'message_id': message_id, 'local_port': local_port, 'path': f'/cae/dev/{device_id}/attr/r/?name={attr_name}'})

def build_cae_attr_write_coap(device_id: str, attr_name: str, attr_value: str, *, local_port: int=56800, token_seed: int=10002, message_id: int=1):
    """SDK 本地写属性：CON PUT /cae/dev/<id>/attr/w，JSON 含 devId/name/value。"""
    token = str(int(token_seed)).encode('ascii')
    body = compact({'devId': str(device_id), 'name': str(attr_name), 'value': str(attr_value)}).encode('utf-8')
    pdu = build_coap_request(method=3, message_id=message_id, token=token, uri_port=local_port, path_segments=['cae', 'dev', device_id, 'attr', 'w'], payload=body)
    return (pdu, {'attr': attr_name, 'value': str(attr_value), 'token': token.decode(), 'message_id': message_id, 'local_port': local_port, 'path': f'/cae/dev/{device_id}/attr/w', 'payload': body.decode('utf-8')})

def _complete_control_command(command, **result):
    if not command:
        return
    command['result'] = result
    done = command.get('done')
    if done is not None and not done.is_set():
        done.set()

def _fail_pending_controls(pending, reason: str):
    for command in list(pending.values()):
        _complete_control_command(command, ok=False, error=reason)
    pending.clear()

def _resolve_pending_writes(pending, fields):
    if not pending or not isinstance(fields, dict):
        return
    for name, command in list(pending.items()):
        expected = command.get('expected')
        if name not in fields:
            continue
        current = fields.get(name)
        if current == expected or current == command.get('value'):
            pending.pop(name, None)
            _complete_control_command(command, ok=True, confirmed=True, value=current)
            continue
        if isinstance(current, dict) and current.get('value') in (expected, command.get('value')):
            pending.pop(name, None)
            _complete_control_command(command, ok=True, confirmed=True, value=current.get('value'))

def build_secure_coap_packet(coap_pdu: bytes, local_key: str, *, biz_sn: int, uss_sn: int, session: int, type_byte: int):
    encrypted = biz_encrypt(coap_pdu, local_key, biz_sn)
    return uss_encode_info_code(USS_INFO_DATA_CODE, uss_sn, encrypted, type_byte=type_byte, flag=1, session=session)

def parse_fridge_payload(plain: bytes):
    epp = parse_epp_frame(plain)
    if not epp:
        return {'kind': 'no_epp', 'cae_prefix_len': len(plain), 'raw_hex': plain.hex()}
    result = {'kind': 'unknown', 'cae_prefix_len': epp['offset'], 'epp': {k: v for k, v in epp.items() if k not in ('data', 'raw')}}
    cmd = epp['command']
    cmd_upper = cmd.upper()
    if cmd_upper == '6C01':
        result.update(parse_change_6c01(epp['data']))
        return result
    decoder = current_decoder()
    if decoder is not None and decoder.supports_command(cmd_upper):
        frame = decoder.decode_status(cmd_upper, epp['data'])
        result['kind'] = 'full_status' if cmd_upper == '6D01' else 'profile_status'
        result['status'] = _profile_frame_to_status(frame)
        return result
    if cmd == '0f5a':
        result['kind'] = 'alarm_bitmap'
        result['alarm'] = parse_alarm_0f5a(epp['data'])
        if decoder is not None and decoder.alarms:
            result['alarm']['profile_alarm_map'] = decoder.decode_alarm_bitmap(epp['data'])
        return result
    if cmd == '6d01':
        result['kind'] = 'full_status'
        result['status'] = parse_bc12l1000_status(epp['data'])
    else:
        result['epp_data_hex'] = epp['data'].hex()
    return result

def _hex_rows(data: bytes, width: int=16):
    rows = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hx = ' '.join((f'{b:02x}' for b in chunk))
        asc = ''.join((chr(b) if 32 <= b < 127 else '.' for b in chunk))
        rows.append((off, hx, asc))
    return rows

def print_complete_protocol_payloads(plain: bytes, parsed: dict):
    print('        ���� complete decrypted payload ����')
    print(f'        decrypted data[{len(plain)}]:')
    for off, hx, asc in _hex_rows(plain):
        print(f'        {off:04x}: {hx:<47s}  |{asc}|')
    epp = parse_epp_frame(plain)
    if not epp:
        print('        EPP: not found')
        return
    raw = epp.get('raw', b'')
    data = epp.get('data', b'')
    print('        ���� complete EPP frame ����')
    print(f'        EPP offset={epp.get('offset')} total={len(raw)} declared_len={epp.get('declared_len')} frame_type=0x{epp.get('frame_type') or 0:02x} cmd={epp.get('command')} checksum=0x{epp.get('checksum') or 0:02x} checksum_ok={epp.get('checksum_ok')}')
    for off, hx, asc in _hex_rows(raw):
        print(f'        epp+{off:02x}: {hx:<47s}  |{asc}|')
    print('        ���� complete EPP data area ����')
    print(f'        EPP data[{len(data)}] (offsets below are relative to EPP data[0]):')
    for off, hx, asc in _hex_rows(data):
        print(f'        d+{off:02d}: {hx:<47s}  |{asc}|')
    print('        ���� EPP data byte index ����')
    entries = []
    for i, b in enumerate(data):
        entries.append(f'{i:02d}=0x{b:02x}({b:3d})')
    for i in range(0, len(entries), 8):
        print('        ' + '  '.join(entries[i:i + 8]))

def _format_profile_value(item: dict):
    v = item.get('value')
    unit = item.get('unit')
    if isinstance(v, bool):
        text = 'true' if v else 'false'
    else:
        text = str(v)
    return f'{text} {unit}'.rstrip() if unit else text
VTROOM2_MODE_MAP = {31: '0�㱣��', 33: '����', 35: '��Ʒ', 37: 'ĸӤ'}

def _compact_bool(v):
    if v is None:
        return '?'
    return '��' if bool(v) else '��'
FIELD_CN = {'refrigeratorDoorStatus': '�����', 'refrigerator2DoorStatus': '�����2', 'freezerDoorStatus': '�䶳��', 'vtRoomDoorStatus': '��������', 'refrigeratorTargetTempLevel': '����趨', 'freezerTargetTempLevel': '�䶳�趨', 'vtRoomTargetTempLevel': '�����趨', 'vtRoom2TargetTempLevel': 'Ӥ���ռ�', 'intelligenceMode': '����ģʽ', 'travelMode': '����ģʽ', 'nightMode': 'ҹ��ģʽ', 'cellPreservationStatus': 'ϸ��������', 'refSterilizationForcedOff': 'ǿ�ƹر�ɱ��', 'refSterilizationForcedOn': 'ǿ�ƿ���ɱ��', 'daypartingElectricityStatus': '��ʱ�õ�', 'forcedDefrostingStatus': 'ǿ�ƻ�˪', 'emergencyPowerSaving': '��������', 'peakPowerSaving': '��ʱ����', 'purificationMode': '����ģʽ'}

def build_changepara_index(profile_decoder):
    out = {}
    if profile_decoder is None:
        return out
    for name, definition in (profile_decoder.change_parameters or {}).items():
        cmd = str(definition.get('varyStatusCmd') or '').upper()
        attr = str(definition.get('attrID') or '').replace('0x', '').replace(' ', '')
        if not cmd or not attr:
            continue
        try:
            attr_bytes = bytes.fromhex(attr)
        except ValueError:
            continue
        d = dict(definition)
        d['name'] = name
        d['_attr_bytes'] = attr_bytes
        out.setdefault(cmd, {})[attr_bytes] = d
    return out

def decode_change_value(definition: dict, raw: bytes):
    if not raw:
        return (None, None)
    raw_int = int.from_bytes(raw, 'big', signed=False)
    variants = definition.get('variants')
    if isinstance(variants, list):
        for item in variants:
            if item.get('eppValue') == raw_int:
                return (item.get('stdValue'), raw_int)
            try:
                if int(item.get('eppValue')) == raw_int:
                    return (item.get('stdValue'), raw_int)
            except Exception:
                pass
        return (raw_int, raw_int)
    if isinstance(variants, dict):
        k = variants.get('k', 1)
        c = variants.get('c', 0)
        try:
            return (raw_int * k + c, raw_int)
        except Exception:
            return (raw_int, raw_int)
    return (raw_int, raw_int)

def _candidate_change_records(data: bytes, attr_map: dict):
    candidates = []
    for off in range(0, max(0, len(data) - 1)):
        two = data[off:off + 2]
        definition = attr_map.get(two)
        if not definition:
            continue
        n = int(definition.get('dataLen') or 0)
        if n <= 0 or off + 2 + n > len(data):
            continue
        raw = data[off + 2:off + 2 + n]
        value, raw_int = decode_change_value(definition, raw)
        candidates.append({'offset': off, 'attr_id': two.hex(), 'name': definition.get('name'), 'value': value, 'raw_value': raw_int, 'raw_hex': raw.hex(), 'data_len': n, 'definition': definition})
    accepted = []
    occupied_until = -1
    for item in sorted(candidates, key=lambda x: x['offset']):
        if item['offset'] < occupied_until:
            continue
        accepted.append(item)
        occupied_until = item['offset'] + 2 + item['data_len']
    return accepted

def parse_change_6c01(data: bytes):
    idx = build_changepara_index(current_decoder())
    attr_map = idx.get('6C01', {})
    changes = _candidate_change_records(data, attr_map)
    return {'kind': 'change_status', 'command': '6C01', 'raw_hex': data.hex(), 'changes': changes, 'unknown': not bool(changes)}

class SessionStateCache:

    def __init__(self):
        self.fields = {}

    def apply_snapshot(self, parsed: dict):
        status = parsed.get('status') or {}
        fields = status.get('fields') or {}
        for name, item in fields.items():
            if not isinstance(item, dict) or not item.get('available', True):
                continue
            self.fields[name] = item.get('value')

    def apply_changes(self, parsed: dict):
        applied = []
        for change in parsed.get('changes') or []:
            name = change.get('name')
            if not name:
                continue
            old = self.fields.get(name)
            new = change.get('value')
            self.fields[name] = new
            item = dict(change)
            item['old_value'] = old
            item['new_value'] = new
            applied.append(item)
        return applied

    def door_summary(self):

        def b(name):
            v = self.fields.get(name)
            if v is None:
                return '?'
            return '��' if bool(v) else '��'
        return f'���1{b('refrigeratorDoorStatus')}/���2{b('refrigerator2DoorStatus')}/�䶳{b('freezerDoorStatus')}/����{b('vtRoomDoorStatus')}'

def _format_change_semantic(name, value):
    if name in {'refrigeratorDoorStatus', 'refrigerator2DoorStatus', 'freezerDoorStatus', 'vtRoomDoorStatus', 'intelligenceMode', 'travelMode', 'nightMode', 'cellPreservationStatus', 'refSterilizationForcedOff', 'refSterilizationForcedOn', 'daypartingElectricityStatus', 'forcedDefrostingStatus', 'emergencyPowerSaving', 'peakPowerSaving'}:
        return '��' if bool(value) else '��'
    if name == 'refrigeratorTargetTempLevel' and value is not None:
        return f'{int(value) - 1}��(L{value})'
    if name == 'freezerTargetTempLevel' and value is not None:
        return f'{int(value) - 30}��(L{value})'
    if name == 'vtRoomTargetTempLevel' and value is not None:
        return f'{int(value) - 31}��(L{value})'
    if name == 'vtRoom2TargetTempLevel':
        return f'{VTROOM2_MODE_MAP.get(value, value)}(L{value})'
    return str(value)

def compact_change_line(applied_changes, state_cache: SessionStateCache):
    if not applied_changes:
        return '[CHANGE] 6C01 received but no known attrID matched (use --debug-raw once)'
    parts = []
    for ch in applied_changes:
        name = ch['name']
        cn = FIELD_CN.get(name, name)
        old = ch.get('old_value')
        new = ch.get('new_value')
        old_s = '?' if old is None else _format_change_semantic(name, old)
        new_s = _format_change_semantic(name, new)
        parts.append(f'{cn} {old_s}��{new_s} [{ch['attr_id']}]')
    return '[CHANGE] ' + '��'.join(parts) + f' | ��:{state_cache.door_summary()}'

def compact_fridge_line(parsed: dict) -> str:
    kind = parsed.get('kind')
    if kind in ('full_status', 'profile_status'):
        status = parsed.get('status') or {}
        fields = status.get('fields') or {}

        def val(name):
            item = fields.get(name)
            return None if not item else item.get('value')
        cmd = (status.get('command') or '?').upper()
        if cmd == '6D01':
            rt = val('refrigeratorTemperatureC')
            ft = val('freezerTemperatureC')
            vt = val('vtRoomTemperature')
            env = val('envTemperature')
            hum = val('envHumidity')
            rl = val('refrigeratorTargetTempLevel')
            fl = val('freezerTargetTempLevel')
            vl = val('vtRoomTargetTempLevel')
            v2 = val('vtRoom2TargetTempLevel')
            rset = None if rl is None else int(rl) - 1
            fset = None if fl is None else int(fl) - 30
            vset = None if vl is None else int(vl) - 31
            v2name = VTROOM2_MODE_MAP.get(v2, f'L{v2}' if v2 is not None else '?')
            doors = f'���1{_compact_bool(val('refrigeratorDoorStatus'))}/���2{_compact_bool(val('refrigerator2DoorStatus'))}/�䶳{_compact_bool(val('freezerDoorStatus'))}/����{_compact_bool(val('vtRoomDoorStatus'))}'
            modes = f'����{_compact_bool(val('intelligenceMode'))}/����{_compact_bool(val('travelMode'))}/ҹ��{_compact_bool(val('nightMode'))}'
            ster = val('sterilizationTime')
            ster_off = val('refSterilizationOffTime')
            return f'[STATUS] ��� {rt}���{rset}��(L{rl}) | �䶳 {ft}���{fset}��(L{fl}) | ���� {vt}���{vset}��(L{vl}) | Ӥ��={v2name}(L{v2}) | ��:{doors} | ģʽ:{modes} | ���� {env}��/{hum}% | ɱ�� {ster}% ͣ��{ster_off}min'
        pairs = []
        for name, item in fields.items():
            if len(pairs) >= 8:
                break
            pairs.append(f'{name}={_format_profile_value(item)}')
        return f'[STATUS {cmd}] ' + ' '.join(pairs)
    if kind == 'change_status':
        return f'[CHANGE] decoded={len(parsed.get('changes') or [])}'
    if kind == 'alarm_bitmap':
        alarm = parsed.get('alarm') or {}
        mapped = (alarm.get('profile_alarm_map') or {}).get('active') or []
        if mapped:
            names = [x.get('description') or x.get('name') or f'bit{x.get('pos')}' for x in mapped]
            return '[ALARM] ' + '��'.join(names)
        bits = alarm.get('active_fault_bits') or []
        if bits:
            return '[ALARM] active bits=' + ','.join((str(x) for x in bits))
        return '[ALARM] �ޱ���'
    if kind == 'no_epp':
        return f'[RX] ��EPP���� {parsed.get('cae_prefix_len', 0)}B'
    return f'[RX] {kind}'

def print_fridge_status(parsed: dict):
    kind = parsed.get('kind')
    if kind in ('full_status', 'profile_status'):
        s = parsed['status']
        f = s['fields']
        print('        ���� profile decoded status ����')
        print(f'        profile={s.get('profile')} version={s.get('profile_version')} cmd={s.get('command')} source={s.get('profile_source')}')
        for name, item in f.items():
            off = item.get('offset')
            print(f'        {name:34s} = {_format_profile_value(item):12s} (raw={item.get('raw')}, off={off}, word={item.get('profile_start_word')}, bit={item.get('profile_start_bit')}, len={item.get('profile_length')})')
        unavailable = s.get('unavailable_fields') or []
        if unavailable:
            print(f'        profile fields outside this short frame: {len(unavailable)}')
        if s.get('unknown_nonzero'):
            unknown = ' '.join((f'{x['offset']}:{x['hex']}' for x in s['unknown_nonzero']))
            print(f'        unclaimed non-zero bytes: {unknown}')
    elif kind == 'alarm_bitmap':
        a = parsed['alarm']
        print('        ���� alarm bitmap ����')
        print(f'        raw        = {a['raw_hex']}')
        print(f'        has_alarm  = {a['has_alarm']}')
        print(f'        active bits= {a['active_fault_bits']}')
        mapped = (a.get('profile_alarm_map') or {}).get('active') or []
        for item in mapped:
            print(f'        pos {item['pos']}: {item.get('name')} / {item.get('description')}')

def print_fridge_chinese_details(parsed: dict):
    if parsed.get('kind') != 'full_status':
        return
    s = parsed['status']
    f = s['fields']

    def val(key):
        item = f.get(key)
        return None if not item else item.get('value')

    def bool_text(v):
        return '?' if v is None else '����' if v else '�ر�'
    print('        �T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T �������飨JSON Profile���T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T')
    print('        ����ǰ�¶ȡ�')
    for label, key in (('�����', 'refrigeratorTemperatureC'), ('�䶳��', 'freezerTemperatureC'), ('������', 'vtRoomTemperature'), ('�����¶�', 'envTemperature')):
        v = val(key)
        print(f'        {label}��{(v if v is not None else '?')} ��C')
    eh = val('envHumidity')
    if eh is not None:
        print(f'        ����ʪ�ȣ�{eh} %')
    print('        ���趨�ȼ���')
    for label, key in (('����趨�ȼ�', 'refrigeratorTargetTempLevel'), ('�䶳�趨�ȼ�', 'freezerTargetTempLevel'), ('�����趨�ȼ�', 'vtRoomTargetTempLevel'), ('������2ģʽ�ȼ�', 'vtRoom2TargetTempLevel')):
        v = val(key)
        print(f'        {label}��{(v if v is not None else '?')}')
    print('        ���� / ģʽ״̬��')
    for label, key in (('�����', 'refrigeratorDoorStatus'), ('�����2', 'refrigerator2DoorStatus'), ('�䶳��', 'freezerDoorStatus'), ('��������', 'vtRoomDoorStatus'), ('����ģʽ', 'intelligenceMode'), ('����ģʽ', 'travelMode'), ('ϸ��������', 'cellPreservationStatus')):
        print(f'        {label}��{bool_text(val(key))}')
    print('        ��ɱ�� / ҹ��ģʽ��')
    st = val('sterilizationTime')
    so = val('refSterilizationOffTime')
    print(f'        ɱ������/ֵ��{(st if st is not None else '?')} %')
    print(f'        ɱ���رռ�ʱ��{(so if so is not None else '?')} min')
    print(f'        ҹ��ģʽ��{bool_text(val('nightMode'))}')
    print(f'        ҹ�����ȣ�{(val('modeBrightness') if val('modeBrightness') is not None else '?')} / 50')
    print(f'        �ռ����ȣ�{(val('brightness') if val('brightness') is not None else '?')} / 100')
    print(f'        ҹ��ʱ�䣺{val('lightModeStartTime') or '?'} - {val('lightModeStopTime') or '?'}')
    unavailable = s.get('unavailable_fields') or []
    if unavailable:
        print(f'        ����֡˵������ǰ֡�� {s.get('raw_data_len')}B������ {len(unavailable)} ���°� Profile �ֶγ���֡���ȣ��Ѱ�ȫ������')
    print('        �T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T')

def _load_jsonl(path: str):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        return []
    return out

def _status_byte_map_from_record(rec: dict):
    try:
        parsed = rec['parsed']
        if parsed.get('kind') != 'full_status':
            return None
        table = parsed['status']['byte_table']
        return {int(x['offset']): int(x['dec']) for x in table}
    except Exception:
        return None

def diff_with_previous_snapshot(path: str, current_parsed: dict):
    if not path or current_parsed.get('kind') != 'full_status':
        return []
    current = {int(x['offset']): int(x['dec']) for x in current_parsed['status'].get('byte_table', [])}
    if not current:
        return []
    records = _load_jsonl(path)
    previous = None
    for rec in reversed(records):
        previous = _status_byte_map_from_record(rec)
        if previous:
            break
    if not previous:
        return []
    changes = []
    for off in sorted(set(previous) | set(current)):
        old = previous.get(off)
        new = current.get(off)
        if old != new:
            changes.append({'offset': off, 'old': old, 'new': new, 'old_hex': None if old is None else f'{old:02x}', 'new_hex': None if new is None else f'{new:02x}', 'delta': None if old is None or new is None else new - old})
    return changes
KNOWN_STATUS_OFFSETS = {0: 'refrigeratorTemperatureC', 1: 'freezerTemperatureC', 2: 'vtRoomTemperature', 4: 'envTemperature', 5: 'envHumidity', 6: 'refrigeratorTargetTempLevel', 7: 'freezerTargetTempLevel', 8: 'vtRoomTargetTempLevel', 9: 'vtRoom2TargetTempLevel', 15: 'door/status flags', 17: 'refrigerator2DoorStatus flags', 35: 'refSterilizationOffTime', 38: 'sterilizationTime(lo/first)', 39: 'sterilizationTime(hi/second)', 62: 'lightModeStopTime[0]', 63: 'lightModeStopTime[1]', 64: 'lightModeStartTime[0]', 65: 'lightModeStartTime[1]', 66: 'modeBrightness(raw)', 67: 'brightness(raw)', 68: 'nightMode'}

def print_snapshot_diff(changes: list[dict]):
    if not changes:
        print('        snapshot diff: no byte changes vs previous full-status snapshot')
        return
    print('        ���� changed bytes vs previous snapshot ����')
    for c in changes:
        name = KNOWN_STATUS_OFFSETS.get(c['offset'], 'UNKNOWN')
        delta = '' if c['delta'] is None else f', ��={c['delta']:+d}'
        print(f'        off {c['offset']:02d}  {name:30s}  {c['old_hex']}({c['old']}) -> {c['new_hex']}({c['new']}){delta}')

def append_snapshot(path: str, *, device_id: str, device_ip: str, session: int, uss_msg: dict, biz_sn: int, parsed: dict):
    rec = {'ts': int(time.time()), 'local_time': time.strftime('%Y-%m-%d %H:%M:%S'), 'deviceId': device_id, 'deviceIp': device_ip, 'session': session, 'uss': {'info_code': f'0x{uss_msg['info_code']:08x}', 'info_type': uss_msg['info_type'], 'sn': uss_msg['sn'], 'flag': uss_msg['flag']}, 'biz_sn': biz_sn, 'parsed': parsed}
    with open(path, 'a', encoding='utf-8') as fp:
        fp.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')

def print_uss_message(prefix: str, msg: dict, show_payload=False):
    print(f'{prefix} info=0x{msg['info_code']:08x} type={msg['info_type']} verByte=0x{msg['type_byte']:02x} flag={msg['flag']} sn={msg['sn']} session={msg['session']} payload={len(msg['payload'])}B')
    if show_payload and msg['payload']:
        print(f'    payload: {msg['payload'].hex(' ')}')

def probe_local_56800(ip: str, device_id: str, local_key: str, local_key_version: int | None, *, port: int=DEFAULT_LOCAL_PORT, pro_ver: int=2, connect_timeout: float=4.0, collect_seconds: float=3.0, show_secrets: bool=False, snapshot_log: str | None=DEFAULT_SNAPSHOT_LOG, show_complete_raw: bool=True, heartbeat_interval: float=SDK_HEARTBEAT_INTERVAL, heartbeat_enabled: bool=True, debug_raw: bool=False, coap_read_console: bool=False, stop_event=None, on_state=None, liveness_timeout=None, command_queue=None):
    if debug_raw:
        print('\n' + '=' * 72)
        print('[*] LAN 56800 V22')
        print(f'    target      = {ip}:{port}')
        print(f'    deviceId    = {device_id}')
        print(f'    LocalKey    = {(local_key if show_secrets else redact(local_key, 4))}')
        print(f'    cloud key v = {local_key_version}')
        print(f'    pro_ver     = {pro_ver}')
        print(f'    heartbeat   = {('enabled' if heartbeat_enabled else 'disabled')}')
        print('=' * 72)
    t0 = time.monotonic()
    try:
        s = socket.create_connection((ip, port), timeout=connect_timeout)
    except Exception as e:
        print(f'[!] TCP 56800 connect failed: {type(e).__name__}: {e}')
        return {'stage': 'local_tcp', 'error': repr(e)}
    print(f'[LAN] connected {ip}:{port} in {time.monotonic() - t0:.3f}s')
    pending_controls = {}
    try:
        hello = uss_hello(device_id, sn=1, pro_ver=pro_ver)
        if debug_raw:
            print(f'[>] HELLO {len(hello)}B: {hello.hex(' ')}')
        s.sendall(hello)
        try:
            resp, extra = uss_recv_one(s, connect_timeout)
        except Exception as e:
            print(f'[!] No decodable HELLO_RESP: {type(e).__name__}: {e}')
            return {'stage': 'hello_resp', 'error': repr(e)}
        if debug_raw:
            print_uss_message('[<] HELLO_RESP', resp, show_payload=True)
        if resp['info_type'] != USS_INFO_HELLO_RESP:
            print('[!] The peer answered, but not with uSS HELLO_RESP.')
            return {'stage': 'hello_resp', 'unexpected_info': resp['info_code'], 'raw': resp['raw'].hex()}
        if len(resp['payload']) >= 8:
            status, device_key_version = struct.unpack('>II', resp['payload'][:8])
        else:
            status, device_key_version = (0, 0)
        version_match = local_key_version is None or device_key_version == 0 or int(local_key_version) == int(device_key_version)
        print(f'[HS] session={resp['session']} status={status} keyver device={device_key_version} cloud={local_key_version} match={('yes' if version_match else 'NO')}')
        if status != 1:
            print('[!] Device explicitly rejected HELLO; stopping before HELLO_DONE.')
            return {'stage': 'hello_rejected', 'status': status, 'device_key_version': device_key_version}
        if not version_match:
            print('[!] Cloud key version and device version differ; do not decrypt with a stale key.')
            return {'stage': 'key_version_mismatch', 'device_key_version': device_key_version, 'cloud_key_version': local_key_version}
        type_byte = resp['type_byte'] or USS_TYPE_BYTE[pro_ver]
        done = uss_hello_done(2, resp['session'], type_byte)
        if debug_raw:
            print(f'[>] HELLO_DONE {len(done)}B: {done.hex(' ')}')
        s.sendall(done)
        try:
            done_resp, extra2 = uss_recv_one(s, connect_timeout)
        except Exception as e:
            print(f'[!] No decodable HELLO_DONE_RESP: {type(e).__name__}: {e}')
            return {'stage': 'hello_done_resp', 'session': resp['session'], 'device_key_version': device_key_version, 'error': repr(e)}
        if debug_raw:
            print_uss_message('[<] HELLO_DONE_RESP', done_resp, show_payload=True)
        if done_resp['info_type'] != USS_INFO_HELLO_DONE_RESP:
            print('[!] Expected HELLO_DONE_RESP; stopping.')
            return {'stage': 'hello_done_resp', 'unexpected_info': done_resp['info_code'], 'raw': done_resp['raw'].hex()}
        session_biz_sn = 0
        print(f'[HS] HELLO_DONE_RESP flag={done_resp['flag']} payload={len(done_resp['payload'])}B')
        if done_resp['payload']:
            try:
                crypto_sn, plain = biz_decrypt(done_resp['payload'], local_key)
                if len(plain) >= 4:
                    session_biz_sn = int.from_bytes(plain[:4], 'big')
                else:
                    session_biz_sn = int(crypto_sn)
                print(f'[HS] HELLO_DONE_RESP crypto_sn={crypto_sn} session_biz_sn={session_biz_sn} data={len(plain)}B')
                if debug_raw:
                    print(f'    data: {plain.hex(' ')}')
            except Exception as e:
                print(f'[!] HELLO_DONE_RESP decrypt failed: {e}')
        print(f'[LAN] session ready; listen={collect_seconds:.1f}s heartbeat={('off' if not heartbeat_enabled else f'{heartbeat_interval:.1f}s/plain-5DF2')}')
        s.settimeout(0.35)
        deadline = time.monotonic() + collect_seconds
        stream = bytearray(extra + extra2)
        frames = []
        decrypted = []
        next_uwt_seq = 1
        heartbeat_sent = 0
        heartbeat_decrypted_echoes = 0
        decrypt_failures = 0
        last_hb_sent = time.monotonic()
        last_rx = time.monotonic()
        state_cache = SessionStateCache()
        coap_queue = queue.Queue()
        coap_stop = threading.Event()
        next_coap_token = 10002
        next_coap_mid = 1
        next_coap_biz_sn = session_biz_sn
        next_coap_uss_sn = 0
        next_cae_counter = 1
        if coap_read_console:
            print('[READ] CAE/CoAP SDK-path probe enabled (first biz_sn=0, uSS_sn=0). Commands: read <profileProperty> | quit')

            def _coap_reader():
                while not coap_stop.is_set():
                    try:
                        line = input('read> ')
                    except (EOFError, KeyboardInterrupt):
                        break
                    coap_queue.put(line.strip())
            threading.Thread(target=_coap_reader, name='haier-coap-read-input', daemon=True).start()
        while time.monotonic() < deadline and not (stop_event and stop_event.is_set()):
            now = time.monotonic()
            if liveness_timeout and now - last_rx >= liveness_timeout:
                return {'stage': 'liveness_timeout', 'last_rx_age': now - last_rx, 'heartbeat_sent': heartbeat_sent, 'heartbeat_like_rx': heartbeat_decrypted_echoes}
            if coap_read_console:
                while True:
                    try:
                        cmdline = coap_queue.get_nowait()
                    except queue.Empty:
                        break
                    if not cmdline:
                        continue
                    lower = cmdline.lower()
                    if lower in ('quit', 'exit', 'q'):
                        coap_stop.set()
                        deadline = now
                        print('[READ] stopping session')
                        break
                    if not lower.startswith('read '):
                        print('[READ!] use: read refrigeratorTargetTempLevel')
                        continue
                    attr = cmdline[5:].strip()
                    if not attr:
                        print('[READ!] missing property name')
                        continue
                    try:
                        coap_pdu, cmeta = build_cae_attr_read_coap(device_id, attr, local_port=port, token_seed=next_coap_token, message_id=next_coap_mid)
                        packet = build_secure_coap_packet(coap_pdu, local_key, biz_sn=next_coap_biz_sn, uss_sn=next_coap_uss_sn, session=resp['session'], type_byte=type_byte)
                        s.sendall(packet)
                        print(f'[READ>] {attr} token={cmeta['token']} mid={cmeta['message_id']} biz_sn={next_coap_biz_sn} uss_sn=0 coap={len(coap_pdu)}B outer={len(packet)}B')
                        if debug_raw:
                            print(f'        CoAP={coap_pdu.hex(' ')}')
                            print(f'        uSS ={packet.hex(' ')}')
                        next_coap_token += 1
                        next_coap_mid = next_coap_mid + 1 & 65535
                        if next_coap_mid == 0:
                            next_coap_mid = 1
                        next_coap_biz_sn = next_coap_biz_sn + 1 & 4294967295
                        next_coap_uss_sn = 0
                    except Exception as e:
                        print(f'[READ!] {type(e).__name__}: {e}')
            if command_queue is not None:
                while True:
                    try:
                        command = command_queue.get_nowait()
                    except queue.Empty:
                        break
                    if not command or command.get('kind') != 'attr_write':
                        _complete_control_command(command, ok=False, error='unsupported_command')
                        continue
                    try:
                        from .protocol.epp import build_cae_op_request, build_old_epp_frame, wrap_cae_epp_envelope
                        name = str(command['name'])
                        wire = str(command.get('wire') or 'haismart')
                        decoder = current_decoder()
                        if decoder is None:
                            _complete_control_command(command, ok=False, error='profile_missing')
                            continue
                        built = decoder.encode_epp_write(name, command['value'])
                        attr_text = decoder.encode_write_value(name, command['value'])
                        command['expected'] = command['value']
                        command['meta'] = built
                        sizes = []
                        if wire in ('coap', 'both'):
                            coap_pdu, cmeta = build_cae_attr_write_coap(
                                device_id, name, attr_text, local_port=port,
                                token_seed=next_coap_token, message_id=next_coap_mid,
                            )
                            coap_packet = build_secure_coap_packet(
                                coap_pdu, local_key, biz_sn=next_coap_biz_sn,
                                uss_sn=next_coap_uss_sn, session=resp['session'], type_byte=type_byte,
                            )
                            s.sendall(coap_packet)
                            command['token'] = cmeta['token']
                            sizes.append(f'coap={len(coap_packet)}B biz_sn={next_coap_biz_sn}')
                            next_coap_token += 1
                            next_coap_mid = next_coap_mid + 1 & 65535
                            if next_coap_mid == 0:
                                next_coap_mid = 1
                            next_coap_biz_sn = next_coap_biz_sn + 1 & 4294967295
                        if wire in ('epp_enc', 'epp_plain', 'both', 'haismart'):
                            epp = build_old_epp_frame(built['frame_type'], built['epp_cmd'], built['param'])
                            if wire == 'haismart':
                                inner = build_cae_op_request(epp, device_id, next_cae_counter)
                                epp_packet = build_secure_coap_packet(
                                    inner, local_key, biz_sn=next_coap_biz_sn,
                                    uss_sn=0, session=resp['session'], type_byte=type_byte,
                                )
                                sizes.append(
                                    f'haismart={len(epp_packet)}B cae=2714 counter={next_cae_counter} biz_sn={next_coap_biz_sn}'
                                )
                                next_cae_counter += 2
                                next_coap_biz_sn = next_coap_biz_sn + 1 & 4294967295
                            elif wire == 'epp_plain':
                                epp_plain = wrap_cae_epp_envelope(epp)
                                epp_packet = uss_encode_info_code(
                                    USS_INFO_DATA_CODE, 0, epp_plain,
                                    type_byte=type_byte, flag=0, session=resp['session'],
                                )
                                sizes.append(f'{wire}={len(epp_packet)}B')
                            else:
                                epp_plain = wrap_cae_epp_envelope(epp)
                                epp_packet = build_secure_coap_packet(
                                    epp_plain, local_key, biz_sn=next_coap_biz_sn,
                                    uss_sn=0, session=resp['session'], type_byte=type_byte,
                                )
                                sizes.append(f'{wire}={len(epp_packet)}B biz_sn={next_coap_biz_sn}')
                                next_coap_biz_sn = next_coap_biz_sn + 1 & 4294967295
                            s.sendall(epp_packet)
                            if debug_raw:
                                print(f'        EPP={epp.hex(' ')}')
                        pending_controls[name] = command
                        print(
                            f'[WRITE>] wire={wire} {name} std={command['value']!r} json={attr_text!r} '
                            f'epp={built['epp_cmd']}:{built['param'].hex()} {" ".join(sizes)}'
                        )
                    except Exception as e:
                        _complete_control_command(command, ok=False, error=repr(e))
            if heartbeat_enabled and now - last_hb_sent >= heartbeat_interval:
                packet, inner_hb = build_uss_heartbeat(device_id, uwt_seq=next_uwt_seq, session=resp['session'], type_byte=type_byte)
                try:
                    s.sendall(packet)
                except Exception as e:
                    print(f'[HB!] send failed: {type(e).__name__}: {e}')
                    break
                heartbeat_sent += 1
                print(f'[HB>] seq={next_uwt_seq} cmd=5DF2 plain EAC4/flag0 len={len(packet)}B')
                if debug_raw:
                    print(f'      {packet.hex(' ')}')
                next_uwt_seq = next_uwt_seq + 1 & 4294967295
                last_hb_sent = now
            progressed = False
            while len(stream) >= 6:
                declared = struct.unpack('>H', stream[4:6])[0]
                total = 6 + declared
                if total < 16:
                    print(f'[!] stream desync: declared={declared}; raw={bytes(stream[:64]).hex(' ')}')
                    stream.clear()
                    break
                if len(stream) < total:
                    break
                raw_msg = bytes(stream[:total])
                del stream[:total]
                m = uss_decode_message(raw_msg)
                last_rx = time.monotonic()
                frames.append(m)
                if debug_raw:
                    print_uss_message('[<] PUSH', m)
                progressed = True
                if m['flag'] == 1 and m['payload']:
                    try:
                        bsn, plain = biz_decrypt(m['payload'], local_key)
                        decrypt_failures = 0
                        last_rx = time.monotonic()
                        coap_msg = parse_coap_message(plain)
                        if coap_msg is not None:
                            code_text = f'{coap_msg['code_class']}.{coap_msg['code_detail']:02d}'
                            payload = coap_msg['payload']
                            try:
                                payload_text = payload.decode('utf-8')
                            except Exception:
                                payload_text = payload.hex()
                            if len(payload_text) > 220:
                                payload_text = payload_text[:217] + '...'
                            token_text = coap_msg['token'].decode('ascii', 'replace')
                            print(f'[READ<] CoAP {code_text} mid={coap_msg['message_id']} token={token_text} payload={payload_text or '<empty>'}')
                            if debug_raw:
                                print(f'        plain={plain.hex(' ')}')
                            pending = next(
                                (item for item in pending_controls.values() if item.get('token') == token_text),
                                pending_controls.get(token_text),
                            )
                            if pending is not None and coap_msg['code'] != 0:
                                pending['coap'] = {'code': code_text, 'payload': payload_text, 'token': token_text}
                                if coap_msg['code_class'] != 2:
                                    pending_controls.pop(str(pending.get('name') or ''), None)
                                    _complete_control_command(
                                        pending, ok=False, error=f'CoAP {code_text}',
                                        coap=pending['coap'], token=token_text,
                                    )
                                else:
                                    pending['coap_accepted'] = True
                                    print(f'[WRITE<] CoAP accepted {pending.get('name')} {code_text}')
                            decrypted.append({'uss_info_code': m['info_code'], 'uss_sn': m['sn'], 'biz_sn': bsn, 'data': plain, 'epp': None, 'parsed': {'kind': 'coap', 'coap': coap_msg}})
                            continue
                        if len(plain) >= 4 and struct.unpack('>I', plain[:4])[0] in (UWT_HEARTBEAT_CMD, 24051):
                            heartbeat_decrypted_echoes += 1
                            hb_seq = struct.unpack('>I', plain[8:12])[0] if len(plain) >= 12 else None
                            print(f'[HB<] encrypted heartbeat-like frame biz_sn={bsn} seq={hb_seq} len={len(plain)}B')
                            decrypted.append({'uss_info_code': m['info_code'], 'uss_sn': m['sn'], 'biz_sn': bsn, 'data': plain, 'epp': None, 'parsed': {'kind': 'uwt_heartbeat', 'uwt_seq': hb_seq}})
                            continue
                        summary = epp_summary(plain)
                        parsed = parse_fridge_payload(plain)
                        if on_state is not None and parsed.get('kind') not in ('unknown', 'uwt_heartbeat'):
                            on_state(parsed)
                        decrypted.append({'uss_info_code': m['info_code'], 'uss_sn': m['sn'], 'biz_sn': bsn, 'data': plain, 'epp': summary, 'parsed': parsed})
                        if parsed.get('kind') == 'full_status':
                            state_cache.apply_snapshot(parsed)
                            _resolve_pending_writes(pending_controls, state_cache.fields)
                            print(compact_fridge_line(parsed))
                        elif parsed.get('kind') == 'change_status':
                            applied = state_cache.apply_changes(parsed)
                            _resolve_pending_writes(pending_controls, state_cache.fields)
                            print(compact_change_line(applied, state_cache))
                        else:
                            print(compact_fridge_line(parsed))
                        if debug_raw:
                            print(f'    [+] decrypt OK: biz_sn={bsn}, data={len(plain)}B')
                            if summary:
                                print(f'        EPP frame_type=0x{summary['frame_type']:02x} cmd={summary['command']} length={summary['length']}B')
                            if show_complete_raw:
                                print_complete_protocol_payloads(plain, parsed)
                            if parsed.get('kind') == 'change_status':
                                print(f'    6C01 data={parsed.get('raw_hex')}')
                                for ch in parsed.get('changes') or []:
                                    print(f'    attr={ch['attr_id']} off={ch['offset']} name={ch['name']} raw={ch['raw_hex']} value={ch['value']}')
                            print_fridge_status(parsed)
                            print_fridge_chinese_details(parsed)
                            if snapshot_log and parsed.get('kind') == 'full_status':
                                changes = diff_with_previous_snapshot(snapshot_log, parsed)
                                print_snapshot_diff(changes)
                        if snapshot_log:
                            append_snapshot(snapshot_log, device_id=device_id, device_ip=ip, session=resp['session'], uss_msg=m, biz_sn=bsn, parsed=parsed)
                    except Exception as e:
                        if not isinstance(e, UnicodeError):
                            decrypt_failures += 1
                            if decrypt_failures >= 3:
                                return {'stage': 'local_key_invalid', 'decrypt_failures': decrypt_failures, 'error': repr(e)}
                        print(f'    [!] decrypt failed: {e}')
                elif m['payload']:
                    payload = m['payload']
                    uwt_cmd = struct.unpack('>I', payload[:4])[0] if len(payload) >= 4 else None
                    if uwt_cmd == 24051:
                        heartbeat_decrypted_echoes += 1
                        hb_seq = struct.unpack('>I', payload[8:12])[0] if len(payload) >= 12 else None
                        print(f'[HB<] ACK cmd=5DF3 seq={hb_seq} len={len(payload)}B')
                    else:
                        print(f'[RX] plaintext cmd={uwt_cmd!s} len={len(payload)}B')
                        if debug_raw:
                            print(f'     {payload.hex(' ')}')
            try:
                chunk = s.recv(4096)
                if not chunk:
                    print(f'[LAN] peer closed after {time.monotonic() - t0:.2f}s')
                    break
                stream += chunk
            except socket.timeout:
                if not progressed:
                    continue
            except Exception as e:
                print(f'[!] receive error: {type(e).__name__}: {e}')
                break
        coap_stop.set()
        _fail_pending_controls(pending_controls, 'session_closed')
        if debug_raw:
            print('\n[*] LAN probe summary')
            print(f'    session             = {resp['session']}')
            print(f'    device key version  = {device_key_version}')
            print(f'    cloud key version   = {local_key_version}')
            print(f'    pushed uSS frames   = {len(frames)}')
            print(f'    decrypted biz frames= {len(decrypted)}')
            print(f'    heartbeat sent      = {heartbeat_sent}')
            print(f'    heartbeat-like rx   = {heartbeat_decrypted_echoes}')
            if heartbeat_enabled:
                print(f'    last RX age         = {time.monotonic() - last_rx:.2f}s')
        return {'stage': 'local_done', 'session': resp['session'], 'type_byte': type_byte, 'device_key_version': device_key_version, 'cloud_key_version': local_key_version, 'version_match': version_match, 'push_frames': len(frames), 'decrypted_frames': len(decrypted), 'heartbeat_sent': heartbeat_sent, 'heartbeat_like_rx': heartbeat_decrypted_echoes, 'heartbeat_interval': heartbeat_interval if heartbeat_enabled else None, 'epp': [x['epp'] for x in decrypted if x['epp']], 'parsed_kinds': [x['parsed'].get('kind') for x in decrypted], 'snapshot_log': snapshot_log}
    finally:
        try:
            s.close()
        except Exception:
            pass
        _fail_pending_controls(pending_controls, 'session_closed')

def load_key_cache(path: str, device_id: str):
    p = Path(path)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'[!] Failed to read key cache {path}: {e}')
        return None
    if isinstance(obj.get('devices'), dict):
        item = obj['devices'].get(device_id)
    elif obj.get('deviceId') == device_id:
        item = obj
    else:
        item = None
    if not isinstance(item, dict):
        return None
    key = item.get('localKey') or item.get('key')
    version = item.get('localKeyVers') or item.get('version') or item.get('vers')
    if not key:
        return None
    try:
        version = int(version) if version is not None else None
    except Exception:
        pass
    return {'stage': 'done', 'key': str(key), 'version': version, 'source': 'cache', 'cache_file': str(p)}

def save_key_cache(path: str, device_id: str, key: str, version):
    p = Path(path)
    obj = {'devices': {}}
    if p.exists():
        try:
            old = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(old, dict):
                if isinstance(old.get('devices'), dict):
                    obj = old
                elif old.get('deviceId'):
                    old_id = str(old.get('deviceId'))
                    obj = {'devices': {old_id: {'localKey': old.get('localKey') or old.get('key'), 'localKeyVers': old.get('localKeyVers') or old.get('version'), 'savedAt': old.get('savedAt')}}}
        except Exception:
            pass
    obj.setdefault('devices', {})
    obj['devices'][device_id] = {'localKey': key, 'localKeyVers': version, 'savedAt': int(time.time())}
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[+] LocalKey cache updated: {p}')

def result_from_manual_key(key: str, version):
    try:
        version = int(version) if version is not None else None
    except Exception:
        pass
    return {'stage': 'done', 'key': key, 'version': version, 'source': 'manual'}

def show_snapshot_history(path: str):
    records = _load_jsonl(path)
    full = [r for r in records if r.get('parsed', {}).get('kind') == 'full_status']
    if not full:
        print(f'[!] No full_status records in {path}')
        return
    print(f'[*] {len(full)} full-status snapshots in {path}')
    prev_map = None
    prev_time = None
    for idx, rec in enumerate(full):
        cur = _status_byte_map_from_record(rec)
        tm = rec.get('local_time') or rec.get('ts')
        if prev_map is None:
            print(f'    #{idx + 1} {tm}: baseline')
        else:
            changes = []
            for off in sorted(set(prev_map) | set(cur or {})):
                old = prev_map.get(off)
                new = (cur or {}).get(off)
                if old != new:
                    changes.append({'offset': off, 'old': old, 'new': new, 'old_hex': None if old is None else f'{old:02x}', 'new_hex': None if new is None else f'{new:02x}', 'delta': None if old is None or new is None else new - old})
            print(f'    #{idx + 1} {tm}: {len(changes)} changed byte(s)')
            for c in changes:
                name = KNOWN_STATUS_OFFSETS.get(c['offset'], 'UNKNOWN')
                delta = '' if c['delta'] is None else f' ��={c['delta']:+d}'
                print(f'       off {c['offset']:02d} {name:30s} {c['old_hex']}({c['old']}) -> {c['new_hex']}({c['new']}){delta}')
        prev_map = cur
        prev_time = tm

def main():
    ap = argparse.ArgumentParser()
    auth = ap.add_mutually_exclusive_group(required=False)
    auth.add_argument('--phone')
    auth.add_argument('--token')
    ap.add_argument('--password')
    ap.add_argument('--client-id', help='China HTTP clientId when using --token; normally phone')
    ap.add_argument('--device-id', required=True, help='Haier module deviceId')
    ap.add_argument('--key-cache', default=DEFAULT_KEY_CACHE, help='Local LocalKey cache JSON; default haier_localkey.json')
    ap.add_argument('--auth-cache', default=DEFAULT_AUTH_CACHE, help='Cached Haier HTTP token/clientId JSON; default haier_auth_cache.json')
    ap.add_argument('--refresh-auth', action='store_true', help='Ignore cached HTTP token and perform account login again')
    ap.add_argument('--local-key', help='Use this LocalKey directly; skips Haier cloud login/MQTT')
    ap.add_argument('--local-key-version', type=int, help='Version for --local-key')
    ap.add_argument('--refresh-key', action='store_true', help='Force cloud login/MQTT and refresh the cached LocalKey')
    ap.add_argument('--no-key-save', action='store_true', help='Do not save a freshly fetched LocalKey to --key-cache')
    ap.add_argument('--device-ip', required=True, help='LAN appliance IP')
    ap.add_argument('--local-port', type=int, default=DEFAULT_LOCAL_PORT)
    ap.add_argument('--local-timeout', type=float, default=4.0)
    ap.add_argument('--collect-seconds', type=float, default=60.0, help='Per-session receive window; V22 sends the SDK-derived heartbeat during this window')
    ap.add_argument('--heartbeat-interval', type=float, default=SDK_HEARTBEAT_INTERVAL, help='UWT heartbeat interval in seconds; SDK behavior is about 5 seconds')
    ap.add_argument('--no-heartbeat', action='store_true', help='Disable V22 UWT heartbeat for A/B comparison')
    ap.add_argument('--once', action='store_true', help='Run one 56800 session and exit')
    ap.add_argument('--reconnect-delay', type=float, default=0.5, help='Delay before reconnect after fridge closes session')
    ap.add_argument('--max-runtime', type=float, default=0.0, help='Stop persistent mode after N seconds; 0 means until Ctrl+C')
    ap.add_argument('--snapshot-log', default=DEFAULT_SNAPSHOT_LOG, help='Append parsed status/alarm snapshots as JSONL; empty string disables')
    ap.add_argument('--show-snapshot-history', action='store_true', help='Print all full-status byte changes in the existing snapshot log and exit')
    ap.add_argument('--no-complete-raw', action='store_true', help='Do not print full decrypted/EPP/EPP-data hex dumps (v12 default: print all)')
    ap.add_argument('--debug-raw', action='store_true', help='Restore verbose uSS/decrypted/EPP/profile debug output')
    ap.add_argument('--coap-read-console', action='store_true', help='Enable V22 read-only CAE/CoAP attribute probe console')
    ap.add_argument('--pro-ver', type=int, choices=(2, 3), default=2)
    ap.add_argument('--skip-lan', action='store_true', help='Only fetch LocalKey; do not connect to TCP 56800')
    ap.add_argument('--show-secrets', action='store_true', help='Print full LocalKey in the LAN section')
    ap.add_argument('--profile-json', default=None, help='Haier profile/config JSON. Default: auto-select haier_profile_2.0.46.json beside the script')
    ap.add_argument('--no-profile', action='store_true', help='Disable JSON profile decoder and fall back to legacy v13 refrigerator parser')
    ap.add_argument('--host', default=DEFAULT_HOST, help='TLS hostname/SNI, default gw.haier.net')
    ap.add_argument('--connect-ip', help='Connect to this IP but keep --host as TLS SNI. Useful for replaying an endpoint observed in a pcap.')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT, help='MQTT/TLS gateway port. Default: 56811 for current gw.haier.net DNS-resolved IPs; use 56212 for legacy endpoints if needed')
    ap.add_argument('--mqtt-client-id')
    ap.add_argument('--mqtt-username')
    ap.add_argument('--mqtt-password')
    ap.add_argument('--username-body', help='Pin the 8-digit derived-auth body for reproducibility')
    ap.add_argument('--legacy-tls', action='store_true', help="Lower OpenSSL security level for Haier's legacy TLS")
    ap.add_argument('--insecure-legacy-tls', action='store_true', help="Also disable certificate-chain verification for Haier's private/self-signed chain; TLS encryption and SNI remain enabled, and peer SHA256 is printed")
    ap.add_argument('--timeout', type=float, default=12.0)
    args = ap.parse_args()
    if args.heartbeat_interval <= 0:
        ap.error('--heartbeat-interval must be > 0')
    global PROFILE_DECODER, PROFILE_PATH
    if not args.no_profile:
        PROFILE_PATH = choose_profile_file(args.profile_json, base_dir=Path(__file__).resolve().parent)
        if PROFILE_PATH is None:
            if args.profile_json:
                ap.error(f'Profile JSON not found: {args.profile_json}')
            print('[!] No Haier profile JSON found; using legacy v13 refrigerator parser.')
        else:
            try:
                PROFILE_DECODER = HaierProfileDecoder.from_file(PROFILE_PATH)
                print(f'[+] Loaded Haier profile: {PROFILE_PATH} (Version={PROFILE_DECODER.version}, name={PROFILE_DECODER.profile_name})')
                if PROFILE_DECODER.version != '2.0.46':
                    print('[!] Note: current confirmed refrigerator profile is Version 2.0.46; this file differs.')
            except Exception as e:
                ap.error(f'Unable to load profile JSON {PROFILE_PATH}: {e}')
    result = None
    if args.local_key and (not args.refresh_key):
        result = result_from_manual_key(args.local_key, args.local_key_version)
        print('[+] Using LocalKey supplied on command line; cloud login skipped.')
    elif not args.refresh_key:
        result = load_key_cache(args.key_cache, args.device_id)
        if result:
            print(f'[+] Loaded LocalKey from cache: {args.key_cache}')
            print(f'    key     = {redact(result['key'], 4)}')
            print(f'    version = {result.get('version')}')
            print('[+] Cloud login/MQTT skipped.')
    if result is None:
        sess = requests.Session()
        auth_source = None
        cached_auth = None if args.refresh_auth else load_auth_cache(args.auth_cache)
        if args.token:
            if not args.client_id:
                ap.error('--token requires --client-id')
            client_id, token = (args.client_id, args.token)
            auth_source = 'command_line_token'
        elif args.phone and (args.password or args.refresh_auth):
            if not args.password:
                if sys.stdin.isatty():
                    args.password = getpass.getpass('Haier account password: ')
                else:
                    ap.error('--phone requires --password when --refresh-auth is used')
            client_id, token = login(sess, args.phone, args.password)
            save_auth_cache(args.auth_cache, client_id, token, args.phone)
            auth_source = 'login'
        elif cached_auth:
            client_id = cached_auth['client_id']
            token = cached_auth['token']
            auth_source = 'cache'
            print(f'[+] Loaded HTTP auth from cache: {args.auth_cache}')
        elif args.phone:
            client_id, token = interactive_login(sess, args.phone)
            save_auth_cache(args.auth_cache, client_id, token, args.phone)
            auth_source = 'interactive_login'
        else:
            try:
                client_id, token = interactive_login(sess, None)
            except RuntimeError as e:
                ap.error(str(e))
            save_auth_cache(args.auth_cache, client_id, token, client_id)
            auth_source = 'interactive_login'
        print(f'[+] HTTP clientId={client_id}')
        print(f'[+] token={redact(token)}')
        print(f'[+] HTTP auth source={auth_source}')
        try:
            device_list(sess, token, client_id, validate_auth=True)
        except PermissionError as e:
            if auth_source != 'cache':
                raise
            print(f'[!] Cached HTTP token is no longer valid: {e}')
            clear_auth_cache(args.auth_cache)
            phone_hint = (cached_auth or {}).get('phone') or args.phone or client_id
            if args.password and phone_hint:
                client_id, token = login(sess, phone_hint, args.password)
            else:
                try:
                    client_id, token = interactive_login(sess, phone_hint)
                except RuntimeError:
                    ap.error('Cached Haier token expired. Re-run once with --phone <account> --password <password> --refresh-auth --refresh-key. The new token will then be cached automatically.')
            save_auth_cache(args.auth_cache, client_id, token, phone_hint)
            print(f'[+] HTTP clientId={client_id}')
            print(f'[+] token={redact(token)}')
            print('[+] HTTP auth source=renewed_login')
            device_list(sess, token, client_id, validate_auth=True)
        mqtt_client_id = args.mqtt_client_id or default_mqtt_client_id(client_id)
        if args.mqtt_username and args.mqtt_password:
            username = args.mqtt_username
            password = args.mqtt_password
            print('[*] using explicitly supplied MQTT auth')
        else:
            body, username, password = derive_gateway_auth(args.username_body)
            print('[*] using ONE experimental haier_sdk-derived auth attempt')
            print(f'    username body={body}')
            print(f'    username={username}')
            print(f'    password={redact(password)}')
        print(f'[*] mqtt clientId={mqtt_client_id}')
        result = run_gateway(args.host, args.port, mqtt_client_id, username, password, token, args.device_id, args.timeout, args.connect_ip, args.legacy_tls, args.insecure_legacy_tls)
        if result.get('stage') == 'done' and result.get('key') and (not args.no_key_save):
            save_key_cache(args.key_cache, args.device_id, str(result['key']), result.get('version'))
    print('\n[*] LocalKey result:')
    safe_result = dict(result)
    if 'key' in safe_result:
        safe_result['key'] = safe_result['key'] if args.show_secrets else redact(safe_result['key'], 4)
    if isinstance(safe_result.get('inner'), dict):
        safe_result['inner'] = dict(safe_result['inner'])
        if 'key' in safe_result['inner'] and (not args.show_secrets):
            safe_result['inner']['key'] = redact(safe_result['inner']['key'], 4)
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    if result.get('stage') != 'done' or not result.get('key'):
        print('[!] LocalKey was not obtained, so LAN 56800 stage is skipped.')
        return
    if args.skip_lan:
        print('[i] --skip-lan set; stopping after LocalKey.')
        return

    def run_one_local_session():
        return probe_local_56800(args.device_ip, args.device_id, str(result['key']), result.get('version'), port=args.local_port, pro_ver=args.pro_ver, connect_timeout=args.local_timeout, collect_seconds=args.collect_seconds, show_secrets=args.show_secrets, snapshot_log=args.snapshot_log or None, show_complete_raw=args.debug_raw and (not args.no_complete_raw), heartbeat_interval=args.heartbeat_interval, heartbeat_enabled=not args.no_heartbeat, debug_raw=args.debug_raw, coap_read_console=args.coap_read_console)
    if args.once:
        lan_result = run_one_local_session()
        print('\n[*] final LAN result:')
        print(json.dumps(lan_result, ensure_ascii=False, indent=2))
        return
    print(f'[LISTEN] reconnect=on delay={args.reconnect_delay:.2f}s heartbeat={('off' if args.no_heartbeat else f'{args.heartbeat_interval:.1f}s/plain-5DF2')} (Ctrl+C stop)')
    started = time.monotonic()
    session_no = 0
    last_result = None
    try:
        while True:
            if args.max_runtime > 0 and time.monotonic() - started >= args.max_runtime:
                print('[i] max runtime reached')
                break
            session_no += 1
            print(f'[SESSION] #{session_no}')
            t0 = time.monotonic()
            try:
                last_result = run_one_local_session()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                last_result = {'stage': 'listener_exception', 'error': repr(e)}
                print(f'[!] local session exception: {type(e).__name__}: {e}')
            elapsed = time.monotonic() - t0
            stage = (last_result or {}).get('stage')
            if args.debug_raw:
                print(f'[SESSION] #{session_no} ended {elapsed:.2f}s stage={stage}')
            if stage == 'key_version_mismatch':
                print('[!] Appliance LocalKey version changed; refresh key before reconnecting.')
                break
            if stage == 'hello_rejected':
                print('[!] HELLO rejected; stopping automatic reconnect.')
                break
            if args.reconnect_delay > 0:
                if args.debug_raw:
                    print(f'[LAN] reconnect in {args.reconnect_delay:.2f}s')
                time.sleep(args.reconnect_delay)
    except KeyboardInterrupt:
        print('\n[i] Ctrl+C received; persistent listener stopped.')
    print('\n[*] persistent listener summary')
    print(f'    sessions opened = {session_no}')
    print(f'    runtime         = {time.monotonic() - started:.1f}s')
    if last_result is not None:
        print(f'    last stage      = {last_result.get('stage')}')
if __name__ == '__main__':
    main()

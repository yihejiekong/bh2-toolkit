# -*- coding: utf-8 -*-
"""崩坏学园2 独立客户端协议层（无游戏、无模拟器）。

帧格式
------
    [4B 大端总长(含自身)] + [30B 头] + [8B 尾] + [载荷]
    头 = cmd:u16 | 0xea60:u16 | 00000000 | 会话号(4B) | 14B 零
    尾 = 时间戳:u32 | 校验:u32
    校验 = ~CRC32_reflected(poly=0xEDB88321, init=0x5E0600BE,
                           data = 帧前 30 字节 + 8 个 0 + 载荷)

时间戳 = 真实 unix 秒 + 2006083400（服务器只校验「不太离谱」，±60s 都能过）。

凭据从哪来
----------
本文件不含任何账号信息。每个区服需要 4 个参数：网关地址、会话号、
客户端常量 own_uid、登录帧（十六进制）。这些只能由你自己抓包得到，
放进 ``servers.json``（与本次提交无关，已在 .gitignore 里）：

    {
      "b2": {
        "name": "B服",
        "host": "网关地址",
        "session": "01234567",
        "own_uid": "0x0001A407",
        "login_hex": "000000f0..."
      }
    }

也可以用环境变量 ``BH2_SERVERS`` 指向别的配置文件路径。

抓包与取参的方法见 docs/05-玩家名片协议.md。
"""
import json
import os
import socket
import struct
import time

PORT = int(os.environ.get('BH2_PORT', '26001'))
CRC_POLY = 0xEDB88321
CRC_INIT = 0x5E0600BE
TS_OFFSET = 2006083400

# 登录后立即发送的初始化序列（抓包原样，载荷 = own_uid + 后缀）
_PRIME_TAIL = [
    (0x2410, '082a'), (0x2410, '0811'), (0x2410, '081a'),
    (0x2410, '081e'), (0x2410, '0816'), (0x2410, '0817'),
    (0x0023, '00000000'), (0x0046, ''), (0x0063, '00'),
]

_TAB = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (CRC_POLY if _c & 1 else 0)
    _TAB.append(_c & 0xFFFFFFFF)


def crc32(data, init=CRC_INIT):
    c = init
    for b in data:
        c = (c >> 8) ^ _TAB[(c ^ b) & 0xFF]
    return (~c) & 0xFFFFFFFF


class Server:
    """一个区服的连接参数。"""

    def __init__(self, key, name, host, session_hex, own_uid, login_hex):
        self.key = key
        self.name = name
        self.host = host
        self.port = PORT
        self.session = bytes.fromhex(session_hex)
        self.own_uid = int(own_uid, 0) if isinstance(own_uid, str) else own_uid
        self.login_frame = bytes.fromhex(login_hex)

    # ---- 组帧 ----
    def build(self, cmd, payload, f2=0xEA60, ts=None):
        ln = 38 + len(payload)
        head = (struct.pack('>I', ln) + struct.pack('>HH', cmd, f2)
                + b'\x00' * 4 + self.session + b'\x00' * 14)
        body = head + b'\x00' * 8 + payload
        mac = crc32(body)
        ts = (int(time.time()) + TS_OFFSET) & 0xFFFFFFFF if ts is None else ts
        return body[:30] + struct.pack('>II', ts, mac) + payload

    def resign(self, frame, payload=None):
        payload = frame[38:] if payload is None else payload
        cmd, f2 = struct.unpack('>HH', frame[4:8])
        return self.build(cmd, payload, f2)

    # ---- 业务帧 ----
    def search(self, uid):
        """0x0029：名片摘要请求。"""
        return self.build(0x0029, struct.pack('>II', self.own_uid, uid) + b'\x00')

    def detail(self, uid):
        """0x02b2：名片详情（展示栏 / 成就 / 履历）。"""
        return self.build(0x02B2, struct.pack('>II', self.own_uid, uid))

    def heartbeat(self, n):
        """0x0005：心跳，n 是本次会话累计秒数。"""
        return (0x0005, struct.pack('>II', self.own_uid, n & 0xFFFFFFFF))

    def prime(self):
        u = struct.pack('>I', self.own_uid)
        return [(cmd, u + bytes.fromhex(tail)) for cmd, tail in _PRIME_TAIL]

    def client(self, timeout=10.0):
        return Client(self, timeout=timeout)

    def __repr__(self):
        return '<Server %s %s:%d>' % (self.key, self.host, self.port)


def _conf_path():
    return os.environ.get('BH2_SERVERS') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'servers.json')


def load_servers():
    """读 servers.json；文件不存在就返回空字典（调用方负责给出提示）。"""
    path = _conf_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        conf = json.load(f)
    out = {}
    for key, v in conf.items():
        out[key] = Server(key, v.get('name', key), v['host'], v['session'],
                          v['own_uid'], v['login_hex'])
    return out


SERVERS = load_servers()
DEFAULT = os.environ.get('BH2_SERVER_DEFAULT') or (
    'b2' if 'b2' in SERVERS else (next(iter(SERVERS), '')))


def get(key):
    key = (key or DEFAULT or '').lower()
    if key in SERVERS:
        return SERVERS[key]
    if SERVERS:
        return SERVERS[DEFAULT]
    raise RuntimeError(
        '还没有配置区服参数：请把抓包得到的 host/session/own_uid/login_hex '
        '写进 %s（格式见本文件顶部注释）' % _conf_path())


class Client:
    def __init__(self, srv=None, host=None, port=None, timeout=10.0):
        self.srv = srv or get(None)
        host = host or self.srv.host
        port = port or self.srv.port
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b''
        self.last_frame = b''

    def send(self, data):
        self.sock.sendall(data)

    def login(self):
        self.send(self.srv.resign(self.srv.login_frame))

    def frames(self, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            while len(self.buf) >= 4:
                ln = struct.unpack('>I', self.buf[:4])[0]
                if ln < 8 or ln > 1 << 22 or len(self.buf) < ln:
                    break
                fr = self.buf[:ln]
                self.buf = self.buf[ln:]
                self.last_frame = fr
                cmd, f2 = struct.unpack('>HH', fr[4:8])
                yield cmd, f2, fr[38:]
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return
            if not chunk:
                return
            self.buf += chunk

    def drain(self, seconds):
        n = 0
        for _ in self.frames(seconds):
            n += 1
        return n

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

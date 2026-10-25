# -*- coding: utf-8 -*-
"""常驻查询服务：为每个区服保持一条已登录的游戏网关连接，按 UID 取名片原始载荷。

HTTP（只监听 127.0.0.1:8791）
  GET /pull?uid=12345678&srv=b2   -> {"ok":1,"sum":"<hex>","det":"<hex>"}
  GET /status                     -> {"ok":1,"servers":{"b2":{...},"gf":{...}}}

设计要点：
  - 登录只在进程启动 / 连接断开时做一次，查询全部复用同一条连接
    （避免每次查询都重新登录被风控）
  - 15 秒一次 0x0005 心跳（与真实客户端一致），失败即重连
"""
import json
import os
import socket
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from . import proto
except ImportError:                     # 直接 python service.py 跑
    import proto

LOG = os.environ.get('BH2_QUERY_LOG') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bh2-query.log')
BIND = os.environ.get('BH2_QUERY_BIND', '127.0.0.1')
PORT = int(os.environ.get('BH2_QUERY_PORT', '8791'))
KEEPALIVE_SEC = int(os.environ.get('BH2_KEEPALIVE', '15'))


def log(msg):
    line = time.strftime('[%Y-%m-%d %H:%M:%S] ') + msg
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


class Session:
    def __init__(self, srv):
        self.srv = srv
        self.lock = threading.Lock()
        self.cli = None
        self.relogins = 0
        self.logins_failed = 0
        self.last_ok = 0.0
        self.last_err = ''
        self.last_cmd = 0
        self.last_len = 0
        self.started = time.time()

    def _tag(self):
        return '[%s]' % self.srv.key

    # ---------- 连接管理 ----------
    def _connect_locked(self):
        if self.cli is not None:
            self.cli.close()
            self.cli = None
        log('%s [login] 连接 %s:%d' % (self._tag(), self.srv.host, self.srv.port))
        c = self.srv.client()
        c.login()
        self.relogins += 1
        n = c.drain(6.0)
        log('%s [login] 收到 %d 帧' % (self._tag(), n))
        if n == 0:
            c.close()
            raise RuntimeError('登录无回应（登录帧可能已过期，需要重新抓包）')
        for cmd, payload in self.srv.prime():
            c.send(self.srv.build(cmd, payload))
            time.sleep(0.05)
        time.sleep(0.5)
        c.drain(1.2)
        self.cli = c
        self.last_ok = time.time()
        log('%s [login] 就绪 relogins=%d' % (self._tag(), self.relogins))

    def _drop_locked(self):
        if self.cli is not None:
            try:
                self.cli.close()
            except Exception:
                pass
            self.cli = None

    def _exchange_locked(self, frame, want, timeout=4.0):
        self.cli.send(frame)
        for cmd, _f2, pl in self.cli.frames(timeout):
            if cmd == want:
                self.last_cmd = cmd
                self.last_len = len(pl) + 38
                return pl
        return None

    # ---------- 对外 ----------
    def pull(self, uid):
        with self.lock:
            if self.cli is None:
                self._connect_locked()
            for attempt in (1, 2):
                try:
                    summ = self._exchange_locked(self.srv.search(uid), 0x002A)
                    det = self._exchange_locked(self.srv.detail(uid), 0x02B3)
                except (OSError, socket.timeout) as e:
                    log('%s [pull] 连接异常 %r，重连' % (self._tag(), e))
                    self._drop_locked()
                    if attempt == 2:
                        raise
                    self._connect_locked()
                    continue
                if summ and det:
                    self.last_ok = time.time()
                    self.last_err = ''
                    return summ, det
                log('%s [pull] uid=%d 回应不全 sum=%s det=%s'
                    % (self._tag(), uid, bool(summ), bool(det)))
                self._drop_locked()
                if attempt == 2:
                    self.last_err = '回应不全'
                    raise RuntimeError('服务器未返回完整名片（可能被限流或会话失效）')
                self._connect_locked()
            raise RuntimeError('pull failed')

    def keepalive_loop(self):
        fails = 0
        hb = 0
        while True:
            time.sleep(KEEPALIVE_SEC if self.cli is not None else 30)
            need = False
            with self.lock:
                if self.cli is None:
                    need = True
                else:
                    try:
                        hb += KEEPALIVE_SEC
                        self.cli.send(self.srv.build(*self.srv.heartbeat(hb)))
                        self.cli.drain(1.0)
                    except Exception as e:  # noqa: BLE001
                        log('%s [keepalive] 异常 %r，标记重连' % (self._tag(), e))
                        self._drop_locked()
                        need = True
            if need:
                with self.lock:
                    try:
                        self._connect_locked()
                        fails = 0
                        hb = 0
                        self.last_err = ''
                        log('%s [keepalive] 已重连 relogins=%d' % (self._tag(), self.relogins))
                    except Exception as e:  # noqa: BLE001
                        fails += 1
                        self.last_err = '重连失败: %s' % (e,)
                        log('%s [keepalive] 重连失败第 %d 次：%r' % (self._tag(), fails, e))

    def status(self):
        return {
            'srv': self.srv.key,
            'name': self.srv.name,
            'connected': self.cli is not None,
            'relogins': self.relogins,
            'last_ok': self.last_ok,
            'last_err': self.last_err,
            'uptime': int(time.time() - self.started),
            'host': self.srv.host,
        }


SESS = {k: Session(v) for k, v in proto.SERVERS.items()}


def sess(key):
    s = SESS.get((key or proto.DEFAULT).lower())
    if s is None:
        raise KeyError('未知区服：%s（可选 %s）' % (key, '/'.join(SESS)))
    return s


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, qs = self.path.partition('?')
        params = dict(p.split('=', 1) for p in qs.split('&') if '=' in p)
        if path == '/status':
            return self._json(dict(ok=1, servers={k: v.status() for k, v in SESS.items()}))
        if path == '/pull':
            uid = params.get('uid', '')
            if not uid.isdigit():
                return self._json({'ok': 0, 'err': 'uid 非法'}, 400)
            try:
                S = sess(params.get('srv'))
            except KeyError as e:
                return self._json({'ok': 0, 'err': str(e)}, 400)
            t0 = time.time()
            try:
                summ, det = S.pull(int(uid))
            except Exception as e:  # noqa: BLE001
                log('%s [pull] uid=%s 失败 %r\n%s'
                    % (S.srv.key, uid, e, traceback.format_exc()[-800:]))
                return self._json({'ok': 0, 'err': str(e)}, 502)
            log('[pull] srv=%s uid=%s ok sum=%dB det=%dB(frame %d) %.2fs'
                % (S.srv.key, uid, len(summ), len(det), S.last_len, time.time() - t0))
            return self._json({'ok': 1, 'srv': S.srv.key,
                               'sum': summ.hex(), 'det': det.hex()})
        return self._json({'ok': 0, 'err': 'not found'}, 404)


def _boot_connect():
    for S in SESS.values():
        try:
            with S.lock:
                S._connect_locked()
        except Exception as e:  # noqa: BLE001
            log('%s [boot] 首次登录失败 %r（查询时会重试）' % (S._tag(), e))


def main():
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    log('[boot] http://%s:%d 就绪（区服 %s）' % (BIND, PORT, ','.join(SESS)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=_boot_connect, daemon=True).start()
    for S in SESS.values():
        threading.Thread(target=S.keepalive_loop, daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()

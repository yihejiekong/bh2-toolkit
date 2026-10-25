# -*- coding: utf-8 -*-
"""玩家名片查询（云端独立客户端，双区服）。

用法（区服前缀可省略，默认 B服）：
  查询b2玩家12345678      -> B服（bilibili二区）
  查询b服玩家12345678
  查询官服玩家22334455    -> 官服（国服）
  查询国服玩家22334455
  查询玩家12345678        -> 默认 B服
  绑定b2玩家12345678      -> 绑定 B服 UID
  绑定官服玩家22334455    -> 绑定官服 UID
  查询自己 / 查询@某人    -> 用绑定时的区服
  解绑玩家 / 我的绑定

限制：每人 180 秒只能查一次（管理员不受限）。
数据：本地常驻服务 http://127.0.0.1:8791/pull?srv=b2|gf（见 player/service.py），
      每个区服登录一次长期挂着，查询复用，不重复登录。
"""
import asyncio
import os
import re
import sqlite3
import time

import httpx
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from . import _config, _media
from . import module_switch as _switch
from .player import card as CARD
from .player import parse as P

API = os.environ.get('BH2_QUERY_API', 'http://127.0.0.1:8791')
RATE_SEC = 180
ADMIN = _cfg.ADMIN_SET
OUT_DIR = _config.MATERIAL_ROOT / '玩家名片' / 'out'
KEEP_FILES = 40

SRV_NAMES = {'b2': 'B服', 'gf': '官服'}
_SRV_WORDS = {
    'b2': 'b2', 'b2服': 'b2', 'b服': 'b2', 'bilibili': 'b2', 'bilibili服': 'b2', '哔哩哔哩': 'b2',
    'gf': 'gf', 'gf服': 'gf', 'g服': 'gf', '官服': 'gf', '国服': 'gf', '官方': 'gf',
}


def _srv_of(tok):
    return _SRV_WORDS.get((tok or '').strip().lower(), None)


def _conn():
    return sqlite3.connect(_config.DB)


def _ensure():
    conn = _conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS player_bind (
        qq TEXT PRIMARY KEY, uid INTEGER NOT NULL, srv TEXT NOT NULL DEFAULT 'b2',
        updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))""")
    try:
        conn.execute("ALTER TABLE player_bind ADD COLUMN srv TEXT NOT NULL DEFAULT 'b2'")
    except sqlite3.OperationalError:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS player_qlog (
        qq TEXT PRIMARY KEY, ts REAL NOT NULL)""")
    conn.commit()
    conn.close()


_ensure()

player = on_message(priority=6, block=False)

_SRV = r'(?:b2|b2服|b服|bilibili服?|哔哩哔哩|gf|gf服|g服|官服|国服|官方)'
RE_QUERY = re.compile(r'^查询\s*(%s)?\s*玩家\s*(\d{4,12})$' % _SRV, re.I)
RE_QUERY2 = re.compile(r'^查询\s*(%s)\s*(\d{4,12})$' % _SRV, re.I)
RE_UID = re.compile(r'^查询\s*(\d{4,12})$')
RE_BIND = re.compile(r'^绑定\s*(%s)?\s*玩家\s*(\d{4,12})$' % _SRV, re.I)
RE_SELF = re.compile(r'^查询自己$')
RE_UNBIND = re.compile(r'^解绑玩家$')
RE_MINE = re.compile(r'^我的绑定$')


def _get_bind(qq):
    """返回 (uid, srv) 或 (None, None)。"""
    conn = _conn()
    r = conn.execute('SELECT uid, srv FROM player_bind WHERE qq=?', (str(qq),)).fetchone()
    conn.close()
    return (r[0], r[1] or 'b2') if r else (None, None)


def _set_bind(qq, uid, srv):
    conn = _conn()
    conn.execute('INSERT INTO player_bind(qq,uid,srv) VALUES(?,?,?) '
                 'ON CONFLICT(qq) DO UPDATE SET uid=excluded.uid, srv=excluded.srv, '
                 'updated_at=datetime(\'now\',\'localtime\')', (str(qq), uid, srv))
    conn.commit()
    conn.close()


def _unbind(qq):
    conn = _conn()
    n = conn.execute('DELETE FROM player_bind WHERE qq=?', (str(qq),)).rowcount
    conn.commit()
    conn.close()
    return n


def _rate_left(qq):
    """返回剩余冷却秒数（0 表示可以查）。"""
    if str(qq) in ADMIN:
        return 0
    conn = _conn()
    r = conn.execute('SELECT ts FROM player_qlog WHERE qq=?', (str(qq),)).fetchone()
    conn.close()
    if not r:
        return 0
    left = RATE_SEC - (time.time() - r[0])
    return max(0, int(left))


def _rate_mark(qq):
    conn = _conn()
    conn.execute("INSERT INTO player_qlog(qq,ts) VALUES(?,?) "
                 "ON CONFLICT(qq) DO UPDATE SET ts=excluded.ts", (str(qq), time.time()))
    conn.commit()
    conn.close()


def _cleanup():
    try:
        files = sorted(OUT_DIR.glob('card_*.png'), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[KEEP_FILES:]:
            p.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


async def _pull(uid, srv):
    async with httpx.AsyncClient(timeout=25.0) as cli:
        r = await cli.get(API + '/pull', params={'uid': uid, 'srv': srv})
        return r.json()


async def _send_card(event, uid, srv='b2'):
    left = _rate_left(event.get_user_id())
    if left:
        await player.send('查询冷却中，还要等 %d 秒' % left, at_sender=True)
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        j = await _pull(uid, srv)
    except Exception as e:  # noqa: BLE001
        await player.send('查询服务不可用：%s' % e)
        return
    if not j.get('ok'):
        await player.send('查询失败：%s' % (j.get('err') or '未知错误'))
        return
    _rate_mark(event.get_user_id())
    summ_pl = bytes.fromhex(j['sum'])
    det_pl = bytes.fromhex(j['det'])
    try:
        png, summ, det, ncar = await asyncio.to_thread(CARD.render, summ_pl, det_pl, uid, srv)
    except Exception as e:  # noqa: BLE001
        await player.send('名片渲染失败：%s' % e)
        return
    await player.send(_media.image(png))
    asyncio.create_task(asyncio.to_thread(_cleanup))


@player.handle()
async def _(event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return
    if not _switch.is_on(event.group_id, 'player'):
        return
    text = event.get_plaintext().strip()
    uid_me = event.get_user_id()

    # 查询b2玩家123 / 查询玩家123 / 查询123
    m = RE_QUERY.match(text) or RE_QUERY2.match(text)
    if m:
        srv = _srv_of(m.group(1)) or 'b2'
        await _send_card(event, int(m.group(2)), srv)
        return
    m = RE_UID.match(text)
    if m:
        await _send_card(event, int(m.group(1)), 'b2')
        return

    if RE_SELF.match(text):
        uid, srv = _get_bind(uid_me)
        if not uid:
            await player.finish('你还没绑定 UID，先发「绑定玩家<你的UID>」或「绑定官服玩家<UID>」')
        await _send_card(event, uid, srv)
        return

    m = RE_BIND.match(text)
    if m:
        srv = _srv_of(m.group(1)) or 'b2'
        uid = int(m.group(2))
        old_uid, old_srv = _get_bind(uid_me)
        _set_bind(uid_me, uid, srv)
        extra = ''
        if old_uid:
            extra = '（原 %s UID %d）' % (SRV_NAMES.get(old_srv, old_srv), old_uid)
        await player.finish('已绑定 %s UID %d%s' % (SRV_NAMES.get(srv, srv), uid, extra))

    if RE_UNBIND.match(text):
        n = _unbind(uid_me)
        await player.finish('已解绑' if n else '你本来就没绑定')

    if RE_MINE.match(text):
        uid, srv = _get_bind(uid_me)
        if uid:
            await player.finish('你绑定的 %s UID：%d' % (SRV_NAMES.get(srv, srv), uid))
        await player.finish('你还没绑定 UID')

    # 查询@某人（区服跟随对方绑定）
    if text.startswith('查询'):
        for seg in event.get_message():
            if seg.type == 'at' and seg.data.get('qq') not in (None, 'all', '0'):
                target = str(seg.data['qq'])
                if target == uid_me:
                    await player.finish('想查自己就发「查询自己」')
                uid, srv = _get_bind(target)
                if not uid:
                    await player.finish('对方还没绑定 UID，让他先发「绑定玩家<UID>」')
                await _send_card(event, uid, srv)
                return

# -*- coding: utf-8 -*-
"""B站动态公告推送插件。

监听指定 UP 主（默认「崩坏学园2-灵依娘desu」mid=133934）的最新动态，
每隔 1 小时检查一次，若有新动态则把「动态链接 + 文字摘要」转发到已开启
公告的群里。

交互：
  开启公告 / 开启动态公告   -> 在当前群开启公告推送（仅群主/管理员）
  关闭公告 / 关闭动态公告   -> 在当前群关闭公告推送（仅群主/管理员）

规则：
  - 每个群默认关闭，需手动「开启公告」
  - 定时任务每小时触发一次，拉取最新动态，与本地已推送记录比对去重
  - 支持配置 B站 Cookie（SESSDATA）提升稳定性，无 Cookie 时自动降级
  - 数据源优先级：B站动态 API（带 Cookie）→ RSSHub 公共实例

数据：
  - announce_group 表：group_id -> enabled（该群是否开启公告）
  - announce_seen 表：dynamic_id -> 已推送过的动态 ID（去重）
"""
import asyncio
import json
import os
import time
from datetime import datetime

import httpx
from nonebot import get_bot, get_driver, get_plugin_config, on_command, require
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.log import logger
from pydantic import BaseModel

from . import _config

# ==================== 配置 ====================

# 要监听的 UP 主 mid（崩坏学园2-灵依娘desu）
UP_MID = "133934"
UP_NAME = "崩坏学园2-灵依娘desu"


class Config(BaseModel):
    """从 .env 读取（NoneBot 的 dotenv 只喂给配置系统，不进 os.environ）。"""

    bili_cookie: str = ""
    announce_interval: int = 3600
    announce_admin_only: bool = True
    announce_selftest: bool = False
    # 只推送「发布时间在最近 N 小时内」的动态，更老的只标记不推送（防止置顶旧帖/翻页抖动被当成新动态）
    announce_fresh_hours: int = 24


_plugin_cfg = get_plugin_config(Config)

# B站登录 Cookie（SESSDATA 等），写入 .env 的 BILI_COOKIE，提升稳定性
BILI_COOKIE = _plugin_cfg.bili_cookie

# RSSHub 公共实例（按优先级排列，逐个尝试）
RSSHUB_INSTANCES = [
    "https://rsshub.rssforever.com",
    "https://rsshub.app",
    "https://rsshub.pseudoyu.com",
]

# 检查间隔（秒），默认 1 小时
CHECK_INTERVAL = _plugin_cfg.announce_interval

# 允许操作开关的身份：owner=群主, admin=管理员, False 则任何人
_REQUIRE_ADMIN = _plugin_cfg.announce_admin_only

# 启动自检：为 True 时，本次启动后首次连上 QQ 立刻推一条最新动态到已开启的群，
# 用于验证「拉取 → 拼装 → 发送」整条链路是否可用（默认关闭，正式环境保持 False）。
_SELFTEST = _plugin_cfg.announce_selftest

# 新鲜度窗口（小时）：发布时间早于 now - FRESH_HOURS 的动态一律不推送
FRESH_HOURS = max(1, int(_plugin_cfg.announce_fresh_hours))


def _now_ts() -> int:
    return int(time.time())


def _to_ts(v) -> int:
    """把各种时间表示统一成 unix 秒：int/float 秒、毫秒、'YYYY-MM-DD HH:MM'、RFC822。"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        n = int(v)
        if n > 10 ** 11:  # 毫秒
            n //= 1000
        return n
    s = str(v).strip()
    if not s:
        return 0
    if s.isdigit():
        return _to_ts(int(s))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except ValueError:
            pass
    try:  # RSS 的 RFC822：Thu, 23 Oct 2026 12:00:00 +0800
        from email.utils import parsedate_to_datetime

        return int(parsedate_to_datetime(s).timestamp())
    except Exception:  # noqa: BLE001
        return 0


def _fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "未知时间"


def _is_fresh(ts: int) -> bool:
    """发布时间是否在允许窗口内；拿不到时间时保守放行（避免漏推真正的新动态）。"""
    if not ts:
        return True
    return ts >= _now_ts() - FRESH_HOURS * 3600

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ==================== 数据层 ====================

def _conn():
    import sqlite3
    return sqlite3.connect(_config.DB)


def _ensure_tables():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS announce_group (
            group_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS announce_seen (
            dynamic_id TEXT PRIMARY KEY,
            seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()


def is_enabled(group_id: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT enabled FROM announce_group WHERE group_id = ?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0])


def set_enabled(group_id: str, enabled: bool):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO announce_group (group_id, enabled) VALUES (?, ?) "
        "ON CONFLICT(group_id) DO UPDATE SET enabled = excluded.enabled",
        (group_id, 1 if enabled else 0),
    )
    conn.commit()
    conn.close()


def enabled_groups() -> list[str]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM announce_group WHERE enabled = 1")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def is_seen(dynamic_id: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM announce_seen WHERE dynamic_id = ?", (dynamic_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row)


def mark_seen(dynamic_id: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO announce_seen (dynamic_id) VALUES (?)",
        (dynamic_id,),
    )
    conn.commit()
    conn.close()


# ==================== 动态获取 ====================

async def _fetch_bilibili(host_mid: str) -> list[dict]:
    """直连 B站动态 API，返回 [{id, text, url, time}] 列表（新->旧）。

    两条通道：
      1. feed/space    —— 完整动态流（含视频投稿），部分 IP 被风控返回 -412
      2. opus/feed/space —— 图文动态流，实测风控环境下仍可用（降级）
    返回空列表表示两条都没拉到。
    """
    cookies = {}
    if BILI_COOKIE:
        for kv in BILI_COOKIE.split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                cookies[k] = v

    async with httpx.AsyncClient(timeout=15) as client:
        items = await _fetch_feed_space(client, host_mid, cookies)
        if not items:
            logger.debug("feed/space 无数据，尝试 opus/feed/space")
            items = await _fetch_opus_space(client, host_mid, cookies)
        return items


async def _fetch_feed_space(client: httpx.AsyncClient, host_mid: str, cookies: dict) -> list[dict]:
    """完整动态流（含视频投稿）。被风控时返回空列表。"""
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    headers = {
        "User-Agent": UA,
        "Referer": f"https://space.bilibili.com/{host_mid}/dynamic",
        "Accept": "application/json",
    }
    for attempt in range(2):
        try:
            resp = await client.get(
                url,
                params={"host_mid": host_mid, "features": "itemOpusStyle"},
                headers=headers,
                cookies=cookies or None,
            )
            if resp.status_code == 200 and "application/json" in resp.headers.get(
                "content-type", ""
            ):
                data = resp.json()
                if data.get("code") == 0:
                    return _parse_feed(data)
                logger.debug(f"B站动态 API 返回 code={data.get('code')}: {data.get('message')}")
            else:
                logger.debug(f"B站动态 API HTTP {resp.status_code}（可能被风控）")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"B站动态 API 请求异常: {e}")
        await asyncio.sleep(1.5)
    return []


async def _fetch_opus_space(client: httpx.AsyncClient, host_mid: str, cookies: dict) -> list[dict]:
    """图文动态流（opus）。feed/space 被风控时的可用降级通道。"""
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/feed/space"
    headers = {
        "User-Agent": UA,
        "Referer": f"https://space.bilibili.com/{host_mid}/dynamic",
        "Accept": "application/json",
    }
    try:
        resp = await client.get(
            url,
            params={"host_mid": host_mid, "page": "1"},
            headers=headers,
            cookies=cookies or None,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return _parse_opus(data)
            logger.debug(f"B站 opus API 返回 code={data.get('code')}: {data.get('message')}")
        else:
            logger.debug(f"B站 opus API HTTP {resp.status_code}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"B站 opus API 请求异常: {e}")
    return []


async def _resolve_opus_ts(client: httpx.AsyncClient, opus_id: str, cookies: dict) -> int:
    """opus 通道不返回时间，用 opus/detail 拿真实 pub_ts 与置顶标记，返回 (ts, is_top)。"""
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail"
    headers = {
        "User-Agent": UA,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json",
    }
    try:
        resp = await client.get(url, params={"id": opus_id}, headers=headers, cookies=cookies or None)
        if resp.status_code != 200:
            return 0, False
        data = resp.json()
        if data.get("code") != 0:
            return 0, False
        item = (data.get("data") or {}).get("item") or {}
        mods = item.get("modules") or []
        # 该接口的 modules 是 [{module_type, module_author, ...}, ...] 列表
        if isinstance(mods, dict):
            mods = [mods]
        for m in mods:
            author = (m or {}).get("module_author") or {}
            if author:
                return _to_ts(author.get("pub_ts")), bool(author.get("is_top"))
        return 0, False
    except Exception as e:  # noqa: BLE001
        logger.debug(f"opus {opus_id} 时间解析失败: {e}")
        return 0, False


# 动态类型 -> 友好描述（纯图/投稿等文字为空时用作兜底文案）
_TYPE_LABEL = {
    "MAJOR_TYPE_ARCHIVE": "发布了新视频",
    "MAJOR_TYPE_DRAW": "发布了新图片动态",
    "MAJOR_TYPE_ARTICLE": "发布了新专栏",
    "MAJOR_TYPE_OPUS": "发布了新图文",
    "MAJOR_TYPE_COMMON": "发布了新动态",
}


def _parse_feed(data: dict) -> list[dict]:
    items = data.get("data", {}).get("items", [])
    result = []
    for it in items:
        id_str = it.get("id_str") or str(it.get("dynamic_id", ""))
        if not id_str:
            continue
        modules = it.get("modules", {})
        mod_dyn = modules.get("module_dynamic", {})
        # 文字内容：纯文字动态在 modules.module_dynamic.desc.text
        desc = mod_dyn.get("desc")
        text = (desc or {}).get("text", "")
        text = (text or "").strip()
        # 动态类型（MAJOR_TYPE_ARCHIVE=视频投稿，DRAW=纯图等）
        mtype = ""
        major = mod_dyn.get("major")
        if major:
            mtype = major.get("type", "")
        # 文字为空时用类型兜底，避免推「空动态」
        if not text:
            text = _TYPE_LABEL.get(mtype, "")
        author = modules.get("module_author") or {}
        pub_ts = _to_ts(author.get("pub_ts"))
        tag = ((modules.get("module_tag") or {}).get("text") or "").strip()
        result.append(
            {
                "id": id_str,
                "text": text,
                "url": f"https://t.bilibili.com/{id_str}",
                "time": _fmt_ts(pub_ts),
                "pub_ts": pub_ts,
                "pinned": bool(author.get("is_top")) or tag in ("置顶", "Top", "TOP"),
            }
        )
    return result


def _parse_opus(data: dict) -> list[dict]:
    """解析 opus/feed/space 的返回，结构比 feed/space 扁平。

    [{opus_id, content, jump_url, pub_time}] -> [{id, text, url, time}]
    内容里常带零宽空格（\\u200b），去掉避免推送时出现诡异空白。
    """
    items = data.get("data", {}).get("items", []) or []
    result = []
    for it in items:
        oid = str(it.get("opus_id") or "").strip()
        if not oid:
            continue
        text = (it.get("content") or "").replace("\u200b", "").strip()
        url = it.get("jump_url") or f"//www.bilibili.com/opus/{oid}"
        if url.startswith("//"):
            url = "https:" + url
        # 该接口的 pub_time 恒为空字符串，发布时间需要再用 opus/detail 查（见 _resolve_opus_ts）
        pub_ts = _to_ts(it.get("pub_time"))
        result.append(
            {
                "id": oid,
                "text": text or "发布了新动态",
                "url": url,
                "time": _fmt_ts(pub_ts),
                "pub_ts": pub_ts,
                "pinned": False,
                "need_time": not pub_ts,
            }
        )
    return result


def _seen_count() -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM announce_seen")
    n = cur.fetchone()[0]
    conn.close()
    return n


async def _fetch_rsshub(host_mid: str) -> list[dict]:
    """RSSHub 降级数据源，返回 [{id, text, url, time}]（新->旧）。"""
    import xml.etree.ElementTree as ET

    for base in RSSHUB_INSTANCES:
        url = f"{base}/bilibili/user/dynamic/{host_mid}"
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": UA})
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.text)
                items = []
                for item in root.iter("item"):
                    link = item.findtext("link") or ""
                    title = item.findtext("title") or ""
                    guid = item.findtext("guid") or link
                    # 从 link 提取 dynamic id（t.bilibili.com/xxx）
                    dyn_id = ""
                    for part in link.split("/"):
                        if part.isdigit():
                            dyn_id = part
                            break
                    if not dyn_id:
                        dyn_id = guid
                    pub_ts = _to_ts(item.findtext("pubDate"))
                    items.append(
                        {
                            "id": dyn_id,
                            "text": title,
                            "url": link or f"https://t.bilibili.com/{dyn_id}",
                            "time": _fmt_ts(pub_ts),
                            "pub_ts": pub_ts,
                            "pinned": False,
                        }
                    )
                if items:
                    logger.info(f"RSSHub {base} 拉到 {len(items)} 条动态")
                    return items
        except Exception as e:  # noqa: BLE001
            logger.debug(f"RSSHub {base} 失败: {e}")
    return []


async def fetch_latest(host_mid: str = UP_MID) -> list[dict]:
    """拉取最新动态（新->旧），优先 B站直连，失败降级 RSSHub。"""
    items = await _fetch_bilibili(host_mid)
    if not items:
        logger.warning("B站动态 API 未拉到数据，降级 RSSHub")
        items = await _fetch_rsshub(host_mid)
    return items


# ==================== 定时任务 ====================

async def _check_once():
    """拉取最新动态，把「未推送过」的新动态发给所有已开启的群。"""
    _ensure_tables()
    groups = enabled_groups()
    if not groups:
        return
    try:
        items = await fetch_latest()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"拉取动态异常: {e}")
        return
    if not items:
        return

    # 首次运行建立基线：此时 announce_seen 为空，若直接推送会把最多 20 条历史
    # 动态一次性刷进群。这里只做标记，不发消息。
    if _seen_count() == 0:
        for it in items:
            mark_seen(it["id"])
        logger.info(f"首次运行，已把 {len(items)} 条历史动态记为基线（不入群），之后只推新动态")
        return

    # 置顶动态永远是旧帖，只标记不推送（它每次都会出现在列表首屏）
    unseen = []
    for it in items:
        if is_seen(it["id"]):
            continue
        if it.get("pinned"):
            mark_seen(it["id"])
            logger.info(f"跳过置顶动态 {it['id']}（{it.get('time')}）")
            continue
        unseen.append(it)

    # opus 通道没有发布时间，逐条补解析（只对未见过的条目做，最多 8 条）
    todo = [it for it in unseen if it.get("need_time") and not it.get("pub_ts")][:8]
    head = items[0]
    if head.get("need_time") and not head.get("pub_ts") and head not in todo:
        todo.insert(0, head)
    if todo:
        cookies = {}
        for kv in (BILI_COOKIE or "").split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                cookies[k] = v
        async with httpx.AsyncClient(timeout=15) as client:
            for it in todo:
                ts, top = await _resolve_opus_ts(client, it["id"], cookies)
                if ts:
                    it["pub_ts"] = ts
                    it["time"] = _fmt_ts(ts)
                    it["need_time"] = False
                if top:
                    it["pinned"] = True
                await asyncio.sleep(0.4)

    # 最新一条写进日志，方便以后核对「到底拉到了什么」
    logger.info(
        f"B站动态检查：拉到 {len(items)} 条，最新 {head['id']}（{head.get('time')}）"
        f"{' [置顶]' if head.get('pinned') else ''}"
    )

    # 新鲜度护栏：只有「发布时间在最近 FRESH_HOURS 小时内」的才算新动态。
    # B站 feed 的 20 条窗口会随置顶/翻页抖动，旧帖可能首次出现在列表里，
    # 若不看时间就会被当成新动态推出去。
    new_items, stale = [], []
    for it in unseen:
        if _is_fresh(it.get("pub_ts") or 0):
            new_items.append(it)
        else:
            stale.append(it)
    if stale:
        logger.info(
            f"忽略 {len(stale)} 条过期动态（发布时间早于 {FRESH_HOURS} 小时）："
            + "、".join(f"{it['id']}({it.get('time')})" for it in stale[:5])
        )
        for it in stale:
            mark_seen(it["id"])
    if not new_items:
        return

    logger.info(f"发现 {len(new_items)} 条新动态，准备推送到 {len(groups)} 个群")
    bot = get_bot()
    for group_id in groups:
        for it in reversed(new_items):  # 按时间正序发（旧->新）
            msg = _build_msg(it)
            try:
                await bot.send_group_msg(group_id=int(group_id), message=msg)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"推送到群 {group_id} 失败: {e}")
            await asyncio.sleep(0.5)
    # 全部发送成功后标记已推送
    for it in new_items:
        mark_seen(it["id"])


def _build_msg(item: dict) -> Message:
    text = item.get("text") or ""
    url = item.get("url") or ""
    parts = [f"【{UP_NAME} 发布新动态】"]
    if text:
        # 控制摘要长度，避免刷屏
        summary = text if len(text) <= 120 else text[:120] + "…"
        parts.append(summary)
    parts.append(url)
    return Message(MessageSegment.text("\n".join(parts)))


# ==================== 开关命令 ====================

def _is_admin(event: GroupMessageEvent) -> bool:
    if not _REQUIRE_ADMIN:
        return True
    role = getattr(event.sender, "role", None)
    # role: owner / admin / member
    return role in ("owner", "admin")


on_enable = on_command("开启公告", aliases={"开启动态公告", "打开公告"}, block=True, priority=5)
on_disable = on_command("关闭公告", aliases={"关闭动态公告", "停用公告"}, block=True, priority=5)


@on_enable.handle()
async def handle_enable(event: GroupMessageEvent):
    _ensure_tables()
    if not _is_admin(event):
        await on_enable.finish("只有群主或管理员才能开启公告哦~")
    set_enabled(str(event.group_id), True)
    await on_enable.finish("公告已开启，我会每小时检查「崩坏学园2-灵依娘desu」的新动态并转发到本群~")


@on_disable.handle()
async def handle_disable(event: GroupMessageEvent):
    _ensure_tables()
    if not _is_admin(event):
        await on_disable.finish("只有群主或管理员才能关闭公告哦~")
    set_enabled(str(event.group_id), False)
    await on_disable.finish("公告已关闭，本群不再接收动态推送~")


# ==================== 定时器注册 ====================

_scheduler = require("nonebot_plugin_apscheduler").scheduler


@_scheduler.scheduled_job("interval", seconds=CHECK_INTERVAL, id="bili_announce_check",
                          misfire_grace_time=60, coalesce=True)
async def _scheduled_check():
    try:
        await _check_once()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"公告检查任务异常: {e}")


# 启动时建表，确保首次可用
_ensure_tables()
logger.info(
    f"B站动态公告插件已加载，UP={UP_MID}，间隔={CHECK_INTERVAL}s，"
    f"Cookie={'已配置(' + str(len(BILI_COOKIE)) + '字符)' if BILI_COOKIE else '未配置'}"
)

# ==================== 启动自检（ANNOUNCE_SELFTEST=true 时启用） ====================
# 只在本次进程内第一次连上 QQ 时执行一次，忽略 announce_seen 去重，直接推最新一条，
# 用来确认「B站拉取 → 拼装 → 发群」这条链路真的能走通。
_selftest_done = False

if _SELFTEST:

    @get_driver().on_bot_connect
    async def _selftest_on_connect(bot):  # noqa: ANN001
        global _selftest_done
        if _selftest_done:
            return
        _selftest_done = True
        await asyncio.sleep(3)
        groups = enabled_groups()
        if not groups:
            logger.warning("公告自检：没有已开启公告的群，跳过")
            return
        items = await fetch_latest()
        if not items:
            logger.warning("公告自检：未拉取到任何动态（B站接口与 RSSHub 均失败）")
            return
        latest = items[0]
        for gid in groups:
            try:
                await bot.send_group_msg(group_id=int(gid), message=_build_msg(latest))
                logger.info(f"公告自检：已推送动态 {latest['id']} 到群 {gid}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"公告自检：推送到群 {gid} 失败: {e}")


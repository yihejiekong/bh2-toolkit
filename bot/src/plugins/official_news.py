# -*- coding: utf-8 -*-
"""崩坏学园2 官网公告推送插件。

像 announce.py 的 B站动态推送一样：每小时检查一次官网公告页，有新公告就推
「标题 + 正文摘要 + 链接」到已开启公告的群。

数据源（官网公告页 https://www.benghuai.com/news/ 前端实际调用的接口）：
  POST https://www.benghuai.com/news/getNotice
       -> data: {new:[...], version:[...], gach:[...], event:[...]}
       每条：{id, title, time, type, feature}
  POST https://www.benghuai.com/news/getNoticeByID?id=<id>
       -> data: {id, title, text(HTML 正文), time, type, feature}

规则：
  - 开关独立：本插件用自己的 news_group 表，「开启官网公告 / 关闭官网公告」只影响官网公告，
    和 B站动态推送（announce 插件）互不干扰
  - 每小时检查一次（NEWS_INTERVAL，默认 3600 秒）
  - 首次运行只把现有公告记为基线，不刷屏；之后只推没见过的 id
  - 同一条公告 id 只推一次（news_seen 表去重）
  - 升级兼容：news_group 为空时，自动把已开启 B站公告的群也设为开启
"""
import asyncio
import html
import re

import httpx
from nonebot import get_bot, get_driver, get_plugin_config, on_command, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.log import logger
from pydantic import BaseModel

from . import _config

BASE = "https://www.benghuai.com/news/"
LIST_API = BASE + "getNotice"
DETAIL_API = BASE + "getNoticeByID"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE,
    "X-Requested-With": "XMLHttpRequest",
}

# 公告类型：官网接口的 type 字段（0 其他 / 1 活动 / 2 祈愿 / 3 版本）
TYPE_LABEL = {"0": "其他", "1": "活动", "2": "祈愿", "3": "版本"}

# 摘要长度上限（字符）
MAX_SUMMARY = 120


class Config(BaseModel):
    news_interval: int = 3600
    news_selftest: bool = False
    news_admin_only: bool = True
    # 公告发布时间早于 now - NEWS_FRESH_HOURS 的，只标记不推送（防止老公告被当新公告）
    news_fresh_hours: int = 72


_cfg = get_plugin_config(Config)
CHECK_INTERVAL = _cfg.news_interval
_SELFTEST = _cfg.news_selftest
_ADMIN_ONLY = _cfg.news_admin_only

# 新鲜度窗口（小时）
FRESH_HOURS = max(1, int(_cfg.news_fresh_hours))


def _to_ts(v) -> int:
    """官网 time 字段形如 '2026-10-23 10:00:00'；也兼容纯数字与 ISO。"""
    if v is None:
        return 0
    s = str(v).strip()
    if not s:
        return 0
    if s.isdigit():
        n = int(s)
        return n // 1000 if n > 10 ** 11 else n
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            import time as _t
            import datetime as _dt

            return int(_t.mktime(_dt.datetime.strptime(s, fmt).timetuple()))
        except ValueError:
            pass
    return 0


def _is_fresh(ts: int) -> bool:
    if not ts:
        return True
    import time as _t

    return ts >= int(_t.time()) - FRESH_HOURS * 3600


# ==================== 数据层 ====================

def _conn():
    import sqlite3
    return sqlite3.connect(_config.DB)


def _ensure_tables():
    conn = _conn()
    cur = conn.cursor()
    # 本插件独立的群级开关表（与 announce 插件的 announce_group 互不影响）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_group (
            group_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_seen (
            notice_id TEXT PRIMARY KEY,
            title TEXT,
            seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 升级兼容：news_group 还没任何记录时，把已开启 B站公告的群一并设为开启，
    # 避免拆分开关后老群静默收不到推送。之后用户关掉的就是关掉了，不会被重新打开。
    cur.execute("SELECT COUNT(*) FROM news_group")
    if cur.fetchone()[0] == 0:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='announce_group'")
        if cur.fetchone():
            cur.execute(
                "INSERT OR IGNORE INTO news_group (group_id, enabled) "
                "SELECT group_id, 1 FROM announce_group WHERE enabled = 1"
            )
    conn.commit()
    conn.close()


def news_enabled_groups() -> list[str]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM news_group WHERE enabled = 1")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def set_news_enabled(group_id: str, enabled: bool):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO news_group (group_id, enabled) VALUES (?, ?) "
        "ON CONFLICT(group_id) DO UPDATE SET enabled = excluded.enabled",
        (str(group_id), 1 if enabled else 0),
    )
    conn.commit()
    conn.close()


def is_seen(notice_id: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM news_seen WHERE notice_id = ?", (notice_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row)


def mark_seen(notice_id: str, title: str = ""):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO news_seen (notice_id, title) VALUES (?, ?)",
        (notice_id, title),
    )
    conn.commit()
    conn.close()


def _seen_count() -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM news_seen")
    n = cur.fetchone()[0]
    conn.close()
    return n


# ==================== 拉取 ====================

async def fetch_notices() -> list[dict]:
    """拉公告列表（「最新公告」tab），按 id 去重，返回新->旧。"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(LIST_API, headers=HEADERS)
        resp.raise_for_status()
        payload = resp.json()

    if payload.get("retcode") != 1:  # 官网接口成功时 retcode 就是 1
        raise RuntimeError(f"getNotice 返回异常: retcode={payload.get('retcode')}")

    raw = (payload.get("data") or {}).get("new") or []
    out, seen = [], set()
    for it in raw:
        nid = str(it.get("id") or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        raw_time = it.get("time") or ""
        out.append(
            {
                "id": nid,
                "title": (it.get("title") or "").strip(),
                "time": raw_time,
                "pub_ts": _to_ts(raw_time),
                "type": str(it.get("type") or "0"),
            }
        )
    return out


async def fetch_detail(notice_id: str) -> dict:
    """拉公告正文（HTML），失败返回空 dict，不影响推送。"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(DETAIL_API, params={"id": notice_id}, headers=HEADERS)
            resp.raise_for_status()
            payload = resp.json()
        if payload.get("retcode") == 1:
            return payload.get("data") or {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"拉取公告 {notice_id} 正文失败: {e}")
    return {}


# ==================== 消息构造 ====================

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(raw: str) -> str:
    """HTML 正文转纯文本：块级标签换行、去标签、还原实体、压缩空白。"""
    s = raw or ""
    s = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = s.replace("\u200b", "").replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def notice_url(notice_id: str) -> str:
    return f"{BASE}?para=new_{notice_id}"


def _build_msg(item: dict, detail: dict) -> Message:
    title = item.get("title") or "（无标题）"
    label = TYPE_LABEL.get(item.get("type", "0"), "公告")
    body = _plain_text((detail or {}).get("text", ""))
    summary = re.sub(r"\s+", " ", body).strip()
    if len(summary) > MAX_SUMMARY:
        summary = summary[:MAX_SUMMARY] + "…"

    parts = [f"【崩坏学园2 官网公告 · {label}】{title}"]
    if summary:
        parts.append(summary)
    parts.append(notice_url(item["id"]))
    return Message(MessageSegment.text("\n".join(parts)))


# ==================== 定时检查 ====================

async def _check_once():
    _ensure_tables()
    groups = news_enabled_groups()
    if not groups:
        return

    try:
        items = await fetch_notices()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"官网公告拉取失败: {e}")
        return
    if not items:
        return

    # 首次运行只建基线，避免把历史公告一次性刷进群
    if _seen_count() == 0:
        for it in items:
            mark_seen(it["id"], it["title"])
        logger.info(f"官网公告首次运行，已把 {len(items)} 条历史公告记为基线（不入群）")
        return

    head = items[0]
    logger.info(
        f"官网公告检查：拉到 {len(items)} 条，最新 {head['id']}《{head.get('title')}》（{head.get('time')}）"
    )

    unseen = [it for it in items if not is_seen(it["id"])]
    new_items, stale = [], []
    for it in unseen:
        if _is_fresh(it.get("pub_ts") or 0):
            new_items.append(it)
        else:
            stale.append(it)
    if stale:
        logger.info(
            f"忽略 {len(stale)} 条过期公告（发布时间早于 {FRESH_HOURS} 小时）："
            + "、".join(f"{it['id']}({it.get('time')})" for it in stale[:5])
        )
        for it in stale:
            mark_seen(it["id"], it["title"])
    if not new_items:
        return

    logger.info(f"官网公告发现 {len(new_items)} 条新公告，准备推送到 {len(groups)} 个群")
    try:
        bot = get_bot()
    except ValueError:
        logger.warning("官网公告：当前没有已连接的 Bot，跳过本次推送")
        return

    for it in reversed(new_items):  # 旧 -> 新，和 B站动态推送一致
        detail = await fetch_detail(it["id"])
        msg = _build_msg(it, detail)
        for gid in groups:
            try:
                await bot.send_group_msg(group_id=int(gid), message=msg)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"官网公告推送到群 {gid} 失败: {e}")
            await asyncio.sleep(0.5)
    for it in new_items:
        mark_seen(it["id"], it["title"])


# ==================== 开关命令 ====================

def _is_admin(event: GroupMessageEvent) -> bool:
    """群主/管理员才能开关；NEWS_ADMIN_ONLY=false 时任何人可操作。"""
    if not _ADMIN_ONLY:
        return True
    role = getattr(event.sender, "role", None)
    return role in ("owner", "admin")


news_on = on_command(
    "开启官网公告", aliases={"开官网公告", "打开官网公告"}, block=True, priority=5
)
news_off = on_command(
    "关闭官网公告", aliases={"关官网公告", "关掉官网公告"}, block=True, priority=5
)


@news_on.handle()
async def handle_news_on(event: GroupMessageEvent):
    _ensure_tables()
    if not _is_admin(event):
        await news_on.finish("只有群主或管理员才能开启官网公告哦~")
    set_news_enabled(event.group_id, True)
    await news_on.finish(
        "官网公告已开启，我会每小时检查一次《崩坏学园2》官网公告页，"
        "有新公告就转发到本群~"
    )


@news_off.handle()
async def handle_news_off(event: GroupMessageEvent):
    _ensure_tables()
    if not _is_admin(event):
        await news_off.finish("只有群主或管理员才能关闭官网公告哦~")
    set_news_enabled(event.group_id, False)
    await news_off.finish(
        "官网公告已关闭，本群不再接收官网公告推送（B站动态推送不受影响）~"
    )


# ==================== 定时器 ====================

_scheduler = require("nonebot_plugin_apscheduler").scheduler


@_scheduler.scheduled_job(
    "interval",
    seconds=CHECK_INTERVAL,
    id="official_news_check",
    misfire_grace_time=60,
    coalesce=True,
)
async def _scheduled_check():
    try:
        await _check_once()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"官网公告检查任务异常: {e}")


# ==================== 启动自检（NEWS_SELFTEST=true 时启用） ====================

_selftest_done = False

if _SELFTEST:

    @get_driver().on_bot_connect
    async def _selftest_on_connect(bot):  # noqa: ANN001
        global _selftest_done
        if _selftest_done:
            return
        _selftest_done = True
        await asyncio.sleep(3)
        _ensure_tables()
        groups = news_enabled_groups()
        if not groups:
            logger.warning("官网公告自检：没有开启官网公告的群，跳过")
            return
        items = await fetch_notices()
        if not items:
            logger.warning("官网公告自检：未拉取到任何公告")
            return
        # 先把历史记成基线，避免定时任务稍后重复推
        for it in items:
            mark_seen(it["id"], it["title"])
        latest = items[0]
        detail = await fetch_detail(latest["id"])
        msg = _build_msg(latest, detail)
        for gid in groups:
            try:
                await bot.send_group_msg(group_id=int(gid), message=msg)
                logger.info(f"官网公告自检：已推送 {latest['id']}《{latest['title']}》到群 {gid}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"官网公告自检：推送到群 {gid} 失败: {e}")


_ensure_tables()
logger.info(
    f"官网公告插件已加载，间隔={CHECK_INTERVAL}s，基线进度={_seen_count()} 条"
)

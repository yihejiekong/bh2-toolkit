# -*- coding: utf-8 -*-
"""装备查询插件。

交互：
  装备查询 白花        -> 返回最多 9 条匹配列表
  （1分钟内）回复序号 1  -> 返回该装备的装备卡（无卡则回退发图标）

搜索匹配「名称 + 别名」，用 SQLite LIKE 包含匹配。
素材目录：<素材根>/装备卡、<素材根>/图标、<素材根>/觉醒立绘
"""
import sqlite3
from pathlib import Path

from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg

from . import _session, _config, _media, module_switch as _switch

DB = _config.DB
ICON_DIR = _config.ICON_DIR
CARD_ROOT = _config.CARD_ROOT

MAX_RESULTS = 200  # 搜索结果上限（分页前先截断，防止爆量）
PAGE_SIZE = 9       # 每页显示条数
SESSION_TTL = 60    # 秒

SESSION_TYPE = "equip"


def _conn():
    return sqlite3.connect(DB)


def _search(keyword: str, limit: int = MAX_RESULTS):
    """LIKE 包含匹配（匹配名称 + 别名，对中文关键词更精准）。"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, rarity, category, icon_file, card_file
        FROM equip WHERE name LIKE ? OR alias LIKE ?
        ORDER BY
            CASE WHEN name = ? THEN 0
                 WHEN name LIKE ? THEN 1
                 ELSE 2 END,
            rarity DESC
        LIMIT ?
        """,
        (f"%{keyword}%", f"%{keyword}%", keyword, f"{keyword}%", limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _fmt_line(idx, name, rarity, category):
    return f"{idx}. {name} {rarity or '?'}★（{category or '?'}）"


def _render_page(items, page):
    """渲染某一页的列表文本。返回 (文本行列表, 是否有下一页)。"""
    total = len(items)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_items = items[start:end]

    lines = [f"找到 {total} 条（第 {page + 1}/{total_pages} 页），回复序号查看（1分钟内有效）："]
    for i, (eid, name, rarity, cat, icon, card) in enumerate(page_items, 1):
        lines.append(_fmt_line(i, name, rarity, cat))
    has_next = page + 1 < total_pages
    if has_next:
        lines.append("0. 下一页")
    return lines, has_next


def _icon_path(icon_file: str) -> Path | None:
    if not icon_file:
        return None
    p = ICON_DIR / icon_file
    if p.exists():
        return p
    return None


def _card_path(card_file: str) -> Path | None:
    """装备卡 PNG 路径。card_file 是相对 CARD_ROOT 的路径。

    库里存的是 Windows 风格路径（反斜杠分隔：类别目录、PNG、文件名），
    统一转成 POSIX 分隔符后再拼到 CARD_ROOT 下，否则 Linux 上会把反斜杠
    当普通字符，永远找不到文件。
    """
    if not card_file:
        return None
    rel = str(card_file).replace("\\", "/").lstrip("/")
    p = CARD_ROOT / rel
    if p.exists():
        return p
    return None


def _build_image_segment(icon_file: str, card_file: str) -> MessageSegment:
    """优先发装备卡，无卡则回退发图标。"""
    # 1. 装备卡优先
    cp = _card_path(card_file)
    if cp:
        return _media.image(cp)
    # 2. 回退图标
    ip = _icon_path(icon_file)
    if ip:
        return _media.image(ip)
    return MessageSegment.text("（图片缺失）")


# 命令：装备查询 xxx
query = on_command(
    "装备查询",
    aliases={"查询装备", "查装备", "查图鉴", "查询图鉴", "装备"},
    block=True,
    priority=5,
)


def _build_result_message(item) -> Message:
    """根据一条装备记录，构造回复消息（纯图片，不带文字）。"""
    eid, name, rarity, category, icon_file, card_file = item
    seg = _build_image_segment(icon_file, card_file)
    return Message(seg)


@query.handle()
async def handle_query(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not await _switch.require(query, event, "equip"):
        return
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await query.finish("用法：查询装备 <关键词>")
    items = _search(keyword)
    if not items:
        await query.finish("没有找到装备捏，请检查拼写~")
    # 唯一结果：直接出图
    if len(items) == 1:
        await query.finish(_build_result_message(items[0]))
    # 存会话（记录全部 items + 当前页）
    key = (event.group_id, event.user_id)
    _session.set_session(key, SESSION_TYPE, items, SESSION_TTL)

    lines, _ = _render_page(items, 0)
    await query.finish("\n".join(lines))


# 回复处理：0 翻页 / 1~9 选装备
number = on_regex(r"^[0-9]$", block=False, priority=10)


@number.handle()
async def handle_number(event: GroupMessageEvent):
    if not _switch.is_on(event.group_id, "equip"):
        return
    key = (event.group_id, event.user_id)
    sess = _session.get_session(key, SESSION_TYPE)
    if not sess:
        return  # 不是本插件有效会话，放行

    text = event.get_plaintext().strip()
    num = int(text)
    items = sess["items"]
    total = len(items)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    # 0 = 翻页
    if num == 0:
        page = sess["page"]
        if page + 1 >= total_pages:
            await number.finish("已经是最后一页啦~")
        sess["page"] = page + 1
        _session.touch(sess, SESSION_TTL)
        lines, _ = _render_page(items, page + 1)
        await number.finish("\n".join(lines))

    # 1~9 选装备（当前页内的序号）
    page = sess["page"]
    start = page * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    if num > len(page_items):
        await number.finish(f"序号超出范围（本页共 {len(page_items)} 条）")

    item = page_items[num - 1]
    # 消费会话
    _session.clear(key)
    await number.finish(_build_result_message(item))

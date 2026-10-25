# -*- coding: utf-8 -*-
"""觉醒立绘查询插件。

交互：
  立绘查询 琪亚娜      -> 返回最多 9 条匹配列表（角色名 + 装备名均可搜）
  （1分钟内）回复序号 1 -> 返回对应觉醒立绘图

命令别名：立绘查询 / 觉醒查询 / CG查询 / 立绘 / 觉醒

数据：illust 表（角色名 -> 立绘文件）+ illust_equip 表（装备名 -> 立绘）。
搜索匹配「觉醒角色名」或「装备名」，用 SQLite LIKE 包含匹配。
素材目录：<素材根>/觉醒立绘、<素材根>/官网CG
"""
import sqlite3
from pathlib import Path

from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg

from . import _session, _config, _media, module_switch as _switch

DB = _config.DB
ILLUST_DIR = _config.ILLUST_DIR
# 官网下载页「CG下载区」的图（单独放一个目录，不混进觉醒立绘）
CG_DIR = ILLUST_DIR.parent / "官网CG"
CG_SERIES = "官网CG"
# 这些关键词直接列出全部官网 CG
CG_BROWSE_WORDS = {"cg", "cg图", "壁纸", "wallpaper", "官网cg", "官网壁纸", "全部cg"}

MAX_RESULTS = 200  # 搜索结果上限
PAGE_SIZE = 9       # 每页显示条数
SESSION_TTL = 60    # 秒

SESSION_TYPE = "illust"


def _conn():
    return sqlite3.connect(DB)


def _search(keyword: str, limit: int = MAX_RESULTS):
    """LIKE 包含匹配（角色名 + 装备名），返回去重后的立绘列表。

    关键词命中 CG_BROWSE_WORDS 时，直接列出全部官网 CG（按日期倒序）。
    返回项结构：(file, role_name, series)
    """
    conn = _conn()
    cur = conn.cursor()

    if keyword.strip().lower() in CG_BROWSE_WORDS:
        cur.execute(
            """
            SELECT file, role_name, series FROM illust
            WHERE series = ? ORDER BY file DESC LIMIT ?
            """,
            (CG_SERIES, limit),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    # 匹配角色名或装备名，按立绘文件去重
    cur.execute(
        """
        SELECT file, role_name, series
        FROM (
            -- 直接按角色名命中
            SELECT i.file AS file, i.role_name AS role_name, i.series AS series,
                   CASE WHEN i.role_name = ? THEN 0
                        WHEN i.role_name LIKE ? THEN 1
                        ELSE 2 END AS ord
            FROM illust i
            WHERE i.role_name LIKE ?
            UNION ALL
            -- 按装备名命中，映射到立绘
            SELECT i.file, i.role_name, i.series,
                   CASE WHEN e.equip_name = ? THEN 0
                        WHEN e.equip_name LIKE ? THEN 1
                        ELSE 2 END AS ord
            FROM illust_equip e
            JOIN illust i ON i.file = e.file
            WHERE e.equip_name LIKE ?
        )
        GROUP BY file
        ORDER BY MIN(ord) ASC, role_name ASC
        LIMIT ?
        """,
        (
            keyword, f"{keyword}%", f"%{keyword}%",   # 角色名匹配参数
            keyword, f"{keyword}%", f"%{keyword}%",   # 装备名匹配参数
            limit,
        ),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _fmt_line(idx, role_name, series):
    s = f"（{series}）" if series else ""
    return f"{idx}. {role_name}{s}"


def _render_page(items, page):
    """渲染某一页的列表文本。返回 (文本行列表, 是否有下一页)。"""
    total = len(items)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_items = items[start:end]

    lines = [f"找到 {total} 条（第 {page + 1}/{total_pages} 页），回复序号查看（1分钟内有效）："]
    for i, (file, role_name, series) in enumerate(page_items, 1):
        lines.append(_fmt_line(i, role_name, series))
    has_next = page + 1 < total_pages
    if has_next:
        lines.append("0. 下一页")
    return lines, has_next


def _illust_path(file: str) -> Path | None:
    if not file:
        return None
    for base in (ILLUST_DIR, CG_DIR):
        p = base / file
        if p.exists():
            return p
    return None


def _build_result_message(item) -> Message:
    """根据一条立绘记录，构造回复消息（纯图片，不带文字）。"""
    file, role_name, series = item
    p = _illust_path(file)
    if p:
        return Message(_media.image(p))
    return Message(MessageSegment.text("（立绘缺失）"))


# 命令：立绘查询 xxx
query = on_command(
    "立绘查询",
    aliases={
        "查询立绘", "查立绘",
        "觉醒查询", "查询觉醒", "查觉醒",
        "CG查询", "查询CG", "cg查询", "查询cg",
        "立绘", "觉醒", "CG", "cg",
    },
    block=True,
    priority=5,
)


@query.handle()
async def handle_query(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not await _switch.require(query, event, "illust"):
        return
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await query.finish("用法：立绘查询 <关键词>")
    items = _search(keyword)
    if not items:
        await query.finish("没有找到立绘捏，请检查拼写~")
    # 唯一结果：直接出图
    if len(items) == 1:
        await query.finish(_build_result_message(items[0]))
    # 存会话（记录全部 items + 当前页）
    key = (event.group_id, event.user_id)
    _session.set_session(key, SESSION_TYPE, items, SESSION_TTL)

    lines, _ = _render_page(items, 0)
    await query.finish("\n".join(lines))


# 回复处理：0 翻页 / 1~9 选立绘
number = on_regex(r"^[0-9]$", block=False, priority=10)


@number.handle()
async def handle_number(event: GroupMessageEvent):
    if not _switch.is_on(event.group_id, "illust"):
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

    # 1~9 选立绘（当前页内的序号）
    page = sess["page"]
    start = page * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    if num > len(page_items):
        await number.finish(f"序号超出范围（本页共 {len(page_items)} 条）")

    item = page_items[num - 1]
    # 消费会话
    _session.clear(key)
    await number.finish(_build_result_message(item))

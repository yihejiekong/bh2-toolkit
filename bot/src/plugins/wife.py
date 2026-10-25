# -*- coding: utf-8 -*-
"""抽老婆 / 换老婆插件。

交互：
  抽老婆 / 随机老婆   -> 从「拥有觉醒立绘的武器/服装/徽章」中随机抽一件，
                          发送「你今天的老婆是XXX哦~」+ 觉醒立绘图
  换老婆 / 更换老婆 / 换一个
                      -> 再随机一件（不可与本人今天已抽、也不可与今天群里
                          其他人抽过重复），发送「新换的老婆是XXX哦~」+ 图

规则：
  - 每个用户每天「抽」1 次 + 「换」1 次（共 2 次），凌晨（跨日期）自动刷新
  - 「换」必须先抽过，且只消耗换的配额，不会占用抽的次数
  - .env 里 BOT_ADMINS 列出的 qq 不受次数限制
  - 装备名不带稀有度，只要名字

数据：illust_equip 表 join equip 表，按 name 精确匹配，
      筛 category IN ('武器','服装','徽章')，取 (equip_name, file)。
持久化：wife_record 表（group_id/user_id/date/equip_name/kind），
        kind 区分 'draw'（抽）与 'swap'（换），配额按 kind 分别统计。
"""
import random
import sqlite3
import time
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg

from . import _config, _media, module_switch as _switch

DB = _config.DB
ILLUST_DIR = _config.ILLUST_DIR

# 拥有觉醒立绘的装备类别（不含使魔，按需求只要武器/服装/徽章）
_CATS = ("武器", "服装", "徽章")

# 特权用户：不受「每天一次」限制
_PRIVILEGED_USERS = _cfg.ADMIN_SET


def _conn():
    return sqlite3.connect(DB)


def _ensure_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wife_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            equip_name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'draw',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 老表迁移：早期版本没有 kind 列（全部视为『抽』）
    cols = {r[1] for r in cur.execute("PRAGMA table_info(wife_record)")}
    if "kind" not in cols:
        cur.execute("ALTER TABLE wife_record ADD COLUMN kind TEXT NOT NULL DEFAULT 'draw'")
    # 加速按 (group_id, date) 查今天已抽装备
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wife_group_date ON wife_record(group_id, date)")
    # 加速按 (user_id, date, kind) 统计个人当日配额
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_wife_user_date ON wife_record(user_id, date, kind)"
    )
    conn.commit()
    conn.close()


def _today():
    """当天日期字符串（本地时区），跨天即刷新。"""
    return time.strftime("%Y-%m-%d")


def _candidates():
    """所有可抽的 (equip_name, file) 列表。

    注意：equip 表每个稀有度一行，同名装备会 join 出多行，故需按
    equip_name 去重（illust_equip 里每个装备名只有一条、category 唯一）。
    """
    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(_CATS))
    cur.execute(
        f"""
        SELECT ie.equip_name, ie.file
        FROM illust_equip ie
        JOIN equip e ON e.name = ie.equip_name
        WHERE e.category IN ({placeholders})
          AND ie.file IS NOT NULL AND ie.file != ''
        GROUP BY ie.equip_name, ie.file
        """,
        _CATS,
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _today_used_names(group_id: str, date: str) -> set[str]:
    """今天该群所有人已抽过的装备名集合。"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT equip_name FROM wife_record WHERE group_id = ? AND date = ?",
        (group_id, date),
    )
    names = {r[0] for r in cur.fetchall()}
    conn.close()
    return names


def _user_today_count(user_id: str, date: str, kind: str) -> int:
    """该用户今天已用掉的次数（按 kind 分开统计：'draw' 抽 / 'swap' 换，跨群累计）。"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM wife_record WHERE user_id = ? AND date = ? AND kind = ?",
        (user_id, date, kind),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def _record(group_id: str, user_id: str, date: str, equip_name: str, kind: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO wife_record (group_id, user_id, date, equip_name, kind) VALUES (?,?,?,?,?)",
        (group_id, user_id, date, equip_name, kind),
    )
    conn.commit()
    conn.close()


def _pick(used_names: set[str]):
    """从候选中随机抽一个未用过的，返回 (equip_name, file) 或 None。"""
    pool = [c for c in _candidates() if c[0] not in used_names]
    if not pool:
        return None
    return random.choice(pool)


def _illust_path(file: str) -> Path | None:
    if not file:
        return None
    p = ILLUST_DIR / file
    return p if p.exists() else None


def _build_msg(prefix: str, equip_name: str, file: str) -> Message:
    """构造「XX老婆是XXX哦~」+ 立绘图 的消息。"""
    text = f"{prefix}老婆是{equip_name}哦~"
    p = _illust_path(file)
    if not p:
        # 立绘缺失时至少把文字发出来
        return Message(MessageSegment.text(text + "\n（立绘缺失）"))
    return Message(MessageSegment.text(text) + _media.image(p))


# 抽老婆
draw = on_command(
    "抽老婆",
    aliases={"随机老婆", "抽一个老婆"},
    block=True,
    priority=5,
)


@draw.handle()
async def handle_draw(event: GroupMessageEvent):
    if not await _switch.require(draw, event, "wife"):
        return
    _ensure_table()
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    date = _today()

    # 特权用户跳过次数限制
    if user_id not in _PRIVILEGED_USERS:
        if _user_today_count(user_id, date, "draw") >= 1:
            await draw.finish("你今天已经抽过老婆啦，明天再来吧~")

    # 随机一件，避开今天已抽过的
    used = _today_used_names(group_id, date)
    picked = _pick(used)
    if not picked:
        await draw.finish("今天的老婆都被抽完啦，明天再来吧~")
    equip_name, file = picked

    _record(group_id, user_id, date, equip_name, "draw")
    await draw.finish(_build_msg("你今天的", equip_name, file))


# 换老婆
swap = on_command(
    "换老婆",
    aliases={"更换老婆", "换一个", "换一个老婆"},
    block=True,
    priority=5,
)


@swap.handle()
async def handle_swap(event: GroupMessageEvent):
    if not await _switch.require(swap, event, "wife"):
        return
    _ensure_table()
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    date = _today()

    # 特权用户跳过次数限制
    if user_id not in _PRIVILEGED_USERS:
        if _user_today_count(user_id, date, "swap") >= 1:
            await swap.finish("你今天已经换过啦，明天再来吧~")
        if _user_today_count(user_id, date, "draw") < 1:
            await swap.finish("你今天还没抽老婆呢，先发「抽老婆」再换吧~")

    # 换一个：避开今天已抽过的（含自己 + 群里其他人）
    used = _today_used_names(group_id, date)
    picked = _pick(used)
    if not picked:
        await swap.finish("今天的老婆都被换完啦，明天再来吧~")
    equip_name, file = picked

    _record(group_id, user_id, date, equip_name, "swap")
    await swap.finish(_build_msg("新换的", equip_name, file))

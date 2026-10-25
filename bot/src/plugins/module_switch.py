# -*- coding: utf-8 -*-
"""群级功能开关：给没有开关的插件统一加「开启 / 关闭」。

用法（群主 / 管理员）：
  功能列表              -> 看本群各功能开关状态
  关闭功能 猜装备        -> 关掉某个功能（也可以用英文 key：guess）
  开启功能 猜装备        -> 重新打开
  关闭全部功能 / 开启全部功能

设计：
  - 状态存 module_switch 表，按 (group_id, module) 记录，**默认开启**，
    所以没动过的群行为和加开关之前完全一致
  - 开关命令本身不受开关影响，关掉的功能永远能重新开启
  - 各插件在 handler 开头调用 is_on() / require()，被关掉时静默返回或提示一句
  - 「公告」和「官网公告」有自己的专用开关，不在这张表里
"""
import sqlite3
import time

from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message
from pydantic import BaseModel

from . import _config

# module key -> 展示名（顺序即「功能列表」的输出顺序）
MODULES = {
    "equip": "装备查询",
    "illust": "立绘查询",
    "chara": "角色查询与语音",
    "guess": "猜装备",
    "wife": "抽老婆",
    "emote": "表情包",
    "autoreply": "固定回复",
    "player": "玩家查询",
    "dragon": "群龙王榜",
    "elite": "精英技能",
    "zombie": "僵尸娘图鉴",
}

# 别名：让「关闭功能 装备」「关闭功能 老婆」这类自然说法也能命中
ALIASES = {
    "equip": ["装备", "查装备", "图鉴", "装备图鉴"],
    "illust": ["立绘", "觉醒", "立绘查询", "cg", "觉醒立绘"],
    "chara": ["角色", "角色查询", "查角色", "语音", "角色语音"],
    "guess": ["猜装备", "猜图鉴", "竞猜", "游戏", "小游戏"],
    "wife": ["老婆", "抽老婆", "换老婆"],
    "emote": ["表情", "表情包", "斗图"],
    "autoreply": ["固定回复", "自动回复", "回复"],
    "player": ["玩家", "查玩家", "玩家名片", "名片"],
    "dragon": ["龙王", "群龙王", "龙王榜"],
    "elite": ["精英技能", "查询精英技能", "查询技能", "技能图鉴"],
    "zombie": ["僵尸娘", "查询僵尸娘", "怪物", "查询怪物", "怪物查询", "僵尸娘查询"],
}

# 全局管理员（不受群内角色限制）
_ADMIN_USERS = _cfg.ADMIN_SET


class Config(BaseModel):
    switch_admin_only: bool = True


_cfg = get_plugin_config(Config)
_ADMIN_ONLY = _cfg.switch_admin_only


def _conn():
    return sqlite3.connect(_config.DB)


def _ensure():
    conn = _conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_switch (
            group_id TEXT NOT NULL,
            module TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (group_id, module)
        )
        """
    )
    conn.commit()
    conn.close()


def is_on(group_id, module: str) -> bool:
    """该群该功能是否开启（没有记录 = 默认开启）。"""
    if module not in MODULES:
        return True
    _ensure()
    conn = _conn()
    row = conn.execute(
        "SELECT enabled FROM module_switch WHERE group_id = ? AND module = ?",
        (str(group_id), module),
    ).fetchone()
    conn.close()
    return True if row is None else bool(row[0])


def set_on(group_id, module: str, enabled: bool):
    _ensure()
    conn = _conn()
    conn.execute(
        "INSERT INTO module_switch (group_id, module, enabled) VALUES (?, ?, ?) "
        "ON CONFLICT(group_id, module) DO UPDATE SET "
        "enabled = excluded.enabled, updated_at = datetime('now', 'localtime')",
        (str(group_id), module, 1 if enabled else 0),
    )
    conn.commit()
    conn.close()


def states(group_id) -> dict:
    _ensure()
    conn = _conn()
    rows = dict(
        conn.execute(
            "SELECT module, enabled FROM module_switch WHERE group_id = ?",
            (str(group_id),),
        ).fetchall()
    )
    conn.close()
    return {k: bool(rows.get(k, 1)) for k in MODULES}


async def require(matcher, event: GroupMessageEvent, module: str) -> bool:
    """命令类 handler 用：被关闭时回一句提示并结束，返回 False。"""
    if is_on(event.group_id, module):
        return True
    await matcher.finish(f"「{MODULES.get(module, module)}」功能已被管理员关闭啦~")
    return False


def _resolve(name: str) -> str | None:
    """把用户输入解析成 module key：支持 key、展示名、别名、最长包含匹配。"""
    text = (name or "").strip().lower()
    if not text:
        return None
    for key in MODULES:
        if text == key or text == MODULES[key].lower():
            return key
    for key, aliases in ALIASES.items():
        if text in (a.lower() for a in aliases):
            return key
    # 包含匹配取最长的那个，避免「装备」抢走「猜装备」
    best, best_len = None, 0
    for key, aliases in ALIASES.items():
        for cand in [MODULES[key], *aliases]:
            c = cand.lower()
            if c in text and len(c) > best_len:
                best, best_len = key, len(c)
    return best


def _is_admin(event: GroupMessageEvent) -> bool:
    if not _ADMIN_ONLY:
        return True
    if str(event.user_id) in _ADMIN_USERS:
        return True
    role = getattr(event.sender, "role", None)
    return role in ("owner", "admin")


# ==================== 命令 ====================

off_cmd = on_command("关闭功能", aliases={"关闭模块", "禁用功能"}, block=True, priority=5)
on_cmd = on_command("开启功能", aliases={"开启模块", "启用功能"}, block=True, priority=5)
off_all = on_command("关闭全部功能", aliases={"关闭所有功能"}, block=True, priority=5)
on_all = on_command("开启全部功能", aliases={"开启所有功能"}, block=True, priority=5)
list_cmd = on_command("功能列表", aliases={"功能开关", "开关列表"}, block=True, priority=5)


@off_cmd.handle()
async def handle_off(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not _is_admin(event):
        await off_cmd.finish("只有群主或管理员才能改功能开关哦~")
    name = arg.extract_plain_text().strip()
    key = _resolve(name)
    if key is None:
        hint = "、".join(MODULES.values())
        await off_cmd.finish(f"没找到「{name}」这个功能，可开关的有：{hint}")
    set_on(event.group_id, key, False)
    await off_cmd.finish(f"「{MODULES[key]}」已关闭，发「开启功能 {MODULES[key]}」可以恢复~")


@on_cmd.handle()
async def handle_on(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not _is_admin(event):
        await on_cmd.finish("只有群主或管理员才能改功能开关哦~")
    name = arg.extract_plain_text().strip()
    key = _resolve(name)
    if key is None:
        hint = "、".join(MODULES.values())
        await on_cmd.finish(f"没找到「{name}」这个功能，可开关的有：{hint}")
    set_on(event.group_id, key, True)
    await on_cmd.finish(f"「{MODULES[key]}」已开启~")


@off_all.handle()
async def handle_off_all(event: GroupMessageEvent):
    if not _is_admin(event):
        await off_all.finish("只有群主或管理员才能改功能开关哦~")
    for key in MODULES:
        set_on(event.group_id, key, False)
    await off_all.finish("本群全部功能已关闭（公告类推送有自己的开关，不受影响）~")


@on_all.handle()
async def handle_on_all(event: GroupMessageEvent):
    if not _is_admin(event):
        await on_all.finish("只有群主或管理员才能改功能开关哦~")
    for key in MODULES:
        set_on(event.group_id, key, True)
    await on_all.finish("本群全部功能已开启~")


@list_cmd.handle()
async def handle_list(event: GroupMessageEvent):
    st = states(event.group_id)
    lines = ["【本群功能开关】"]
    for key, label in MODULES.items():
        lines.append(f"{'✅' if st[key] else '❌'} {label}")
    lines.append("")
    lines.append("切换：开启功能 <名称> / 关闭功能 <名称>")
    lines.append("公告类：开启公告（B站动态）、开启官网公告（官网公告）各自独立")
    await list_cmd.finish("\n".join(lines))

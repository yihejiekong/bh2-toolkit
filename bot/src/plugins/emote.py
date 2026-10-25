# -*- coding: utf-8 -*-
"""表情包插件：随机发一张崩坏学园2 官方表情。

交互：
  表情包              -> 从全部表情中随机抽一张发送
  表情包 琪亚娜        -> 从「子目录名/文件名」含「琪亚娜」的表情中随机抽一张
  随机表情包          -> 同上（无关键词）

命令别名：表情包 / 随机表情包 / 表情 / 发个表情

数据：materials/精选表情图/{表情包名}/{表情包名}_序号.{png|jpg|gif}
关键词匹配「子目录名 + 文件名」两者（角色名通常在子目录名里，如「琪亚娜四格表情」）。
"""
import random
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg

from . import _config, _media, module_switch as _switch

EMOTE_DIR = _config.EMOTE_DIR

# 支持的表情文件扩展名
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _all_emotes() -> list[Path]:
    """收集全部表情文件路径。"""
    if not EMOTE_DIR.exists():
        return []
    files = []
    for p in EMOTE_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
            files.append(p)
    return files


def _match_keyword(keyword: str) -> list[Path]:
    """按关键词匹配表情：子目录名或文件名（不含扩展名）包含关键词即命中。"""
    kw = keyword.lower()
    out = []
    for p in _all_emotes():
        # 匹配子目录名（角色名通常在这里）+ 文件名主体
        parent = p.parent.name.lower()
        stem = p.stem.lower()
        if kw in parent or kw in stem:
            out.append(p)
    return out


# 命令：表情包 [关键词]
emote = on_command(
    "表情包",
    aliases={"随机表情包", "表情", "发个表情", "来个表情"},
    block=True,
    priority=5,
)


@emote.handle()
async def handle_emote(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not await _switch.require(emote, event, "emote"):
        return
    keyword = arg.extract_plain_text().strip()

    # 按关键词筛选，无关键词则用全部
    if keyword:
        pool = _match_keyword(keyword)
        if not pool:
            await emote.finish(f"没有找到含「{keyword}」的表情捏~")
    else:
        pool = _all_emotes()
        if not pool:
            await emote.finish("表情包还没准备好捏，请联系管理员~")

    chosen = random.choice(pool)
    try:
        seg = _media.image(chosen)
    except FileNotFoundError:
        await emote.finish("表情文件缺失捏，请联系管理员~")
    await emote.finish(Message(seg))

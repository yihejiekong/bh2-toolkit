# -*- coding: utf-8 -*-
"""僵尸娘查询：汇总图 + 单只僵尸娘的（档案 / 全部技能说明）卡 + 合并演示动图。

交互：
  僵尸娘 / 查询僵尸娘 / 怪物查询 / 查询怪物 / 僵尸娘查询
      -> 回一张 58 只的汇总图（只发图）
  查询僵尸娘 鲨鱼娘 / 查询怪物 NO.57 / 怪物查询 57
      -> 回该僵尸娘的资料卡（含全部技能文案）+ 一张合并演示动图
  （15 分钟内）直接回复编号 57
      -> 回第 57 号的资料卡 + 合并演示

素材：MATERIAL_ROOT/僵尸娘/{僵尸娘汇总.png, index.json, cards/*.png, gif/*.gif}
数据来源：官网 https://www.benghuai.com/data/ 僵尸娘专栏（58 只）。
"""
import json
import re
from pathlib import Path

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

from . import _config, _media, _session, module_switch as _switch

MODULE = "zombie"
SESSION_TYPE = "zombie"
SESSION_TTL = 900          # 15 分钟
MAX_MATCH = 12             # 模糊匹配最多列这么多

ROOT = _config.MATERIAL_ROOT / "僵尸娘"
CARDS = ROOT / "cards"
GIFS = ROOT / "gif"
SUMMARY = ROOT / "僵尸娘汇总.png"

try:
    _INDEX = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
except Exception:  # noqa: BLE001
    _INDEX = []
BY_ID = {int(x["id"]): x for x in _INDEX}

_HEAD = r"(?:查询僵尸娘|僵尸娘查询|查询怪物|怪物查询|僵尸娘|怪物)"

RE_LIST = re.compile(r"^\s*%s\s*$" % _HEAD)
RE_ARG = re.compile(r"^\s*%s\s*(?:no\.?\s*|#)?(.{1,20})$" % _HEAD, re.I)
RE_NUM = re.compile(r"^\s*(\d{1,2})\s*号?\s*$")


def _card(entry) -> Path | None:
    p = CARDS / Path(entry["card"]).name
    return p if p.exists() else None


def _demo(entry) -> Path | None:
    g = entry.get("gif")
    if not g:
        return None
    p = GIFS / Path(g).name
    return p if p.exists() else None


def _match(token: str):
    """编号 / 全名 / 包含。返回命中的 entry 列表。"""
    t = token.strip()
    t = re.sub(r"^(?:no\.?|#)\s*", "", t, flags=re.I)
    t = re.sub(r"号$", "", t).strip()
    if t.isdigit():
        e = BY_ID.get(int(t))
        return [e] if e else []
    exact = [x for x in _INDEX if x["name"] == t]
    if exact:
        return exact
    return [x for x in _INDEX if t and t in x["name"]]


def _detail_message(entry) -> Message:
    msg = Message()
    card = _card(entry)
    if card:
        msg += _media.image(card)
    else:
        msg += MessageSegment.text("（资料卡缺失）")
    demo = _demo(entry)
    if demo:
        msg += _media.image(demo)
    return msg


def _list_text(entries) -> str:
    lines = ["共 %d 只僵尸娘，回复编号或名称查看详情（15 分钟内有效）：" % len(entries)]
    for i, e in enumerate(entries, 1):
        lines.append("%d. %s（NO.%02d）" % (i, e["name"], int(e["id"])))
    if len(entries) > MAX_MATCH:
        lines.append("…… 一次最多列 %d 个，试试更精确的关键词" % MAX_MATCH)
    return "\n".join(lines)


matcher = on_regex(r"^\s*%s" % _HEAD, block=True, priority=6)


@matcher.handle()
async def _(event: GroupMessageEvent):
    if not await _switch.require(matcher, event, MODULE):
        return
    text = event.get_plaintext().strip()

    # 只发了指令：回汇总图（只发图不带文字）
    if RE_LIST.match(text):
        if not SUMMARY.exists():
            await matcher.finish("（汇总图缺失）")
        _session.set_session((event.group_id, event.user_id), SESSION_TYPE, _INDEX, SESSION_TTL)
        await matcher.finish(Message(_media.image(SUMMARY)))

    m = RE_ARG.match(text)
    if not m:
        await matcher.finish("用法：僵尸娘 / 查询僵尸娘 鲨鱼娘 / 查询怪物 NO.57")
    token = m.group(1).strip()
    hits = _match(token)
    if not hits:
        await matcher.finish("没有找到「%s」这只僵尸娘，发「僵尸娘」看全部列表~" % token)
    if len(hits) == 1:
        await matcher.finish(_detail_message(hits[0]))
    hits = hits[:MAX_MATCH]
    _session.set_session((event.group_id, event.user_id), SESSION_TYPE, hits, SESSION_TTL)
    await matcher.finish(_list_text(hits))


number = on_regex(r"^\s*\d{1,2}\s*号?\s*$", block=False, priority=10)


@number.handle()
async def _(event: GroupMessageEvent):
    if not _switch.is_on(event.group_id, MODULE):
        return
    key = (event.group_id, event.user_id)
    sess = _session.get_session(key, SESSION_TYPE)
    if not sess:
        return
    m = RE_NUM.match(event.get_plaintext().strip())
    if not m:
        return
    n = int(m.group(1))
    items = sess["items"]
    if not (1 <= n <= len(items)):
        await number.finish("序号超出范围（当前共 %d 项）" % len(items))
    entry = items[n - 1]
    _session.clear(key)
    await number.finish(_detail_message(entry))

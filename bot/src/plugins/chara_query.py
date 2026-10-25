# -*- coding: utf-8 -*-
"""角色查询插件（官网角色卡 + 角色语音）。

交互：
  查询角色 琪亚娜      -> 发送角色卡图片 + 一条随机日语语音 + 一条随机中文语音
  角色语音 琪亚娜      -> 随机发一条中文语音
  角色语音 琪亚娜 日文  -> 随机发一条日文语音

数据：角色卡目录 roles.json（build_chara_cards.py 生成，目录见 _config.CHARA_DIR）
语音：全部本地化在 角色卡目录/{id}/voice/{china|japan}/00X.mp3，不联网下载。
"""
import json
import random
import re
from pathlib import Path

from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg

from . import _config, _media, module_switch as _switch

CHARA_DIR = _config.CHARA_DIR
ROLES_JSON = CHARA_DIR / "roles.json"


def _load_roles():
    try:
        return json.loads(ROLES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _match_role(roles: dict, keyword: str):
    """按中文名/英文名/id 模糊匹配角色，返回 (chara_id, info) 或 None。"""
    keyword = keyword.strip().lower()
    if not keyword:
        return None
    # 精确中文名
    for cid, info in roles.items():
        if keyword == info["cn"] or keyword == info["cn"].replace("·", ""):
            return cid, info
    # 包含匹配
    for cid, info in roles.items():
        if keyword in info["cn"].lower() or keyword in info["en"].lower() or keyword == cid:
            return cid, info
    return None


def _pick_local_voice(chara_id: str, lang: str) -> Path | None:
    """从本地 voice 目录随机挑一条语音。lang: china / japan / yueyu"""
    vdir = CHARA_DIR / chara_id / "voice" / lang
    if not vdir.exists():
        return None
    files = list(vdir.glob("*.mp3"))
    return random.choice(files) if files else None


# ---- 角色卡查询 ----
def _has_card(event: GroupMessageEvent) -> bool:
    text = event.get_plaintext().strip()
    return bool(re.fullmatch(r"(?:查询角色|角色查询|查角色)[\s]*(.+)", text))


chara_card = on_command("查询角色", aliases={"角色查询", "查角色"}, block=False, priority=50)


@chara_card.handle()
async def handle_card(event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _switch.require(chara_card, event, "chara"):
        return
    roles = _load_roles()
    keyword = args.extract_plain_text().strip()
    hit = _match_role(roles, keyword)
    if not hit:
        if keyword:
            await chara_card.finish("没有找到这个角色捏，请检查名字~（可查：琪亚娜、芽衣、布洛妮娅…）")
        await chara_card.finish("用法：查询角色 <角色名>，比如「查询角色 琪亚娜」")

    cid, info = hit
    png = CHARA_DIR / f"{cid}_card.png"
    if not png.exists():
        await chara_card.finish("该角色的卡片还没生成，请管理员先运行 build_chara_cards.py~")

    # 图片和语音不能合并成一条消息，分三次发送
    await chara_card.send(_media.image(png))
    jp = _pick_local_voice(cid, "japan")
    if jp:
        await chara_card.send(_media.record(jp))
    cn = _pick_local_voice(cid, "china")
    if cn:
        await chara_card.send(_media.record(cn))
    await chara_card.finish()


# ---- 角色语音 ----
chara_voice = on_regex(
    r"^(?:角色语音|查询角色语音|查角色语音)[\s]*(\S+?)(?:[\s]*(中文|日文))?[\s]*$",
    block=False, priority=50,
)


@chara_voice.handle()
async def handle_voice(event: GroupMessageEvent):
    if not await _switch.require(chara_voice, event, "chara"):
        return
    text = event.get_plaintext().strip()
    m = re.match(
        r"^(?:角色语音|查询角色语音|查角色语音)[\s]*(\S+?)(?:[\s]*(中文|日文))?[\s]*$",
        text,
    )
    if not m:
        return
    roles = _load_roles()
    keyword, lang_word = m.group(1), m.group(2)
    hit = _match_role(roles, keyword)
    if not hit:
        await chara_voice.finish("没有找到这个角色捏，请检查名字~")
        return
    cid, _ = hit
    lang = "japan" if lang_word == "日文" else ("yueyu" if lang_word == "粤语" else "china")
    voice_path = _pick_local_voice(cid, lang)
    if not voice_path:
        await chara_voice.finish("该角色没有本地语音文件，请管理员先运行 build_chara_cards.py~")
        return
    await chara_voice.finish(_media.record(voice_path))

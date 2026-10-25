# -*- coding: utf-8 -*-
"""猜装备小游戏插件。

交互：
  猜装备            -> 选择难度（1.简单 2.普通 3.困难）
  1/2/3            -> 确定难度，随机发一张装备图标，进入答题
  答对            -> 鼓励句，进入下一关；全通后「woc，崩批！」
  超时/答错不判死 -> 计时内可继续答，超时则嘲讽 + 正确答案，游戏结束

难度规则：
  简单：6关，50s/关，6星及以上（武器/服装/徽章）
  普通：8关，35s/关，4星及以上（武器/服装/使魔/徽章）
  困难：10关，25s/关，全星级全类别

排行榜：每月1号重置；通关按用时升序排前，失败按已通过关卡数降序排后。
"""
import random
import sqlite3
import time
from pathlib import Path

from nonebot import on_command, on_message, on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.rule import Rule

from . import _session, _config, _media, module_switch as _switch

DB = _config.DB
ICON_DIR = _config.ICON_DIR

# 难度配置: {difficulty: (关卡数, 每关限时秒, 最小稀有度, 是否含使魔)}
DIFF_CFG = {
    1: {"levels": 6, "time": 50, "min_rarity": 6, "with_pet": False, "name": "简单"},
    2: {"levels": 8, "time": 35, "min_rarity": 4, "with_pet": True, "name": "普通"},
    3: {"levels": 10, "time": 25, "min_rarity": 0, "with_pet": True, "name": "困难"},
}

# 游戏状态: key=(group_id, user_id) -> {
#   "difficulty", "level"(当前第几关，从1开始), "equip"(当前目标装备tuple),
#   "deadline"(截止时间戳), "start_ts"(开始时间), "state"("selecting"/"playing")
# }
_games = {}


def _conn():
    return sqlite3.connect(DB)


def _ensure_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guess_rank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            nickname TEXT,
            difficulty INTEGER NOT NULL,
            cleared INTEGER NOT NULL,
            pass_count INTEGER NOT NULL,
            clear_time REAL,
            month TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _current_month():
    return time.strftime("%Y-%m")


def _pick_equip(difficulty: int):
    """按难度随机抽一件装备。返回 (id, name, rarity, category, icon_file, alias)。"""
    cfg = DIFF_CFG[difficulty]
    conn = _conn()
    cur = conn.cursor()
    if cfg["with_pet"]:
        cats = ("武器", "服装", "徽章", "使魔")
    else:
        cats = ("武器", "服装", "徽章")
    placeholders = ",".join("?" * len(cats))
    cur.execute(
        f"""
        SELECT id, name, rarity, category, icon_file, alias
        FROM equip
        WHERE rarity >= ? AND category IN ({placeholders}) AND icon_file IS NOT NULL
        """,
        (cfg["min_rarity"], *cats),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return None
    return random.choice(rows)


def _icon_path(icon_file: str) -> Path | None:
    if not icon_file:
        return None
    p = ICON_DIR / icon_file
    if p.exists():
        return p
    return None


def _match_answer(answer: str, name: str, alias: str) -> bool:
    """命中名字关键字词即可（缩写/别名互含匹配）。"""
    answer = answer.strip()
    if not answer:
        return False
    if answer in name or name in answer:
        return True
    if alias:
        for a in alias.split(","):
            a = a.strip()
            if not a:
                continue
            if answer in a or a in answer:
                return True
    return False


def _praise():
    return random.choice([
        "嘭嘭！好厉害~回答正确！",
        "哇，太强啦！这都认得出来！",
        "好耶！答对咯，真棒~",
        "嘿嘿，难不倒你嘛，正确！",
        "厉害厉害！果然是老玩家~",
        "答对啦！给你点个赞~",
    ])


def _tease(correct_name: str):
    return random.choice([
        f"失败咯~正确答案是{correct_name}，杂鱼群友~哼哼~杂鱼！杂鱼~",
        f"时间到啦~答案是{correct_name}哦，这都猜不到嘛，杂鱼~",
        f"嘿嘿，答案是{correct_name}呢，笨蛋群友~杂鱼！",
        f"没猜出来吧~正确答案是{correct_name}，真是杂鱼呢~",
    ])


# ---- 难度选择状态 Rule ----
def _is_selecting(event: GroupMessageEvent) -> bool:
    key = (event.group_id, event.user_id)
    g = _games.get(key)
    return bool(g and g.get("state") == "selecting")


# ---- 答题状态 Rule ----
def _is_playing(event: GroupMessageEvent) -> bool:
    key = (event.group_id, event.user_id)
    g = _games.get(key)
    return bool(g and g.get("state") == "playing")


# ---- 命令：猜装备 ----
guess = on_command("猜装备", aliases={"猜图鉴", "装备竞猜"}, block=True, priority=5)


@guess.handle()
async def handle_guess(event: GroupMessageEvent):
    if not await _switch.require(guess, event, "guess"):
        return
    key = (event.group_id, event.user_id)
    _games[key] = {"state": "selecting", "difficulty": None}
    await guess.finish(
        "请选择难度：\n"
        "1. 简单（6关，6星+）\n"
        "2. 普通（8关，4星+）\n"
        "3. 困难（10关，全星级）"
    )


# ---- 难度选择：输入 1/2/3 ----
select_diff = on_regex(r"^[123]$", rule=Rule(_is_selecting), block=True, priority=6)


@select_diff.handle()
async def handle_select_diff(event: GroupMessageEvent):
    if not _switch.is_on(event.group_id, "guess"):
        return
    key = (event.group_id, event.user_id)
    difficulty = int(event.get_plaintext().strip())
    cfg = DIFF_CFG[difficulty]

    equip = _pick_equip(difficulty)
    if equip is None:
        del _games[key]
        await select_diff.finish("哎呀，抽不到装备呢，换个难度试试吧~")

    now = time.time()
    _games[key] = {
        "state": "playing",
        "difficulty": difficulty,
        "level": 1,
        "equip": equip,
        "deadline": now + cfg["time"],
        "start_ts": now,
    }

    icon = _icon_path(equip[4])
    seg = _media.image(icon) if icon else MessageSegment.text("（图标缺失）")
    await select_diff.finish(
        Message(f"【{cfg['name']} · 第1/{cfg['levels']}关】请说出该装备名称，限时{cfg['time']}秒~\n")
        + seg
    )


# ---- 答题监听 ----
answer = on_message(rule=Rule(_is_playing), block=False, priority=90)


@answer.handle()
async def handle_answer(event: GroupMessageEvent):
    if not _switch.is_on(event.group_id, "guess"):
        return
    key = (event.group_id, event.user_id)
    g = _games.get(key)
    if not g or g["state"] != "playing":
        return

    cfg = DIFF_CFG[g["difficulty"]]
    equip = g["equip"]
    name = equip[1]
    alias = equip[5]
    answer_text = event.get_plaintext().strip()

    # 超时判断
    if time.time() > g["deadline"]:
        # 记录失败
        _record(g, key, event, cleared=False, pass_count=g["level"] - 1)
        del _games[key]
        await answer.finish(_tease(name))
        return

    # 命中判断
    if _match_answer(answer_text, name, alias):
        # 是否通关
        if g["level"] >= cfg["levels"]:
            clear_time = time.time() - g["start_ts"]
            _record(g, key, event, cleared=True, pass_count=cfg["levels"], clear_time=clear_time)
            del _games[key]
            await answer.finish(
                _praise() + "\n"
                f"恭喜通关【{cfg['name']}】全部{cfg['levels']}关！用时{clear_time:.1f}秒~"
                "\nwoc，崩批！"
            )
            return

        # 进入下一关
        equip = _pick_equip(g["difficulty"])
        if equip is None:
            _record(g, key, event, cleared=False, pass_count=g["level"] - 1)
            del _games[key]
            await answer.finish("哎呀，抽不到装备了，游戏结束~")
            return

        now = time.time()
        g["level"] += 1
        g["equip"] = equip
        g["deadline"] = now + cfg["time"]

        icon = _icon_path(equip[4])
        seg = _media.image(icon) if icon else MessageSegment.text("（图标缺失）")
        await answer.finish(
            Message(_praise() + f"\n【{cfg['name']} · 第{g['level']}/{cfg['levels']}关】请说出该装备名称，限时{cfg['time']}秒~\n")
            + seg
        )
        return

    # 答错：不回复，继续等（避免刷屏）


def _record(g, key, event, cleared, pass_count, clear_time=None):
    """写入排行榜记录。"""
    _ensure_table()
    conn = _conn()
    cur = conn.cursor()
    sender = getattr(event, "sender", None)
    nickname = None
    if sender is not None:
        nickname = getattr(sender, "card", None) or getattr(sender, "nickname", None)
    if not nickname:
        nickname = str(key[1])
    cur.execute(
        """
        INSERT INTO guess_rank (group_id, user_id, nickname, difficulty, cleared, pass_count, clear_time, month)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (str(key[0]), str(key[1]), nickname, g["difficulty"], 1 if cleared else 0,
         pass_count, clear_time, _current_month()),
    )
    conn.commit()
    conn.close()


# ---- 排行榜查询 ----
rank = on_command(
    "猜装备排行榜",
    aliases={"查询排行榜", "排行榜", "猜装备榜", "排行"},
    block=True,
    priority=5,
)


@rank.handle()
async def handle_rank(event: GroupMessageEvent, arg: Message = CommandArg()):
    if not await _switch.require(rank, event, "guess"):
        return
    _ensure_table()
    group_id = str(event.group_id)
    month = _current_month()
    conn = _conn()
    cur = conn.cursor()

    lines = [f"【{month.replace('-', '年')}月 猜装备排行榜】"]
    for diff, dname in [(1, "简单"), (2, "普通"), (3, "困难")]:
        cur.execute(
            """
            SELECT user_id, nickname, cleared, pass_count, clear_time
            FROM guess_rank
            WHERE group_id=? AND difficulty=? AND month=?
            ORDER BY cleared DESC, clear_time ASC, pass_count DESC
            """,
            (group_id, diff, month),
        )
        rows = cur.fetchall()
        # 每用户取最佳记录（去重，按 user_id）
        best = {}
        for uid, nickname, cleared, pc, ct in rows:
            if uid not in best:
                best[uid] = (nickname, cleared, pc, ct)
        ranked = [(uid, *best[uid]) for uid in best][:10]

        lines.append(f"\n——{dname}——")
        if not ranked:
            lines.append("暂无记录")
            continue
        for i, (uid, nickname, cleared, pc, ct) in enumerate(ranked, 1):
            name = nickname or uid
            if cleared:
                lines.append(f"{i}. {name} 通关 {ct:.1f}s")
            else:
                lines.append(f"{i}. {name} 通过 {pc} 关")
    conn.close()
    await rank.finish("\n".join(lines))

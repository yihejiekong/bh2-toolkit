# -*- coding: utf-8 -*-
"""固定回复插件（分群隔离 + 全局固定回复）。

作用域：
  - **群内回复**：`group_id` 存群号，只有那个群能触发、能看见、能改。A 群配的回复 B 群
    既不会触发也看不到。
  - **全局回复**：`group_id IS NULL`，所有群都触发，且只有 _BOT_ADMIN_USERS 能改/删。

权限：
  - 新增群内回复：本群任何成员都能加（各自群互不干扰）。
  - 修改/删除群内回复：本群管理员/群主、这条回复的添加人本人、bot 管理员。
  - 全局回复：只有 bot 管理员（.env 里的 BOT_ADMINS）能增、改、删。
  - 查询、触发：所有人。

交互：
  新增回复                 -> 新增一条【本群】回复（任何群员）
  新增全局回复             -> 新增一条【所有群】回复（仅 bot 管理员）
  用户: xxx/abc           -> 记录触发词（用 / 分隔，xxx 或 abc 均可触发），提示输入回复内容
  用户: 文字/图片/文字+图片 -> 记录回复内容，回复「已记录」
  查询回复                 -> 列出全局 + 本群的触发词，回复序号查看（0 翻页）
  修改回复 <触发词>        -> 修改指定触发词的回复（权限见上）
  删除回复 <触发词>        -> 删除指定触发词对应的回复（权限见上）

  后续：群里有人发送 xxx 或 abc（精确匹配），bot 自动回复已记录的内容。
  匹配顺序：全局回复优先，其次本群回复。

数据：auto_reply 表（id / group_id / triggers / text / images / created_at）。
图片保存到素材目录 materials/固定回复/ 下，回放走 base64。
"""
import base64
import json
import re
import sqlite3
import time
from pathlib import Path

import httpx
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.params import CommandArg

from . import _config, _media, module_switch as _switch

DB = _config.DB
REPLY_IMG_DIR = _config.MATERIAL_ROOT / "固定回复"

PAGE_SIZE = 9
SESSION_TTL = 120  # 新增/修改流程的超时（秒）

# 进行中的新增/修改流程：
# key=(group_id, user_id) -> {"stage": "trigger"|"content", "mode": "add"|"edit:rid",
#                             "triggers": str, "expire": ts}
_pending = {}


def _conn():
    return sqlite3.connect(DB)


def _ensure_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auto_reply (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER DEFAULT NULL,
            created_by INTEGER DEFAULT NULL,
            triggers TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            images TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 老表补列：历史 4 条数据保持 NULL = 全局，与用户「这四条全群通用」的设定一致
    cols = [r[1] for r in cur.execute("PRAGMA table_info(auto_reply)")]
    if "group_id" not in cols:
        cur.execute("ALTER TABLE auto_reply ADD COLUMN group_id INTEGER DEFAULT NULL")
    if "created_by" not in cols:
        cur.execute("ALTER TABLE auto_reply ADD COLUMN created_by INTEGER DEFAULT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auto_reply_group ON auto_reply(group_id)")
    conn.commit()
    conn.close()


def _ensure_img_dir():
    REPLY_IMG_DIR.mkdir(parents=True, exist_ok=True)


# ==================== 数据操作 ====================

def _split_triggers(s: str) -> list[str]:
    return [t.strip() for t in s.split("/") if t.strip()]


def _all_rows(group_id=None):
    """全局回复 + 指定群的回复（全局在前，各自按新到旧）。

    group_id=None 时只返回全局回复（用于全局管理场景）。
    """
    conn = _conn()
    cur = conn.cursor()
    if group_id is None:
        cur.execute(
            "SELECT id, triggers, text, images, group_id FROM auto_reply "
            "WHERE group_id IS NULL ORDER BY id DESC"
        )
    else:
        cur.execute(
            "SELECT id, triggers, text, images, group_id FROM auto_reply "
            "WHERE group_id IS NULL OR group_id=? "
            "ORDER BY (group_id IS NULL) DESC, id DESC",
            (int(group_id),),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def _find_by_trigger(trigger: str, group_id=None):
    """按触发词精确匹配：全局回复优先，其次本群；看不到别的群。"""
    for row in _all_rows(group_id):
        rid, triggers, text, images, gid = row
        if trigger in _split_triggers(triggers):
            return row
    return None


def _insert(triggers: str, text: str, images: list[str], group_id=None, created_by=None):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO auto_reply (group_id, created_by, triggers, text, images) VALUES (?, ?, ?, ?, ?)",
        (None if group_id is None else int(group_id),
         None if created_by is None else int(created_by),
         triggers, text, json.dumps(images, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def _update(rid: int, triggers: str, text: str, images: list[str]):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE auto_reply SET triggers=?, text=?, images=? WHERE id=?",
        (triggers, text, json.dumps(images, ensure_ascii=False), rid),
    )
    conn.commit()
    conn.close()


def _delete(rid: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM auto_reply WHERE id=?", (rid,))
    conn.commit()
    conn.close()


# ==================== 图片下载 ====================

def _new_img_name(ext: str) -> str:
    return f"{int(time.time() * 1000)}.{ext}"


async def _download_image(url: str) -> Path | None:
    if not url:
        return None
    _ensure_img_dir()
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200 or not resp.content:
                return None
            ctype = resp.headers.get("content-type", "")
            ext = "jpg"
            if "png" in ctype:
                ext = "png"
            elif "gif" in ctype:
                ext = "gif"
            elif "webp" in ctype:
                ext = "webp"
            p = REPLY_IMG_DIR / _new_img_name(ext)
            p.write_bytes(resp.content)
            return p
    except Exception:  # noqa: BLE001
        return None


async def _download_via_api(bot: Bot, file: str) -> Path | None:
    """用 OneBot get_image API 兜底获取图片，返回本地路径。

    注意：标准 get_image 返回的 file 是 NapCat 容器内路径，宿主机读不到；
    这里只处理「返回 base64 / http url」的少数实现，其余返回 None。
    """
    if not file:
        return None
    try:
        info = await bot.get_image(file=file)
        if isinstance(info, dict):
            # http url 优先
            for key in ("url", "path", "file"):
                val = info.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return await _download_image(val)
            # base64 数据（file 或 data 字段）
            for key in ("data", "file"):
                raw = info.get(key)
                if not isinstance(raw, str):
                    continue
                if raw.startswith("base64://"):
                    raw = raw[len("base64://"):]
                # 只当内容是合法 base64 时才解码（排除容器路径等非 base64 串）
                if re.fullmatch(r"[A-Za-z0-9+/=]+", raw) and len(raw) % 4 == 0:
                    try:
                        return _save_image_bytes(base64.b64decode(raw))
                    except Exception:  # noqa: BLE001
                        return None
        return None
    except Exception:  # noqa: BLE001
        return None


def _save_image_bytes(data: bytes, ext: str = "jpg") -> Path | None:
    """把图片字节写入本地，返回路径。"""
    if not data:
        return None
    _ensure_img_dir()
    p = REPLY_IMG_DIR / _new_img_name(ext)
    p.write_bytes(data)
    return p


async def _split_msg(bot: Bot, msg: Message) -> tuple[str, list[str]]:
    """分离文字与图片，返回 (纯文字, 已保存图片文件名列表)。

    图片获取按优先级尝试：
    1. segment 的 url 字段（http 直下）
    2. segment 的 file 字段若是 base64:// 直接解码
    3. file 字段若是 http:// 直接下载
    4. 兜底走 get_image API（返回可能是路径/base64，尽力解析）
    """
    text_parts = []
    img_names = []
    for seg in msg:
        if seg.type == "text":
            text_parts.append(seg.data.get("text", ""))
        elif seg.type == "image":
            url = seg.data.get("url", "")
            file = seg.data.get("file", "")
            saved = None

            # 1. url 直下
            if url and url.startswith("http"):
                saved = await _download_image(url)
            # 2. file 是 base64
            if saved is None and file and file.startswith("base64://"):
                saved = _save_image_bytes(base64.b64decode(file[len("base64://"):]))
            # 3. file 是 http url
            if saved is None and file and file.startswith("http"):
                saved = await _download_image(file)
            # 4. 兜底 get_image
            if saved is None and file:
                saved = await _download_via_api(bot, file)

            if saved is not None:
                img_names.append(saved.name)
    return "".join(text_parts).strip(), img_names


# ==================== 回复内容构建 ====================

def _build_reply(text: str, images: list[str]) -> Message:
    msg = Message()
    if text:
        msg += MessageSegment.text(text)
    for img in images:
        p = REPLY_IMG_DIR / img
        if p.exists():
            msg += _media.image(p)
        else:
            msg += MessageSegment.text("（图片缺失）")
    return msg if msg else Message(MessageSegment.text("（空回复）"))


# ==================== 进行中流程状态 ====================

def _key(event: GroupMessageEvent):
    return (str(event.group_id), str(event.user_id))


def _set_pending(event: GroupMessageEvent, stage: str, mode: str, triggers: str = "",
                 scope: str = "group"):
    _pending[_key(event)] = {
        "stage": stage, "mode": mode, "triggers": triggers,
        "scope": scope,  # group=本群回复 / global=全局回复
        "expire": time.time() + SESSION_TTL,
    }


def _get_pending(event: GroupMessageEvent):
    entry = _pending.get(_key(event))
    if not entry or time.time() > entry["expire"]:
        _pending.pop(_key(event), None)
        return None
    return entry


def _clear_pending(event: GroupMessageEvent):
    _pending.pop(_key(event), None)


async def _send(bot: Bot, event: GroupMessageEvent, text: str):
    await bot.send(event=event, message=Message(MessageSegment.text(text)))


# ==================== 命令 ====================

# bot 管理员：唯一能改「全局回复」的人；同时也是所有群回复的管理员
_BOT_ADMIN_USERS = _cfg.ADMIN_SET
_GLOBAL_ONLY_MSG = "只有指定管理员能改全局固定回复哦~"
_GROUP_ADMIN_MSG = "这条不是你加的，只有本群管理员/群主或添加人本人能改哦~"


def _is_bot_admin(event: GroupMessageEvent) -> bool:
    return str(event.user_id) in _BOT_ADMIN_USERS


def _is_group_admin(event: GroupMessageEvent) -> bool:
    role = getattr(getattr(event, "sender", None), "role", "") or ""
    return role in ("admin", "owner")


def _created_by(rid: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT created_by FROM auto_reply WHERE id=?", (rid,))
    row = cur.fetchone()
    conn.close()
    return None if not row else row[0]


def _can_modify(event: GroupMessageEvent, row_group_id, rid=None) -> bool:
    """权限：bot 管理员全通；全局回复只有 bot 管理员；
    群内回复 = 本群群管/群主，或这条回复的添加人本人。"""
    if _is_bot_admin(event):
        return True
    if row_group_id is None:
        return False
    if str(row_group_id) != str(event.group_id):
        return False
    if _is_group_admin(event):
        return True
    if rid is not None:
        cb = _created_by(rid)
        return cb is not None and str(cb) == str(event.user_id)
    return False


def _deny_msg(row_group_id) -> str:
    return _GLOBAL_ONLY_MSG if row_group_id is None else _GROUP_ADMIN_MSG


def _dup_triggers(triggers: str, group_id) -> list[str]:
    """返回已被占用的触发词（全局或本群），用于新增/修改时拦截冲突。"""
    return [t for t in _split_triggers(triggers) if _find_by_trigger(t, group_id)]


add = on_command("新增回复", aliases={"添加回复", "增加回复"}, block=True, priority=5)


@add.handle()
async def handle_add(event: GroupMessageEvent):
    # 任何群员都能给自己群加回复；改/删仍限群管或 bot 管理员，避免互相删配置
    _ensure_table()
    _set_pending(event, "trigger", "add", scope="group")
    await add.finish(
        "请输入触发字段（多个触发词用 / 分隔，例如：xxx/abc）\n本条回复只在本群生效。"
    )


add_global = on_command("新增全局回复", aliases={"添加全局回复"}, block=True, priority=5)


@add_global.handle()
async def handle_add_global(event: GroupMessageEvent):
    if not _is_bot_admin(event):
        await add_global.finish(_GLOBAL_ONLY_MSG)
    _ensure_table()
    _set_pending(event, "trigger", "add", scope="global")
    await add_global.finish(
        "请输入触发字段（多个触发词用 / 分隔）\n本条回复会对所有群生效。"
    )


edit = on_command("修改回复", aliases={"更改回复", "编辑回复"}, block=True, priority=5)


@edit.handle()
async def handle_edit(event: GroupMessageEvent, arg: Message = CommandArg()):
    _ensure_table()
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await edit.finish("用法：修改回复 <触发词>")
    row = _find_by_trigger(keyword, event.group_id)
    if not row:
        await edit.finish(f"本群没有找到触发词「{keyword}」对应的回复哦~")
    rid, triggers, text, images, gid = row
    if not _can_modify(event, gid, rid):
        await edit.finish(_deny_msg(gid))
    _set_pending(event, "trigger", f"edit:{rid}", triggers,
                 scope=("global" if gid is None else "group"))
    scope_tag = "【全局】" if gid is None else "【本群】"
    await edit.finish(
        f"{scope_tag}当前触发词：{triggers}\n请重新输入触发字段（多个用 / 分隔；不修改可直接重发原触发词）"
    )


delete = on_command("删除回复", aliases={"移除回复", "删回复"}, block=True, priority=5)


@delete.handle()
async def handle_delete(event: GroupMessageEvent, arg: Message = CommandArg()):
    _ensure_table()
    keyword = arg.extract_plain_text().strip()
    if not keyword:
        await delete.finish("用法：删除回复 <触发词>")
    row = _find_by_trigger(keyword, event.group_id)
    if not row:
        await delete.finish(f"本群没有找到触发词「{keyword}」对应的回复哦~")
    rid, triggers, text, images, gid = row
    if not _can_modify(event, gid, rid):
        await delete.finish(_deny_msg(gid))
    _delete(rid)
    scope_tag = "（全局，所有群都不再触发）" if gid is None else ""
    await delete.finish(f"已删除触发词「{triggers}」对应的回复~{scope_tag}")


query = on_command("查询回复", aliases={"回复列表", "查看回复", "所有回复"}, block=True, priority=5)

_reply_sessions = {}  # key -> {"rows": [...], "page": 0, "expire": ts}


def _render_reply_page(rows, page):
    total = len(rows)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_rows = rows[start:end]
    n_global = sum(1 for r in rows if r[4] is None)
    lines = [
        f"共 {total} 条固定回复（全局 {n_global} + 本群 {total - n_global}），"
        f"第 {page + 1}/{total_pages} 页，回复序号查看（2分钟内有效）："
    ]
    for i, (rid, triggers, text, images, gid) in enumerate(page_rows, 1):
        preview = text if text else "（纯图片）"
        if len(preview) > 20:
            preview = preview[:20] + "…"
        tag = "【全局】" if gid is None else "【本群】"
        lines.append(f"{i}. {tag}{triggers}  →  {preview}")
    if page + 1 < total_pages:
        lines.append("0. 下一页")
    return lines


@query.handle()
async def handle_query(event: GroupMessageEvent):
    _ensure_table()
    rows = _all_rows(event.group_id)
    if not rows:
        await query.finish("本群还没有任何固定回复哦，群管用「新增回复」添加一条吧~")
    _reply_sessions[_key(event)] = {"rows": rows, "page": 0, "expire": time.time() + SESSION_TTL}
    lines = _render_reply_page(rows, 0)
    await query.finish("\n".join(lines))


# ==================== 进行中流程输入捕获 ====================

async def _handle_pending_input(event: GroupMessageEvent, bot: Bot):
    entry = _get_pending(event)
    if not entry:
        return False

    if entry["stage"] == "trigger":
        raw = event.get_plaintext().strip()
        if not raw:
            await _send(bot, event, "触发字段不能为空哦，请重新输入（多个用 / 分隔）")
            return True
        entry["stage"] = "content"
        entry["triggers"] = raw
        entry["expire"] = time.time() + SESSION_TTL
        await _send(bot, event, "已记录触发字段，现在请输入回复内容（可发文字、图片、或文字+图片）")
        return True

    if entry["stage"] == "content":
        text, img_names = await _split_msg(bot, event.get_message())
        if not text and not img_names:
            await _send(bot, event, "回复内容不能为空哦，请发文字或图片")
            return True
        triggers = entry["triggers"]
        scope = entry.get("scope", "group")
        target_gid = None if scope == "global" else int(event.group_id)
        is_edit = entry["mode"].startswith("edit:")
        rid = int(entry["mode"].split(":")[1]) if is_edit else None

        # 触发词冲突检查：不跟全局/本群已有回复撞车（修改时排除自己）
        dups = []
        for t in _split_triggers(triggers):
            hit = _find_by_trigger(t, event.group_id)
            if hit and (rid is None or hit[0] != rid):
                dups.append(t)
        if dups:
            where = "全局" if scope == "global" else "本群"
            await _send(
                bot, event,
                f"这些触发词已经被占用了：{'/'.join(dups)}\n"
                f"本次未保存，请换一个触发词，或先「删除回复」清掉旧的（当前仍在输入{where}回复内容）",
            )
            return True

        if is_edit:
            _update(rid, triggers, text, img_names)
            _clear_pending(event)
            await _send(bot, event, f"已更新触发词「{triggers}」的回复~")
        else:
            _insert(triggers, text, img_names, target_gid, created_by=event.user_id)
            _clear_pending(event)
            tag = "（全局，所有群生效）" if target_gid is None else "（仅本群生效）"
            await _send(bot, event, f"已记录~{tag}")
        return True

    return False


# ==================== 消息派发（顺序：进行中流程 > 触发词） ====================

# 统一入口处理「进行中流程输入」与「触发词精确匹配」。
# 注意：命令（新增/查询/修改/删除）优先级 5，已先被 on_command 拦截；
# 这里 priority 更高（数值更大=更低优先级），避免抢占命令。
dispatcher = on_message(block=False, priority=50)


@dispatcher.handle()
async def handle_dispatcher(event: GroupMessageEvent, bot: Bot):
    if not _switch.is_on(event.group_id, "autoreply"):
        return
    # 1. 进行中的新增/修改流程优先
    if _key(event) in _pending:
        handled = await _handle_pending_input(event, bot)
        if handled:
            await dispatcher.finish()
            return
    # 2. 触发词精确匹配（pending 流程的输入不会被当触发词；全局优先，其次本群）
    text = event.get_plaintext().strip()
    if text:
        row = _find_by_trigger(text, event.group_id)
        if row is not None:
            rid, triggers, ttext, images_json, gid = row
            images = json.loads(images_json or "[]")
            await dispatcher.finish(_build_reply(ttext, images))


# ==================== 查询回复分页数字 ====================

number = on_message(block=False, priority=60)


@number.handle()
async def handle_number(event: GroupMessageEvent, bot: Bot):
    if not _switch.is_on(event.group_id, "autoreply"):
        return
    sess = _reply_sessions.get(_key(event))
    if not sess or time.time() > sess["expire"]:
        _reply_sessions.pop(_key(event), None)
        return
    text = event.get_plaintext().strip()
    if not re.fullmatch(r"\d+", text):
        return
    num = int(text)
    rows = sess["rows"]
    total = len(rows)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    if num == 0:
        page = sess["page"]
        if page + 1 >= total_pages:
            await number.finish("已经是最后一页啦~")
        sess["page"] = page + 1
        sess["expire"] = time.time() + SESSION_TTL
        await number.finish("\n".join(_render_reply_page(rows, page + 1)))
        return

    page = sess["page"]
    start = page * PAGE_SIZE
    page_rows = rows[start:start + PAGE_SIZE]
    if num > len(page_rows):
        await number.finish(f"序号超出范围（本页共 {len(page_rows)} 条）")
        return
    rid, triggers, ttext, images_json, gid = page_rows[num - 1]
    images = json.loads(images_json or "[]")
    sess["expire"] = time.time() + SESSION_TTL
    first_trigger = triggers.split("/")[0]
    tag = "【全局】" if gid is None else "【本群】"
    msg = Message(MessageSegment.text(f"触发词：{tag}{triggers}\n"))
    msg += _build_reply(ttext, images)
    # 只有有权限的人才显示改/删提示，避免群友照抄后被拒
    if _can_modify(event, gid, rid):
        msg += MessageSegment.text(f"\n（修改：修改回复 {first_trigger}；删除：删除回复 {first_trigger}）")
    await number.finish(msg)


_ensure_table()

# -*- coding: utf-8 -*-
"""NapCat 掉线告警与守护状态。

配合 /usr/local/bin/napcat-guard.sh（systemd: napcat-guard.service）：
  - 守护脚本每分钟检查「容器 / QQ 进程 / 6099 端口」，异常就 docker restart napcat
  - 恢复后把掉线时长写进 /var/log/napcat-guard/pending.jsonl
  - 本插件在启动后和每 5 分钟读一次，私聊推给 bot 管理员，然后清空

命令：
  守护状态        查看守护最近事件与当前健康快照（仅 bot 管理员）
"""
import asyncio
import json
import os
import time

from nonebot import get_bots, get_driver, on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger
from nonebot.params import CommandArg

LOG_DIR = "/var/log/napcat-guard"
PENDING = os.path.join(LOG_DIR, "pending.jsonl")
EVENTS = os.path.join(LOG_DIR, "events.log")
ADMIN = _cfg.ADMIN_QQ

driver = get_driver()


def _fmt_dur(sec: int) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d 小时 %d 分 %d 秒" % (h, m, s)
    if m:
        return "%d 分 %d 秒" % (m, s)
    return "%d 秒" % s


def _load_pending() -> list:
    """读取并原子地挪走告警文件，避免重复推送。"""
    if not os.path.exists(PENDING):
        return []
    try:
        if os.path.getsize(PENDING) == 0:
            return []
        tmp = PENDING + ".flushing"
        os.replace(PENDING, tmp)
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning("[guard] 读取告警文件失败")
        return []
    try:
        with open(tmp, "r", encoding="utf-8", errors="replace") as f:
            return [l.strip() for l in f if l.strip()]
    except Exception:  # noqa: BLE001
        return []


def _requeue(lines: list) -> None:
    try:
        with open(PENDING, "a", encoding="utf-8") as f:
            for l in lines:
                f.write(l + "\n")
        try:
            os.chmod(PENDING, 0o664)
        except OSError:
            pass
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning("[guard] 告警回写失败")


def _build_text(lines: list) -> str:
    rows = []
    for l in lines[-6:]:
        try:
            d = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        at = time.strftime("%m-%d %H:%M", time.localtime(d.get("at") or 0))
        dur = _fmt_dur(d.get("duration") or 0)
        ev = d.get("event")
        if ev == "restart":
            rows.append("· %s 掉线 %s，已自动重启启动恢复" % (at, dur))
        else:
            rows.append("· %s 掉线 %s，已自动恢复" % (at, dur))
    if not rows:
        return ""
    head = "⚠️ NapCat 掉线告警（已自动处理，无需操作）"
    return head + "\n" + "\n".join(rows)


async def _flush_once() -> None:
    lines = _load_pending()
    if not lines:
        return
    text = _build_text(lines)
    if not text:
        return
    bots = get_bots()
    if not bots:
        logger.warning("[guard] 当前没有已连接的 bot，告警留到下次")
        _requeue(lines)
        return
    bot = next(iter(bots.values()))
    try:
        await bot.call_api("send_private_msg", user_id=ADMIN, message=text)
        logger.info("[guard] 已推送 {} 条掉线告警".format(len(lines)))
        try:
            os.remove(PENDING + ".flushing")
        except OSError:
            pass
        # 补回空文件，保持守护脚本的写入通道
        try:
            open(PENDING, "a", encoding="utf-8").close()
            os.chmod(PENDING, 0o664)
        except OSError:
            pass
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning("[guard] 告警推送失败，留到下次重试")
        _requeue(lines)


async def _loop() -> None:
    await asyncio.sleep(25)
    while True:
        try:
            await _flush_once()
        except Exception:  # noqa: BLE001
            logger.opt(exception=True).warning("[guard] 告警循环异常")
        await asyncio.sleep(300)


@driver.on_startup
async def _start() -> None:
    asyncio.create_task(_loop())


status = on_command("守护状态", priority=4, block=True)


@status.handle()
async def handle_status(event, arg: Message = CommandArg()):
    if str(event.get_user_id()) != str(ADMIN):
        await status.finish("只有 bot 管理员能看守护状态~")
    ev = []
    if os.path.exists(EVENTS):
        try:
            with open(EVENTS, "r", encoding="utf-8", errors="replace") as f:
                ev = [l.rstrip() for l in f.readlines()][-10:]
        except Exception:  # noqa: BLE001
            ev = []
    pend = 0
    if os.path.exists(PENDING):
        try:
            with open(PENDING, "r", encoding="utf-8", errors="replace") as f:
                pend = sum(1 for l in f if l.strip())
        except Exception:  # noqa: BLE001
            pend = -1
    lines = ["【NapCat 守护】", "待推送告警：%d 条" % pend]
    if ev:
        lines.append("最近事件：")
        lines.extend(ev)
    else:
        lines.append("还没有事件记录")
    await status.finish("\n".join(lines))

# -*- coding: utf-8 -*-
"""群龙王榜：按群统计每周发言条数，周日 22:00 结算并推图。

指令：群龙王   -> 输出当前周的排行榜图
核心逻辑在 dragon_card.py（不依赖 nonebot，可单独测试）
"""
import re

from nonebot import get_bots, on_message, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent

from . import _media
from . import _dragon_card as DC
from . import module_switch as _switch

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

DC.ensure()

counter = on_message(priority=100, block=False)
board = on_message(priority=6, block=False)

RE_CMD = re.compile(r'^群龙王$')


@counter.handle()
async def _count(event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return
    text = event.get_plaintext().strip()
    if RE_CMD.match(text):          # 「群龙王」本身不计入发言数
        return
    if not text and len(event.get_message()) <= 1:
        return
    DC.incr(event.group_id, event.get_user_id())


@board.handle()
async def _board(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return
    if not RE_CMD.match(event.get_plaintext().strip()):
        return
    if not _switch.is_on(event.group_id, 'dragon'):
        return
    try:
        png, n = await DC.render_board(bot, event.group_id)
    except Exception as e:  # noqa: BLE001
        await board.finish('排行榜生成失败：%s' % e)
        return
    if not png:
        await board.finish('本周还没有发言记录，等大家水起来再来吧~')
        return
    await board.send(_media.image(png))


@scheduler.scheduled_job('cron', day_of_week='sun', hour=22, minute=0,
                         id='dragon_weekly_settle', misfire_grace_time=600)
async def _settle():
    week = DC.week_key()
    bots = list(get_bots().values())
    if not bots:
        return
    bot = bots[0]
    for gid in DC.groups_this_week(week):
        try:
            png, n = await DC.render_board(bot, gid, week)
            if not png:
                continue
            await bot.call_api('send_group_msg', group_id=int(gid),
                               message=Message(_media.image(png)))
            DC.mark_settled(gid, week)
        except Exception:  # noqa: BLE001
            continue

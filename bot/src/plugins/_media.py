# -*- coding: utf-8 -*-
"""本地图片/语音发送工具。

NapCat 跑在独立 Docker 容器里，默认看不到宿主机文件路径。部署时已把素材目录
以只读方式挂进容器（同一绝对路径），所以这里直接发本地路径，由适配器转成
file:// URI 交给 NapCat 读取，省掉 base64 编码开销（装备卡最大 4MB，base64 多三成）。

对应挂载：
  -v /app/bh2-bot/materials:/app/bh2-bot/materials:ro
  -v /app/bh2-bot/bh2-bot/chara_pages:/app/bh2-bot/bh2-bot/chara_pages:ro

若某个部署没做挂载，可临时改成读 bytes 发 base64：
  return MessageSegment.image(Path(file).read_bytes(), **kwargs)
"""
from pathlib import Path
from typing import Union

from nonebot.adapters.onebot.v11 import MessageSegment


def image(file: Union[str, Path], **kwargs) -> MessageSegment:
    """发送本地图片（路径需对 NapCat 容器可见）。"""
    return MessageSegment.image(Path(file).resolve(), **kwargs)


def record(file: Union[str, Path], **kwargs) -> MessageSegment:
    """发送本地语音（路径需对 NapCat 容器可见）。"""
    return MessageSegment.record(Path(file).resolve(), **kwargs)

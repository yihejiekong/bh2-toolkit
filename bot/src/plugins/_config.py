# -*- coding: utf-8 -*-
"""共享配置：统一素材根目录与数据库路径，兼容本地 Windows 与云端 Linux。

素材根目录的优先级：
1. 环境变量 MATERIAL_ROOT（上云时用，如 /app/bh2-bot/materials）
2. 项目目录下的 materials/ 子目录（把素材复制/软链到项目里）

这样上云时只需把素材放到项目 materials/ 下（或设 MATERIAL_ROOT），无需改代码。
"""
import os
from pathlib import Path

# 项目根目录（bh2-bot/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 数据库文件（项目根目录下的 bh2.db）
DB = PROJECT_ROOT / "bh2.db"


def _resolve_material_root() -> Path:
    # 1. 环境变量优先
    env = os.environ.get("MATERIAL_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p
    # 2. 项目内 materials/ 子目录
    local = PROJECT_ROOT / "materials"
    if local.exists():
        return local
    # 都不存在时返回项目内 materials（后续报错时提示放这里）
    return local


MATERIAL_ROOT = _resolve_material_root()
ICON_DIR = MATERIAL_ROOT / "图标"
CARD_ROOT = MATERIAL_ROOT / "装备卡"
ILLUST_DIR = MATERIAL_ROOT / "觉醒立绘"
EMOTE_DIR = MATERIAL_ROOT / "精选表情图"

# 角色卡目录：统一归并到素材根下的「角色卡」子目录（云端 materials/角色卡/）。
# 兼容旧结构：若素材根下没有「角色卡」，回退到项目根下的 chara_pages（本地旧布局）。
CHARA_DIR = MATERIAL_ROOT / "角色卡"
if not CHARA_DIR.exists():
    CHARA_DIR = PROJECT_ROOT / "chara_pages"


# ---- 管理员 ----
# 从 .env 的 BOT_ADMINS 读（逗号分隔的 QQ 号）。留空表示没有 bot 管理员。
_ADMINS_ENV = os.environ.get("BOT_ADMINS", "")
ADMIN_LIST = [x.strip() for x in _ADMINS_ENV.replace(" ", ",").split(",") if x.strip()]
ADMIN_SET = set(ADMIN_LIST)
ADMIN_QQ = int(ADMIN_LIST[0]) if ADMIN_LIST else 0

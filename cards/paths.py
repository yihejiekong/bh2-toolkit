# -*- coding: utf-8 -*-
"""统一路径配置。

所有脚本都从这里取目录，不要在本机绝对路径上写死。优先级：

    环境变量  >  仓库内约定目录

仓库内约定（相对本文件上一级）：

    tables/     图鉴表（xlsx）
    materials/  成品素材（装备卡 / 立绘 / 图标 / …）
    data/       解包中间产物（tsv_all、packs_dec、textures …）
    build/      构建中间物（HTML、截图临时目录、批量清单）

常用环境变量：

    BH2_TABLES     图鉴表目录
    BH2_XLSX       图鉴表 xlsx 完整路径
    MATERIAL_ROOT  素材根目录
    BH2_DATA       解包数据目录
    BH2_TSV        tsv_all 目录
    BH2_BUILD      构建中间物目录
    BH2_BROWSER    浏览器可执行文件（截图用）
"""
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*parts):
    """拼出仓库内的路径。"""
    return os.path.join(BASE, *parts)


TABLES = os.environ.get("BH2_TABLES") or p("tables")
MATERIALS = os.environ.get("MATERIAL_ROOT") or p("materials")
DATA = os.environ.get("BH2_DATA") or p("data")
BUILD = os.environ.get("BH2_BUILD") or p("build")
TSV_DIR = os.environ.get("BH2_TSV") or os.path.join(DATA, "tsv_all")
XLSX = os.environ.get("BH2_XLSX") or os.path.join(TABLES, "bh2_codex.xlsx")


def _browser():
    env = os.environ.get("BH2_BROWSER")
    if env:
        return env
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return shutil.which("msedge") or shutil.which("google-chrome") or "msedge"


def _font(*names):
    """按顺序找字体，找不到就返回空串（PIL 会退回默认字体）。"""
    roots = [
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype/wqy",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/truetype/dejavu",
    ]
    for name in names:
        for root in roots:
            f = os.path.join(root, name)
            if os.path.exists(f):
                return f
    return ""


BROWSER = _browser()
FONT_BD = _font("msyhbd.ttc", "msyh.ttc", "wqy-zenhei.ttc", "NotoSansCJK-Bold.ttc",
                "NotoSansCJKsc-Bold.otf", "DejaVuSans-Bold.ttf")
FONT_RG = _font("msyh.ttc", "wqy-zenhei.ttc", "NotoSansCJK-Regular.ttc",
                "NotoSansCJKsc-Regular.otf", "DejaVuSans.ttf")

if __name__ == "__main__":
    for k in ("BASE", "TABLES", "MATERIALS", "DATA", "TSV_DIR", "BUILD", "XLSX",
              "BROWSER", "FONT_BD"):
        print("%-10s %s" % (k, globals()[k]))

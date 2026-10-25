# -*- coding: utf-8 -*-
"""把崩坏学园2图鉴 Excel 导入 SQLite（新名单版）。

数据源：图鉴表 xlsx（默认 <repo>/tables/bh2_codex.xlsx，可用 BH2_XLSX 覆盖）
卡片：  素材根下的 装备卡/{类别目录}/PNG/{前缀}_{名称}.png

产出 bh2.db，equip 表（每个稀有度一行）+ alias（别名）。

注意：不再创建 equip_fts 全文索引（历史遗留的坏索引——FTS 声明列 skill
但 equip 表只有 skill_raw，查询报 no such column，且实际搜索全走 LIKE，
该索引纯占空间已废弃）。
"""
import sqlite3
import glob
import os
from pathlib import Path

import openpyxl

# 所有路径都可以用环境变量覆盖，默认值按仓库目录结构推导。
_HERE = Path(__file__).resolve()
BOT_DIR = _HERE.parents[1]            # bot/
REPO = _HERE.parents[2]               # 仓库根

XLSX = Path(os.environ.get("BH2_XLSX") or (REPO / "tables" / "bh2_codex.xlsx"))
MATERIAL_ROOT = Path(os.environ.get("MATERIAL_ROOT") or (BOT_DIR / "materials"))
CARD_ROOT = MATERIAL_ROOT / "装备卡"
ICON_DIR = MATERIAL_ROOT / "图标"
ILLUST_XLSX = Path(os.environ.get("BH2_ILLUST_XLSX") or (XLSX.parent / "觉醒立绘索引.xlsx"))
ILLUST_DIR = MATERIAL_ROOT / "觉醒立绘"
DB = Path(os.environ.get("BH2_DB") or (BOT_DIR / "bh2.db"))

# sheet 名 → 卡片目录名
SHEET_CARD_DIR = {
    "武器": "装备卡",
    "服装": "服装卡",
    "使魔-被动技能": "徽章卡",     # 徽章 = 解包表的「被动技能」
    "宠物": "使魔卡",              # 使魔 = 解包表的「宠物」
}

# sheet 名 → 装备类别（显示用）
SHEET_CATEGORY = {
    "武器": "武器",
    "服装": "服装",
    "使魔-被动技能": "徽章",
    "宠物": "使魔",
}


def clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def build_card_index():
    """扫描所有卡片 PNG，建立 {名称: 相对路径} 与 {编号: 相对路径} 两张索引。

    同名装备每个稀有度一行，但卡图可能各自独立（如 50016/50017 破浪守护者）：
    只按名称查会都落到第一张命中的图上，所以导入时优先用编号索引，
    名称索引仅作没有本编号卡图时的回退。排序后再扫，保证回退结果稳定。
    """
    index = {}
    by_id = {}
    for sheet, dname in SHEET_CARD_DIR.items():
        png_dir = CARD_ROOT / dname / "PNG"
        if not png_dir.exists():
            continue
        for f in sorted(png_dir.glob("*.png")):
            # 文件名：{前缀}_{名称}.png，名称可能在中间含下划线，直接取第一个下划线后
            base = f.stem
            # 名称 = 去掉第一个下划线前的数字前缀
            name = base.split("_", 1)[1] if "_" in base else base
            gid = base.split("_", 1)[0] if "_" in base else None
            rel = f.relative_to(CARD_ROOT).as_posix()
            if gid and gid not in by_id:
                by_id[gid] = rel
            if name not in index:
                index[name] = rel
    return index, by_id


def main():
    if not XLSX.exists():
        raise SystemExit("找不到图鉴表：%s\n用 --xlsx 或环境变量 BH2_XLSX 指定" % XLSX)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS equip")
    cur.execute("""
        CREATE TABLE equip (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            name TEXT NOT NULL,
            category TEXT,
            wtype TEXT,
            rarity INTEGER,
            max_level INTEGER,
            series TEXT,
            skill_raw TEXT,
            desc_raw TEXT,
            status TEXT,
            icon_id TEXT,
            icon_file TEXT,
            alias TEXT,
            sheet TEXT,
            card_file TEXT
        )
    """)
    card_index, card_index_by_id = build_card_index()
    print(f"卡片索引：{len(card_index)} 个名称 / {len(card_index_by_id)} 个编号")

    wb = openpyxl.load_workbook(XLSX, read_only=True)
    total = 0
    for sheet, dname in SHEET_CARD_DIR.items():
        if sheet not in wb.sheetnames:
            print(f"[{sheet}] 不存在，跳过")
            continue
        ws = wb[sheet]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        col_idx = {name: i for i, name in enumerate(header)}

        def get(row, key):
            return clean(row[col_idx[key]]) if key in col_idx else None

        n = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            name = get(row, "名称")
            status = get(row, "装备状态")
            if not name:
                continue
            if status not in (None, "正式"):
                continue

            rarity = get(row, "稀有度")
            try:
                rarity = int(rarity) if rarity is not None else None
            except (ValueError, TypeError):
                rarity = None
            max_level = get(row, "最大等级")
            try:
                max_level = int(max_level) if max_level is not None else None
            except (ValueError, TypeError):
                max_level = None

            alias = get(row, "装备别名（社区）")
            icon_file = get(row, "图标文件")
            icon_id = get(row, "图标ID")

            # 卡片：优先按编号（同名不同稀有度各自有图），回退按名称
            game_id_val = str(get(row, "游戏内ID")) if get(row, "游戏内ID") is not None else None
            card_file = card_index_by_id.get(game_id_val) or card_index.get(name)

            cur.execute("""
                INSERT INTO equip (game_id, name, category, wtype, rarity, max_level,
                    series, skill_raw, desc_raw, status, icon_id, icon_file, alias, sheet, card_file)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                game_id_val,
                name, SHEET_CATEGORY[sheet], get(row, "武器类型"), rarity, max_level,
                get(row, "系列"), get(row, "技能（解包原文）"), get(row, "描述（解包原文）"),
                status, str(icon_id) if icon_id is not None else None,
                icon_file, alias, sheet, card_file,
            ))
            n += 1
        total += n
        print(f"[{sheet}] {n} 条")

    conn.commit()

    # 统计
    cur.execute("SELECT COUNT(*) FROM equip")
    print("总条数:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM equip WHERE card_file IS NOT NULL")
    print("有卡片的条数:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(DISTINCT name) FROM equip WHERE card_file IS NOT NULL")
    print("有卡片的独立名称数:", cur.fetchone()[0])

    import_illust(cur)
    conn.commit()
    conn.close()
    print("完成 ->", DB)


def import_illust(cur):
    """导入觉醒立绘索引（觉醒立绘索引.xlsx）。

    illust 表：每张立绘一条（角色名 + 文件名）。
    illust_equip 表：装备名 -> 立绘 映射（用于按装备名查立绘）。
    """
    cur.execute("DROP TABLE IF EXISTS illust")
    cur.execute("""
        CREATE TABLE illust (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            figure_id TEXT,
            role_name TEXT NOT NULL,
            series TEXT,
            file TEXT,
            cited INTEGER
        )
    """)
    cur.execute("DROP TABLE IF EXISTS illust_equip")
    cur.execute("""
        CREATE TABLE illust_equip (
            equip_name TEXT NOT NULL,
            role_name TEXT,
            file TEXT
        )
    """)

    wb = openpyxl.load_workbook(ILLUST_XLSX, read_only=True)

    # 1. 全部立绘 sheet（主表，966 张）
    ws = wb["全部立绘"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    # 序号, 立绘ID, 角色名, 看板Type, 系列, 被装备引用行数, 文件名, 分辨率
    n = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[2]:  # 角色名为空跳过
            continue
        fig_id = clean(row[1])
        role = clean(row[2])
        series = clean(row[4])
        cited = row[5] or 0
        file = clean(row[6])
        cur.execute(
            "INSERT INTO illust (figure_id, role_name, series, file, cited) VALUES (?,?,?,?,?)",
            (str(fig_id) if fig_id is not None else None, role, series, file, int(cited)),
        )
        n += 1
    print(f"[全部立绘] {n} 张")

    # 2. 立绘索引 sheet（装备名 -> 立绘 映射）
    ws2 = wb["立绘索引"]
    header2 = [c.value for c in next(ws2.iter_rows(min_row=1, max_row=1))]
    # 类别, 内部ID, 游戏内ID, 装备名称, 觉醒角色, PosterID, FigureID, 立绘文件, 尺寸
    n2 = 0
    seen = set()
    for row in ws2.iter_rows(min_row=2, values_only=True):
        equip_name = clean(row[3])
        role = clean(row[4])
        file = clean(row[7])
        if not equip_name or not file:
            continue
        key = (equip_name, file)
        if key in seen:
            continue
        seen.add(key)
        cur.execute(
            "INSERT INTO illust_equip (equip_name, role_name, file) VALUES (?,?,?)",
            (equip_name, role, file),
        )
        n2 += 1
    print(f"[立绘索引] {n2} 条装备名映射（去重后）")

    wb.close()


if __name__ == "__main__":
    main()

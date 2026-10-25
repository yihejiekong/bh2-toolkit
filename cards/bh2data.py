"""崩坏学园2 解包数据读取层（textmap + 配置表）。"""

import json
import os
import re
from collections import defaultdict
import paths as P

TSV = os.path.join(P.DATA, 'tsv')
TSV_ALL = P.TSV_DIR
HSOD = os.path.join(P.DATA, 'raw', 'hsod2', 'HSoD2Illustrate-main')


def decode_line(b):
    """数据行是 UTF-8，个别表头注释行是 GBK，逐行兜底。"""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return b.decode("gbk")
        except UnicodeDecodeError:
            return b.decode("utf-8", "replace")


def read_text(path):
    with open(path, "rb") as f:
        return "\n".join(decode_line(x) for x in f.read().split(b"\n"))


def read_tsv(path, skip_caption=True):
    """游戏配置表：第1行英文列名，随后若干行是中文名/Client/类型说明（各表行数不同，需自动探测）。"""
    txt = read_text(path)
    lines = [l for l in txt.splitlines()]
    if not lines:
        return [], []
    hdr = lines[0].split("\t")
    start = 1
    if skip_caption:
        while start < len(lines):
            first = lines[start].split("\t")[0].strip()
            if re.fullmatch(r"-?\d+", first):
                break
            start += 1
        if start >= len(lines):  # 首列非数字的表（无可用数据行）退回第2行
            start = 1
    body = lines[start:]
    rows = []
    for line in body:
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) < len(hdr):
            cells += [""] * (len(hdr) - len(cells))
        rows.append(dict(zip(hdr, cells)))
    return hdr, rows


def load_textmap(tsv_dir=TSV):
    tm = {}
    for i in range(60):
        pth = os.path.join(tsv_dir, f"textmap_{i}.txt")
        if not os.path.exists(pth):
            continue
        txt = read_text(pth)
        for line in txt.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].strip().isdigit():
                tm[parts[0].strip()] = parts[1]
    return tm


def load_json(which="original"):
    with open(os.path.join(HSOD, f"{which}.json"), encoding="utf-8") as f:
        return json.load(f)


def num(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def fmt(v):
    """数字美化：整数值不带小数，其余保留至多 6 位有意义小数。"""
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.10g}"


if __name__ == "__main__":
    tm = load_textmap()
    print("textmap entries:", len(tm))
    for k in ["11001", "12190", "12101"]:
        print(" ", k, "->", tm.get(k))

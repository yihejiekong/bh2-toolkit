# -*- coding: utf-8 -*-
"""批量导出图鉴卡（武器 / 服装共用一套引擎）：HTML 与 PNG 分两个文件夹。

用法：
    python batch.py                  # 武器全量（去重后 1177 张）
    python batch.py --limit 20       # 只做前 20 张（试跑）
    python batch.py --html-only      # 只出 HTML
    python batch.py --png-only       # 只出 PNG（HTML 已存在时）
    python batch.py --ids 897,4803   # 指定游戏内ID
    python batch_fz.py [同样的参数]    # 服装（600 张）

卡片长/短模板由数据自动决定：有觉醒立绘 -> 追加觉醒块 + 觉醒素材行 + 表情差分（长）；没有 -> 到此结束（短）。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardgen as C
import paths as P

ROOT = os.path.join(P.MATERIALS, '装备卡', '装备卡')
BUILD = P.BUILD

EDGE = P.BROWSER
SCALE = 1.5
W = 1080
BG = (0xec, 0xee, 0xf2)
BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')
PROF_ROOT = os.path.join(BUILD, 'edge_profile')


def dirs(root):
    """PNG 落 materials；HTML 与 assets 属于构建中间物，统一放 _tmp。"""
    return (root, os.path.join(BUILD, 'HTML'), os.path.join(root, 'PNG'),
            os.path.join(BUILD, 'assets'))


def fname(dn, name):
    return '%s_%s' % (dn, BAD.sub('_', str(name)).strip())


def ensure_assets(card, asset_dir):
    """把卡片用到的图标/立绘/材料图标/表情差分复制到 <root>/assets，返回是否齐全。"""
    ok = True
    files = [card['icon'], card['figure']]
    files += [m['file'] for m in card['mats']]
    files += [t['file'] for t in (card.get('traits') or [])]
    if card['figure']:
        files += list(card.get('faces') or [])
    for f in files:
        if not f:
            continue
        dest = os.path.join(asset_dir, f)
        if os.path.exists(dest):
            continue
        src = os.path.join(C.ASSETS, f)
        if os.path.exists(src):
            shutil.copyfile(src, dest)
        else:
            ok = False
    return ok


def figure_height(fig):
    if not fig:
        return 0
    try:
        with Image.open(os.path.join(C.ASSETS, fig)) as im:
            w, h = im.size
        return int((170.0 if str(fig).startswith('small_') else 952.0) * h / w) if w else 952
    except Exception:
        return 952


FACE_W = 226
FACE_GAP = 16
FACE_PER_ROW = 4


def faces_height(faces):
    if not faces:
        return 0
    rows = (len(faces) + FACE_PER_ROW - 1) // FACE_PER_ROW
    return 22 + rows * FACE_W + (rows - 1) * FACE_GAP


def est_height(card):
    h = 560
    for item in card['skills']:
        body = item[1]
        meta = item[2] if len(item) > 2 else None
        h += 60 + 60 * max(1, int(len(body) / 27) + 1)
        if meta:
            h += 38
    if card.get('traits'):
        h += 66
    if card['mats']:
        h += 150
    b = card['bio']
    if b:
        h += 260 + 40 * max(1, int(len(b['desc']) / 30) + 1)
        if card['figure']:
            h += figure_height(card['figure']) + faces_height(card.get('faces'))
            if str(card['figure']).startswith('small_'):
                h += 90
    return h


def crop(png):
    im = Image.open(png).convert('RGB')
    px = im.load()
    w, h = im.size
    last = h - 1
    while last > 0:
        row = [px[x, last] for x in range(0, w, 7)]
        if any(abs(c[0] - BG[0]) + abs(c[1] - BG[1]) + abs(c[2] - BG[2]) > 12 for c in row):
            break
        last -= 1
    if last < h - 1:
        im.crop((0, 0, w, min(h, last + 12))).save(png)


def shoot_one(job):
    idx, png_path, html_path, height = job
    prof = os.path.join(PROF_ROOT, 'p%d' % (idx % 8))
    os.makedirs(prof, exist_ok=True)
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
           '--disable-extensions', '--disable-background-networking', '--disable-sync',
           '--user-data-dir=' + prof,
           '--force-device-scale-factor=%s' % SCALE,
           '--window-size=%d,%d' % (W, height),
           '--screenshot=' + png_path,
           'file:///' + html_path.replace('\\', '/')]
    for attempt in range(3):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=120, check=False)
            if os.path.exists(png_path) and os.path.getsize(png_path) > 1000:
                crop(png_path)
                return True
        except Exception:
            pass
        time.sleep(1 + attempt)
    return False


def select_ids(rows, idx, all_variants=False):
    """默认按名称去重，只保留「最高星级 + 最高等级」的那一版（图鉴语义）。
    图纸里同名装备是 1★~7★ 的升星分身，逐星出卡会得到大量重复卡。"""
    if all_variants:
        ids = [k for k, r in rows.items() if str(r[idx['装备状态']]) == '正式']
        return sorted(ids, key=lambda x: int(x))
    best = {}
    for k, r in rows.items():
        nm = str(r[idx['名称']]).strip()
        if not nm or nm in ('N/A', '无'):
            continue
        if str(r[idx['装备状态']]) != '正式':
            continue
        key = (float(r[idx['稀有度']] or 0), float(r[idx['最大等级']] or 0), -int(k))
        if nm not in best or key > best[nm][0]:
            best[nm] = (key, k)
    return sorted((v[1] for v in best.values()), key=lambda x: int(x))


def run(ids, build, root, workers=6, html_only=False, png_only=False):
    global PROF_ROOT
    PROF_ROOT = os.path.join(BUILD, 'edge_profile')
    root, html_dir, png_dir, asset_dir = dirs(root)
    for d in (html_dir, png_dir, asset_dir):
        os.makedirs(d, exist_ok=True)

    print('cards: %d' % len(ids), flush=True)

    jobs = []
    missing_asset = 0
    t0 = time.time()
    ok_ids = []
    for n, dn in enumerate(ids, 1):
        try:
            card = build(dn)
        except Exception as e:
            print('  ! build fail %s: %s' % (dn, e), flush=True)
            continue
        ok_ids.append(dn)
        if not ensure_assets(card, asset_dir):
            missing_asset += 1
        base = fname(dn, card['name'])
        html_path = os.path.join(html_dir, base + '.html')
        png_path = os.path.join(png_dir, base + '.png')
        if not png_only:
            html = C.render(card)
            html = html.replace('src="assets/', 'src="../assets/')
            with io.open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
        if not html_only:
            jobs.append((len(jobs), png_path, html_path, min(est_height(card) + 340, 7000)))
        if n % 200 == 0:
            print('  html %d/%d  %.0fs' % (n, len(ids), time.time() - t0), flush=True)

    print('html done: %d, missing assets: %d, %.0fs' % (len(ok_ids), missing_asset, time.time() - t0), flush=True)

    if not jobs:
        return
    done = 0
    fails = []
    t1 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for job, ok in zip(jobs, ex.map(shoot_one, jobs)):
            done += 1
            if not ok:
                fails.append(job[1])
            if done % 100 == 0:
                print('  png %d/%d  %.0fs' % (done, len(jobs), time.time() - t1), flush=True)
    print('png done: %d ok, %d fail, %.0fs' % (len(jobs) - len(fails), len(fails), time.time() - t1), flush=True)
    for p in fails[:20]:
        print('  fail:', p, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--ids', default='')
    ap.add_argument('--all', action='store_true', help='不做同名升星去重，全部 2149 行都出卡')
    ap.add_argument('--html-only', action='store_true')
    ap.add_argument('--png-only', action='store_true')
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()

    if a.ids:
        ids = [x.strip() for x in a.ids.split(',') if x.strip()]
    else:
        ids = select_ids(C.ROWS, C.IDX, a.all)
    if a.limit:
        ids = ids[:a.limit]
    run(ids, C.build, ROOT, a.workers, a.html_only, a.png_only)


if __name__ == '__main__':
    main()

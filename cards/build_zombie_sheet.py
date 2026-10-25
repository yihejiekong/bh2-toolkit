# -*- coding: utf-8 -*-
"""僵尸娘：①重建 index.json ②生成 58 只汇总图。"""

import io
import json
import os
import re
import subprocess

from PIL import Image

import build_zombie2 as B
import paths as P

MAT = os.path.join(P.MATERIALS, '僵尸娘')
CARDS, GIFS, ICONS = (os.path.join(MAT, x) for x in ('cards', 'gif', 'icons'))
OUT = B.OUT
EDGE = B.EDGE

order = sorted(B.DATA.values(), key=lambda z: -int(z['id']))

# ---------- index.json ----------
index = []
for z in order:
    zid = int(z['id'])
    cname = 'zombie_%03d.png' % zid
    gname = 'zombie_%03d.gif' % zid
    if not os.path.exists(os.path.join(CARDS, cname)):
        print('缺卡', z['name'])
        continue
    index.append({
        'id': zid,
        'name': z['name'],
        'attack_mode': z.get('attack_mode') or '',
        'debut': z.get('debut') or '',
        'info': B.plain(z.get('info')),
        'card': 'cards/' + cname,
        'gif': ('gif/' + gname) if os.path.exists(os.path.join(GIFS, gname)) else '',
        'skills': [{'no': i, 'name': s['name'], 'desc': s['skill_desc'].strip(),
                    'gif': bool((s.get('display_img') or '').strip())}
                   for i, s in enumerate(z['skills'], 1)],
    })
json.dump(index, io.open(os.path.join(MAT, 'index.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
json.dump([{k: v for k, v in z.items() if k != '_list'} for z in order],
          io.open(os.path.join(MAT, 'zombie.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('index', len(index), '卡', len(os.listdir(CARDS)), '动图', len(os.listdir(GIFS)))

# ---------- 汇总图 ----------
COLS = 8
TW, TH = 150, 178
GAP = 14
PADX, PADY = 26, 26
W = PADX * 2 + COLS * TW + (COLS - 1) * GAP
rows = (len(index) + COLS - 1) // COLS

cells = []
for i, e in enumerate(index):
    icon = os.path.join(ICONS, '%03d.png' % e['id'])
    cells.append((i, e['name'], icon))

html = ["""<!doctype html><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#eef1f6;font-family:"Microsoft YaHei",sans-serif;padding:22px}
.card{width:%dpx;background:#fdfbf6;border-radius:24px;padding:26px 26px 30px;
      box-shadow:0 2px 12px rgba(120,110,95,.10);
      background-image:radial-gradient(#efe6d8 1.1px, transparent 1.1px);background-size:26px 26px}
.h1{text-align:center;font-size:44px;font-weight:800;color:#e9a63a;letter-spacing:3px;
    -webkit-text-stroke:5px #fff;paint-order:stroke fill}
.h2{text-align:center;font-size:19px;color:#a89b86;margin-top:10px;letter-spacing:2px}
.grid{display:flex;flex-wrap:wrap;gap:%dpx;margin-top:22px}
.c{width:%dpx;height:%dpx;background:#fff;border-radius:16px;border:1px solid #eee3d0;
   position:relative;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;
   padding-top:8px}
.i{width:96px;height:96px;display:flex;align-items:center;justify-content:center}
.i img{max-width:96px;max-height:96px}
.n{margin-top:2px;font-size:18px;font-weight:700;color:#3d4450;text-align:center;
   line-height:1.2;padding:0 4px}
.x{position:absolute;left:7px;top:6px;font-size:14px;font-weight:700;color:#b8711a;
   background:#f8e9cb;border-radius:8px;padding:1px 6px}
</style><div class="card">
<div class="h1">崩坏学园2 · 僵尸娘</div>
<div class="h2">共 %d 只 · 官网攻略资料 · 按编号排序</div>
<div class="grid">""" % (W, GAP, TW, TH, len(index))]

for i, (_, name, icon) in enumerate(cells, 1):
    html.append('<div class="c"><span class="x">%02d</span><div class="i">'
                '<img src="file:///%s"></div><div class="n">%s</div></div>'
                % (i, icon.replace('\\', '/'), name.replace('&', '&amp;')))
html.append('</div></div>')

hp = os.path.join(OUT, 'zombie_sheet.html')
io.open(hp, 'w', encoding='utf-8').write(''.join(html))
png = os.path.join(MAT, '僵尸娘汇总.png')
subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                '--force-device-scale-factor=2', '--window-size=%d,%d' % (W + 60, 2200),
                '--screenshot=' + png, 'file:///' + hp.replace('\\', '/')],
               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
im = Image.open(png).convert('RGB')
w, h = im.size
bg = im.getpixel((3, h - 3))
y = h - 1
while y > 0:
    row = [im.getpixel((xx, y)) for xx in range(0, w, 7)]
    if any(abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 12 for p in row):
        break
    y -= 1
im = im.crop((0, 0, w, min(h, y + 26)))
im.save(png, optimize=True)
q = im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
qp = os.path.join(MAT, '僵尸娘汇总.png')
q.save(qp, optimize=True)
print('汇总图', im.size, '%.0fKB → 256色 %.0fKB' % (os.path.getsize(png) / 1024,
                                              os.path.getsize(qp) / 1024))

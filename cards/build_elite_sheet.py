# -*- coding: utf-8 -*-
"""生成「精英技能图标汇总图」：HTML + headless Edge 截图 + 裁底。"""

import io
import json
import os
import subprocess

from PIL import Image
import paths as P

BASE = P.BUILD
ICON = os.path.join(BASE, 'elite_icons')
HTML = os.path.join(BASE, 'elite_sheet.html')
PNG = os.path.join(BASE, '精英技能汇总.png')
EDGE = P.BROWSER

d = json.loads(io.open(os.path.join(BASE, 'elite_skill.json'), encoding='utf-8').read())
d.sort(key=lambda x: int(x['id']))

COLS = 6
CELL_W, CELL_H, GAP = 148, 176, 12
CARDPAD = 40
W = COLS * CELL_W + (COLS - 1) * GAP + CARDPAD * 2

cells = []
for i, x in enumerate(d, 1):
    name = x['name']
    fs = 19 if len(name) <= 5 else (17 if len(name) <= 7 else 15)
    rel = 'elite_icons/%s.png' % x['id']
    cells.append(
        '<div class="cell">'
        '<div class="idx">%02d</div>'
        '<div class="ico"><img src="%s"></div>'
        '<div class="nm" style="font-size:%dpx">%s</div>'
        '</div>' % (i, rel, fs, name))

HTML_TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#eef1f6;font-family:"Microsoft YaHei","WenQuanYi Zen Hei",sans-serif;padding:24px}
.card{width:__W__px;background:#fdfbf6;border-radius:24px;padding:34px __P__px 30px;
      box-shadow:0 2px 12px rgba(120,110,95,.10);
      background-image:radial-gradient(#efe6d8 1.1px, transparent 1.1px);background-size:26px 26px}
h1{text-align:center;font-size:38px;color:#e9a63a;letter-spacing:3px;
   text-shadow:0 2px 0 #fff,0 0 1px #e9a63a}
.sub{text-align:center;margin-top:8px;font-size:16px;color:#9aa3b2;letter-spacing:1px}
.grid{display:grid;grid-template-columns:repeat(__C__,__CW__px);gap:__G__px;margin-top:26px;justify-content:center}
.cell{height:__CH__px;background:#fff;border:1px solid #ece5d8;border-radius:14px;
      display:flex;flex-direction:column;align-items:center;justify-content:flex-start;
      padding:8px 6px 6px;position:relative}
.idx{position:absolute;left:7px;top:6px;font-size:15px;font-weight:700;color:#b8711a;background:#f8e9cb;border-radius:8px;padding:1px 7px;letter-spacing:.5px;line-height:1.35}
.ico{width:96px;height:96px;display:flex;align-items:center;justify-content:center;margin-top:10px}
.ico img{max-width:96px;max-height:96px;image-rendering:auto}
.nm{margin-top:6px;line-height:1.25;color:#3d4450;font-weight:600;text-align:center;
    max-width:132px;word-break:break-all}
</style></head><body><div class="card">
<h1>崩坏学园2 · 精英技能</h1>
<div class="sub">共 __N__ 项 · 官网攻略资料 · 按技能编号排序</div>
<div class="grid">__CELLS__</div>
</div></body></html>"""

html = (HTML_TPL.replace('__W__', str(W)).replace('__P__', str(CARDPAD))
        .replace('__C__', str(COLS)).replace('__CW__', str(CELL_W))
        .replace('__G__', str(GAP)).replace('__CH__', str(CELL_H))
        .replace('__N__', str(len(d))).replace('__CELLS__', ''.join(cells)))
io.open(HTML, 'w', encoding='utf-8').write(html)
print('html', W, 'x ?', len(d), 'items')

rows = (len(d) + COLS - 1) // COLS
H = 34 + 60 + 26 + rows * (CELL_H + GAP) + 30 + 40
cmd = [EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
       '--force-device-scale-factor=2', '--window-size=%d,%d' % (W + 48, H),
       '--screenshot=' + PNG, 'file:///' + HTML.replace('\\', '/')]
subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)

im = Image.open(PNG).convert('RGB')
w, h = im.size
bg = im.getpixel((3, h - 3))
y = h - 1
while y > 0:
    row = [im.getpixel((x, y)) for x in range(0, w, 7)]
    if any(abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 12 for p in row):
        break
    y -= 1
im.crop((0, 0, w, min(h, y + 26))).save(PNG)
print('png', Image.open(PNG).size, os.path.getsize(PNG))

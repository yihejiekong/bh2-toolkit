# -*- coding: utf-8 -*-
"""生成单个精英技能的「技能效果 + 生存指南」卡，并下载其 GIF 演示。

用法：python build_skill_card.py <编号> [<编号> ...]
"""

import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request

from PIL import Image
import paths as P

BASE = P.BUILD
MAT = os.path.join(P.MATERIALS, '精英技能')
ICON = os.path.join(MAT)
GIFDIR = os.path.join(MAT, 'gif')
OUT = os.path.join(BASE, 'skill_cards')
EDGE = P.BROWSER
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120',
      'Referer': 'https://www.benghuai.com/data/'}

os.makedirs(GIFDIR, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

DATA = json.loads(io.open(os.path.join(MAT, 'elite_skill.json'), encoding='utf-8').read())
BY = {int(x['id']): x for x in DATA}

TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#eef1f6;font-family:"Microsoft YaHei","WenQuanYi Zen Hei",sans-serif;padding:24px}
.card{width:__W__px;background:#fdfbf6;border-radius:24px;padding:30px 40px 26px;
      box-shadow:0 2px 12px rgba(120,110,95,.10);
      background-image:radial-gradient(#efe6d8 1.1px, transparent 1.1px);background-size:26px 26px}
.head{display:flex;align-items:center;gap:22px}
.ico{width:118px;height:118px;border-radius:20px;background:#fff;border:2px solid #ecd9b6;
     display:flex;align-items:center;justify-content:center;flex:0 0 auto}
.ico img{max-width:104px;max-height:104px}
.tt{flex:1;min-width:0}
.idx{display:inline-block;font-size:15px;font-weight:700;color:#b8711a;background:#f8e9cb;
     border-radius:8px;padding:1px 8px;letter-spacing:.5px}
.nm{font-size:38px;font-weight:800;color:#3d4450;margin-top:8px;letter-spacing:1px}
.kicker{margin-top:4px;font-size:15px;color:#9aa3b2;letter-spacing:2px}
.sec{margin-top:22px}
.bar{display:flex;align-items:center;height:46px;border-radius:10px;padding:0 14px;
     background:linear-gradient(102deg,#f0f9fe 0%,#d8eefb 26%,#b9dff5 58%,#d9eefc 80%,#eff8fd 100%);
     border-left:6px solid #6fbde8}
.bar b{font-size:24px;color:#fff;letter-spacing:1px;
       -webkit-text-stroke:4px #63b3e0;paint-order:stroke fill}
.txt{margin-top:12px;font-size:23px;line-height:1.72;color:#2f3540}
.tip .bar{background:linear-gradient(102deg,#fdf6e6 0%,#fbeccd 40%,#fdf3e0 100%);border-left-color:#e9b657}
.tip .bar b{-webkit-text-stroke:4px #dfa94a}
.tip .txt{color:#6b5a3a}
</style></head><body><div class="card">
<div class="head">
  <div class="ico"><img src="__ICON__"></div>
  <div class="tt">
    <span class="idx">NO.__ID__</span>
    <div class="nm">__NAME__</div>
    <div class="kicker">崩坏学园2 · 精英技能</div>
  </div>
</div>
<div class="sec"><div class="bar"><b>精英技能效果</b></div><div class="txt">__DESC__</div></div>
<div class="sec"><div class="bar"><b>生存指南</b></div><div class="txt">__GUIDE__</div></div>
__TIP__
</div></body></html>"""

TIP_BLOCK = ('<div class="sec tip"><div class="bar"><b>小建议</b></div>'
             '<div class="txt">%s</div></div>')


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def ensure_gif(sid, url):
    """下载演示动图；有的技能官方给的是静态 PNG，按魔数决定扩展名。"""
    for ext in ('gif', 'png'):
        p = os.path.join(GIFDIR, '%d.%s' % (sid, ext))
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
    ext = 'gif' if raw[:6] in (b'GIF89a', b'GIF87a') else 'png'
    p = os.path.join(GIFDIR, '%d.%s' % (sid, ext))
    io.open(p, 'wb').write(raw)
    return p


def render(sid):
    x = BY[sid]
    gif = ensure_gif(sid, x['display_img'])
    tip = TIP_BLOCK % esc(x['tips']) if (x.get('tips') or '').strip() else ''
    html = (TPL.replace('__W__', '900')
            .replace('__ICON__', 'file:///%s/%d.png' % (ICON.replace('\\', '/'), sid))
            .replace('__ID__', '%02d' % sid)
            .replace('__NAME__', esc(x['name']))
            .replace('__DESC__', esc(x['skill_desc']) or '—')
            .replace('__GUIDE__', esc(x['guide']) or '—')
            .replace('__TIP__', tip))
    hp = os.path.join(OUT, 'skill_%d.html' % sid)
    io.open(hp, 'w', encoding='utf-8').write(html)
    png = os.path.join(OUT, '精英技能_%02d_%s.png' % (sid, x['name']))
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                    '--force-device-scale-factor=2', '--window-size=1040,1600',
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
    im.crop((0, 0, w, min(h, y + 26))).save(png)
    with Image.open(gif) as g:
        gsize, frames = g.size, getattr(g, 'n_frames', 1)
    print('%s  card=%s  gif=%s %s %d帧 %.1fKB'
          % (x['name'], Image.open(png).size, gsize, os.path.basename(gif), frames,
             os.path.getsize(gif) / 1024))
    return png, gif


if __name__ == '__main__':
    ids = [int(a) for a in sys.argv[1:]] or [1]
    for i in ids:
        render(i)

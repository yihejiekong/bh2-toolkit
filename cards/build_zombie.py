# -*- coding: utf-8 -*-
"""僵尸娘样例 v2：资料卡 + 合并演示动图（PIL 画标签，宽 360 / 96 色 / 隔帧 → ~1.7MB）。

用法：python build_zombie2.py [id]
"""

import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont
import paths as P

BASE = P.BUILD
WORK = os.path.join(BASE, 'zombie_work')
OUT = os.path.join(BASE, 'zombie_cards')
EDGE = P.BROWSER
FONT_BD = P.FONT_BD
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120',
      'Referer': 'https://www.benghuai.com/data/'}
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

DATA = {int(x['id']): x for x in
        json.loads(io.open(os.path.join(BASE, 'zombie_all.json'), encoding='utf-8').read())}

# ---------- 资料卡 ----------
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
.chips{margin-top:10px;display:flex;gap:10px}
.chip{font-size:16px;color:#7a6a4f;background:#fff6e5;border:1px solid #f0dcb4;
      border-radius:999px;padding:3px 14px}
.chip.act{color:#8a5a86;background:#fbf0fa;border-color:#eccfe7}
.sec{margin-top:22px}
.bar{display:flex;align-items:center;height:46px;border-radius:10px;padding:0 14px;
     background:linear-gradient(102deg,#f0f9fe 0%,#d8eefb 26%,#b9dff5 58%,#d9eefc 80%,#eff8fd 100%);
     border-left:6px solid #6fbde8}
.bar b{font-size:24px;color:#fff;letter-spacing:1px;
       -webkit-text-stroke:4px #63b3e0;paint-order:stroke fill}
.txt{margin-top:12px;font-size:23px;line-height:1.72;color:#2f3540}
.sk{display:flex;gap:18px;margin-top:18px;padding-top:18px;border-top:1px dashed #e6dcc8}
.bar + .sk{border-top:none;padding-top:6px}
.no{flex:0 0 auto;width:52px;height:52px;border-radius:14px;background:#f8e9cb;color:#b8711a;
    font-size:24px;font-weight:800;display:flex;align-items:center;justify-content:center}
.skn{font-size:27px;font-weight:800;color:#3d4450;letter-spacing:.5px}
.dm{font-size:13px;color:#c08a3e;border:1px solid #eed3a3;background:#fff8ea;
    border-radius:6px;padding:0 6px;margin-left:8px;vertical-align:3px;font-weight:400}
.skd{margin-top:8px;font-size:22px;line-height:1.7;color:#39404c}
</style></head><body><div class="card">
<div class="head">
  <div class="ico"><img src="__ICON__"></div>
  <div class="tt">
    <span class="idx">NO.__ID__</span>
    <div class="nm">__NAME__</div>
    <div class="kicker">崩坏学园2 · 僵尸娘</div>
    <div class="chips"><span class="chip act">__MODE__</span><span class="chip">__DEBUT__</span></div>
  </div>
</div>
<div class="sec"><div class="bar"><b>档案</b></div><div class="txt">__INFO__</div></div>
<div class="sec"><div class="bar"><b>技能 __NSK__ 项</b></div>__SKILLS__</div>
</div></body></html>"""

SK_TPL = ('<div class="sk"><div class="no">%02d</div><div style="flex:1;min-width:0">'
          '<div class="skn">%s%s</div><div class="skd">%s</div></div></div>')


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def plain(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h or '')).strip()


def dl(url, name):
    url = urllib.parse.quote((url or '').replace('\\', '/'), safe=':/?&=%')
    p = os.path.join(WORK, name)
    if os.path.exists(p) and os.path.getsize(p) > 500:
        return p
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
    io.open(p, 'wb').write(raw)
    return p


def crop_bottom(png, keep=26):
    im = Image.open(png).convert('RGB')
    w, h = im.size
    bg = im.getpixel((3, h - 3))
    y = h - 1
    while y > 0:
        row = [im.getpixel((xx, y)) for xx in range(0, w, 7)]
        if any(abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 12 for p in row):
            break
        y -= 1
    im.crop((0, 0, w, min(h, y + keep))).save(png)


def build_card(z):
    icon = dl(z['icon'], 'icon_%s.png' % z['id'])
    blocks = []
    for i, s in enumerate(z['skills'], 1):
        has = bool((s.get('display_img') or '').strip())
        blocks.append(SK_TPL % (i, esc(s['name']),
                                '' if has else '<span class="dm">无演示</span>',
                                esc(s['skill_desc'].strip())))
    html = (TPL.replace('__W__', '900')
            .replace('__ICON__', 'file:///' + icon.replace('\\', '/'))
            .replace('__ID__', '%02d' % int(z['id']))
            .replace('__NAME__', esc(z['name']))
            .replace('__MODE__', esc(z.get('attack_mode') or '—'))
            .replace('__DEBUT__', esc(z.get('debut') or '—'))
            .replace('__INFO__', esc(plain(z.get('info'))) or '—')
            .replace('__NSK__', str(len(z['skills'])))
            .replace('__SKILLS__', ''.join(blocks)))
    hp = os.path.join(OUT, 'z%s.html' % z['id'])
    io.open(hp, 'w', encoding='utf-8').write(html)
    png = os.path.join(OUT, '僵尸娘_%s_%s.png' % (z['id'], z['name']))
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    '--no-first-run', '--force-device-scale-factor=2',
                    '--window-size=1040,2600', '--screenshot=' + png,
                    'file:///' + hp.replace('\\', '/')],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    crop_bottom(png)
    return png


# ---------- 合并演示动图 ----------
W_GIF = 360
PAD = 12
LBL = 36
STEP = 2
COLORS = 96
DUR = 240
F_BADGE = ImageFont.truetype(FONT_BD, 21)
F_NAME = ImageFont.truetype(FONT_BD, 22)


def build_montage(z):
    segs = []
    for i, s in enumerate(z['skills'], 1):
        u = (s.get('display_img') or '').strip()
        if not u:
            continue
        ext = '.gif' if u.lower().endswith('.gif') else '.png'
        p = dl(u, 'sk_%s_%d%s' % (z['id'], i, ext))
        im = Image.open(p)
        frames = []
        for k in range(0, getattr(im, 'n_frames', 1), STEP):
            im.seek(k)
            fr = im.convert('RGBA')
            h = round(fr.height * W_GIF / fr.width)
            frames.append(fr.resize((W_GIF, h), Image.LANCZOS))
        segs.append({'no': i, 'name': s['name'], 'frames': frames, 'h': frames[0].height})
    if not segs:
        return None
    tile_w = W_GIF + PAD * 2
    total_h = PAD + sum(LBL + s['h'] + PAD for s in segs)
    n = max(len(s['frames']) for s in segs)

    # 标签条预渲染一次
    labels = []
    for s in segs:
        lb = Image.new('RGB', (tile_w, LBL), (250, 238, 213))
        d = ImageDraw.Draw(lb)
        d.rectangle([0, 0, 4, LBL], fill=(230, 185, 90))
        d.text((14, (LBL - 26) // 2), '%02d' % s['no'], font=F_BADGE, fill=(184, 113, 26))
        d.text((54, (LBL - 27) // 2), s['name'], font=F_NAME, fill=(61, 68, 80))
        labels.append(lb)

    out = []
    for i in range(n):
        canvas = Image.new('RGB', (tile_w, total_h), (253, 251, 246))
        y = PAD
        for s, lb in zip(segs, labels):
            canvas.paste(lb, (0, y))
            y += LBL
            fr = s['frames'][i % len(s['frames'])]
            bg = Image.new('RGBA', fr.size, (253, 251, 246, 255))
            bg.alpha_composite(fr)
            canvas.paste(bg.convert('RGB'), (PAD, y))
            y += s['h'] + PAD
        out.append(canvas.convert('P', palette=Image.ADAPTIVE, colors=COLORS))
    gp = os.path.join(OUT, '僵尸娘_%s_%s_演示.gif' % (z['id'], z['name']))
    out[0].save(gp, save_all=True, append_images=out[1:], duration=DUR, loop=0,
                optimize=True, disposal=2)
    return gp


if __name__ == '__main__':
    zid = int(sys.argv[1]) if len(sys.argv) > 1 else 57
    z = DATA[zid]
    card = build_card(z)
    gi = build_montage(z)
    print('card', Image.open(card).size, '%.0fKB' % (os.path.getsize(card) / 1024))
    if gi:
        g = Image.open(gi)
        print('gif', g.size, g.n_frames, '帧  %.2fMB' % (os.path.getsize(gi) / 1048576))

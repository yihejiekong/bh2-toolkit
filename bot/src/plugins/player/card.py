# -*- coding: utf-8 -*-
"""玩家名片渲染：拼 HTML → headless Chrome 截图 → 裁掉底部空白。

素材全部来自 /app/bh2-bot/materials/：
  玩家名片/data.json     装备/萌章/角色/履历 查表
  玩家名片/avatars/*.png 玩家头像（128×128）
  玩家名片/roles/*.png   角色头像
  玩家名片/emblems/*.png 萌章图标
  图标/*.png             装备图标
"""
import datetime
import json
import os
import subprocess
import tempfile
import threading

from PIL import Image

try:
    from . import parse as P
except ImportError:                     # 被 service.py 以脚本方式导入时
    import parse as P

MATERIALS = os.environ.get('MATERIAL_ROOT', '/app/bh2-bot/materials')
PDIR = os.path.join(MATERIALS, '玩家名片')
ICON_DIR = os.path.join(MATERIALS, '图标')
CHROME = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
TMP = os.environ.get('BH2_CARD_TMP', os.path.join(PDIR, 'out'))
FONT = '"Microsoft YaHei","Noto Sans CJK SC","WenQuanYi Zen Hei","Source Han Sans SC",sans-serif'

SHEETS = [('weapons', '展示武器'), ('skills', '展示徽章'),
          ('costumes', '展示服装'), ('pets', '展示使魔')]

_data = None
_RENDER_LOCK = threading.Lock()      # 2G 内存的机器上串行渲染，避免多个 Chrome 并发


def data():
    global _data
    if _data is None:
        with open(os.path.join(PDIR, 'data.json'), encoding='utf-8') as f:
            _data = json.load(f)
    return _data


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def furl(p):
    return 'file://' + p.replace('\\', '/')


def emblem_path(img_id):
    for k in (img_id - 1, img_id):
        for nm in ('%d.png' % k, '%03d.png' % k):
            p = os.path.join(PDIR, 'emblems', nm)
            if os.path.exists(p):
                return p
    return None


def slots(items, total=10):
    cells = []
    for k in range(total):
        if k < len(items):
            nm, p = items[k]
            img = ('<img src="%s">' % furl(p)) if p else '<span class="ph">%s</span>' % esc(nm[:1])
            cells.append('<div class="slot" title="%s">%s<span class="cap">%s</span></div>'
                         % (esc(nm), img, esc(nm if len(nm) <= 7 else nm[:7] + '…')))
        else:
            cells.append('<div class="slot empty"></div>')
    return ''.join(cells)


CSS = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1000px;background:#eef1f6;font-family:@FONT@;padding:22px 0;
     background-image:radial-gradient(#d9dee8 1px,transparent 1px);background-size:22px 22px}
.card{background:linear-gradient(160deg,#fffdf8 0%,#fdf7ef 55%,#fbf1e9 100%);
      border-radius:20px;width:960px;margin:0 auto;padding:28px 28px 20px;position:relative;overflow:hidden;
      box-shadow:0 10px 30px rgba(120,110,95,.13)}
.card:before{content:"";position:absolute;inset:0;background-image:radial-gradient(#eadfcd 1px,transparent 1px);
            background-size:15px 15px;opacity:.5}
.card>*{position:relative}
h1{font-size:38px;text-align:center;color:#f0a52b;letter-spacing:2px;margin-bottom:18px;
   text-shadow:0 2px 0 #fff,0 3px 5px rgba(220,160,40,.28)}
.head{display:flex;gap:18px;align-items:flex-start}
.tile{width:118px;height:118px;border-radius:16px;background:linear-gradient(160deg,#9b4bd0,#7c33b8);
      border:4px solid #e2cdb8;display:flex;align-items:center;justify-content:center;
      box-shadow:0 3px 0 #fff inset,0 0 0 2px #c9b6d8,0 6px 14px rgba(90,60,120,.3);flex:0 0 auto}
.tile span{font-size:60px;font-weight:700;color:#fff;text-shadow:0 3px 6px rgba(0,0,0,.25)}
.tile img{width:100%;height:100%;border-radius:12px;display:block;object-fit:cover}
.nm{font-size:34px;font-weight:700;color:#2f3742;letter-spacing:1px}
.uid{font-size:20px;color:#8d97a6;margin-top:4px}
.uid b{color:#2f3742}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px 16px;margin-top:12px}
.kv{display:flex;align-items:baseline;gap:8px}
.k{font-size:21px;font-weight:700;color:#5d7fa8;letter-spacing:1px;white-space:nowrap}
.v{font-size:23px;font-weight:700;color:#1296d6;white-space:nowrap}
.sec{margin-top:18px}
.st{font-size:21px;font-weight:700;color:#c47a2a;letter-spacing:1px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.st:before{content:"";width:5px;height:19px;background:#f0b350;border-radius:3px}
.st em{font-style:normal;font-size:16px;color:#b0a89c;font-weight:400}
.ach{display:flex;gap:10px}
.abox{flex:1;background:#fff;border:2px solid #ecdfce;border-radius:12px;padding:8px 10px;text-align:center}
.abox .n{font-size:28px;font-weight:700}
.abox .l{font-size:16px;color:#8d97a6;margin-top:2px}
.gold .n{color:#e0a41c}.silver .n{color:#9aa6b4}.copper .n{color:#c47a3a}
.row{display:grid;grid-template-columns:repeat(10,1fr);gap:7px;margin-bottom:8px}
.rwrap{display:flex;flex-wrap:wrap;gap:8px}
.ro{display:flex;align-items:center;gap:9px;padding:5px 15px 5px 5px;border-radius:14px;background:#fff;border:1px solid #e9e3d9}
.ro .av{width:50px;height:50px;border-radius:11px;background:#eef1f6;object-fit:cover;display:block}
.ro .rn{font-size:19px;color:#3d4450;white-space:nowrap}
.slot{position:relative;aspect-ratio:1/1;border-radius:10px;background:#fff;border:2px solid #e8dccb;
      display:flex;align-items:center;justify-content:center;overflow:hidden}
.slot img{width:100%;height:100%;object-fit:contain}
.slot .ph{font-size:26px;font-weight:700;color:#c9bda9}
.slot .cap{position:absolute;bottom:0;left:0;right:0;font-size:10px;line-height:12px;color:#fff;
      background:rgba(40,50,65,.6);text-align:center;padding:1px 0;white-space:nowrap;overflow:hidden}
.slot.empty{background:repeating-linear-gradient(45deg,#f7f3ec,#f7f3ec 5px,#f1ebe1 5px,#f1ebe1 10px);
      border-style:dashed;border-color:#e4d8c6}
.career{display:flex;flex-wrap:wrap;gap:6px}.cbox{background:#fff;border:2px solid #ecdfce;border-radius:9px;padding:4px 10px;font-size:16px;color:#4a5462}
.srv{display:inline-block;margin-left:10px;padding:1px 10px;border-radius:8px;font-size:15px;
      font-weight:700;color:#fff;background:#7aa8c6;vertical-align:2px}
.srv.gf{background:#d09a6a}
.cbox b{color:#1296d6;margin-right:6px}
</style></head><body><div class="card">
<h1>崩坏学园2 玩家名片</h1>
<div class="head">
  <div class="tile">@AVATAR@</div>
  <div>
    <div class="nm">@NAME@</div>
    <div class="uid">UID <b>@UID@</b>@SRV@</div>
    <div class="grid">
      <div class="kv"><span class="k">等级</span><span class="v">LV.@LV@</span></div>
      <div class="kv"><span class="k">VIP</span><span class="v">@VIP@</span></div>
      <div class="kv"><span class="k">公会</span><span class="v">@GUILD@</span></div>
      <div class="kv"><span class="k">游戏时长</span><span class="v">@PLAYTIME@</span></div>
    </div>
  </div>
</div>
<div class="sec"><div class="st">收藏与成就</div>
  <div class="ach">
    <div class="abox"><div class="n">@ROLE@</div><div class="l">拥有角色</div></div>
    <div class="abox"><div class="n">@POST@</div><div class="l">看板</div></div>
    <div class="abox"><div class="n">@EMBLEM@</div><div class="l">萌章</div></div>
    <div class="abox gold"><div class="n">@GOLD@</div><div class="l">金成就</div></div>
    <div class="abox silver"><div class="n">@SILVER@</div><div class="l">银成就</div></div>
    <div class="abox copper"><div class="n">@COPPER@</div><div class="l">铜成就</div></div>
  </div>
</div>
@SLOTROWS@
@EMBSEC@
<div class="sec"><div class="st">拥有角色 <em>@ROLE@ 名</em></div><div class="rwrap">@ROLECHIPS@</div></div>
@CARSEC@
</div></body></html>"""


def build_html(summ_pl, det_pl, srv='b2'):
    d = data()
    summ = P.parse_summary(summ_pl)
    det = P.parse_detail(det_pl)
    items, embs, roles, cds = d['items'], d['emblems'], d['roles'], d['careers']
    srv_name = '官服' if srv == 'gf' else 'B服'

    rows_html = ''
    for key, title in SHEETS:
        lst = []
        for iid in det[key]:
            nm, f = items.get(key, {}).get(str(iid), ['ID %d' % iid, ''])
            p = os.path.join(ICON_DIR, f) if f else None
            lst.append((str(nm), p if p and os.path.exists(p) else None))
        if not lst:
            continue
        rows_html += ('<div class="sec"><div class="st">%s <em>%d/10</em></div><div class="row">%s</div></div>'
                      % (title, len(lst), slots(lst)))

    emb_cells = []
    for e in det['emblems']:
        nm, img = embs.get(str(e), ['萌章 %d' % e, 0])
        emb_cells.append((nm, emblem_path(img) if img else None))

    played = det['played']
    hh, mm, ss = played // 3600, played % 3600 // 60, played % 60

    av = None
    if summ.get('avatar'):
        for nm in ('%d.png' % summ['avatar'], '%03d.png' % summ['avatar']):
            p = os.path.join(PDIR, 'avatars', nm)
            if os.path.exists(p):
                av = p
                break
    avatar_html = ('<img src="%s">' % furl(av)) if av else '<span>%s</span>' % esc(summ['name'][:1])

    all_c = P.parse_careers(det_pl, cds)
    careers = [c for c in all_c if c['displayed']]
    cbox = ''.join('<div class="cbox"><b>%s</b>%s</div>'
                   % (datetime.datetime.fromtimestamp(c['ts']).strftime('%Y.%m.%d'), esc(c['text']))
                   for c in careers[:30])

    chips = []
    for rid in det['avatars']:
        nm, icon = roles.get(str(rid), ['角色 %d' % rid, 0])
        p = None
        for f in ('%d.png' % icon, '%03d.png' % icon):
            q = os.path.join(PDIR, 'roles', f)
            if os.path.exists(q):
                p = q
                break
        if p:
            chips.append('<span class="ro"><img class="av" src="%s"><span class="rn">%s</span></span>'
                         % (furl(p), esc(nm)))
        else:
            chips.append('<span class="ro"><span class="rn">%s</span></span>' % esc(nm))

    embsec = ''
    if emb_cells:
        embsec = ('<div class="sec"><div class="st">展示萌章 <em>%d/10</em></div><div class="row">%s</div></div>'
                  % (len(emb_cells), slots(emb_cells)))
    carsec = ''
    if careers:
        carsec = ('<div class="sec"><div class="st">游戏履历<em>对外展示 %d 条</em></div>'
                  '<div class="career">%s</div></div>' % (len(careers), cbox))

    html = CSS.replace('@FONT@', FONT)
    for k, v in [('@NAME@', esc(summ['name'])), ('@UID@', str(summ['uid'])),
                 ('@SRV@', '<span class="srv gf">官服</span>' if srv == 'gf'
                  else '<span class="srv">B服</span>'),
                 ('@LV@', str(summ['level'])), ('@VIP@', str(summ['vip'])),
                 ('@GUILD@', esc(summ['guild'] or '—')),
                 ('@PLAYTIME@', '%d小时%d分%d秒' % (hh, mm, ss)),
                 ('@AVATAR@', avatar_html),
                 ('@ROLE@', str(len(det['avatars']))), ('@POST@', str(det['post'])),
                 ('@EMBLEM@', str(det['emblem'])), ('@GOLD@', str(det['gold'])),
                 ('@SILVER@', str(det['silver'])), ('@COPPER@', str(det['copper'])),
                 ('@SLOTROWS@', rows_html), ('@EMBSEC@', embsec), ('@CARSEC@', carsec),
                 ('@ROLECHIPS@', ''.join(chips))]:
        html = html.replace(k, v)
    return html, summ, det, len(careers)


def render(summ_pl, det_pl, uid, srv='b2'):
    """返回 PNG 路径。"""
    with _RENDER_LOCK:
        return _render(summ_pl, det_pl, uid, srv)


def _render(summ_pl, det_pl, uid, srv='b2'):
    os.makedirs(TMP, exist_ok=True)
    html, summ, det, ncar = build_html(summ_pl, det_pl, srv)
    hp = os.path.join(TMP, 'card_%s_%d.html' % (srv, uid))
    png = os.path.join(TMP, 'card_%s_%d.png' % (srv, uid))
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html)
    cmd = [CHROME, '--headless=new', '--no-sandbox', '--disable-gpu',
           '--disable-dev-shm-usage', '--hide-scrollbars', '--allow-file-access-from-files',
           '--no-first-run', '--no-default-browser-check', '--disable-extensions',
           '--disable-background-networking', '--disable-sync', '--disable-translate',
           '--disable-features=Translate,BackForwardCache,AcceptCHFrame',
           '--force-device-scale-factor=2', '--window-size=1000,2400',
           '--screenshot=' + png, 'file://' + hp]
    try:
        os.remove(png)
    except OSError:
        pass
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if not os.path.exists(png):
        raise RuntimeError('chrome failed: %s' % r.stderr.decode('utf-8', 'replace')[-300:])
    im = Image.open(png).convert('RGB')
    w, h = im.size
    px = im.load()

    def blank(y):
        for x in range(0, w, 13):
            c = px[x, y]
            if not (abs(c[0] - 238) < 10 and abs(c[1] - 241) < 10 and abs(c[2] - 246) < 10) \
               and not (abs(c[0] - 217) < 12 and abs(c[1] - 222) < 12 and abs(c[2] - 232) < 12):
                return False
        return True

    bottom = h
    for y in range(h - 1, 0, -1):
        if not blank(y):
            bottom = min(h, y + 40)
            break
    if bottom < h - 4:
        im.crop((0, 0, w, bottom)).save(png)
    try:
        os.remove(hp)
    except OSError:
        pass
    return png, summ, det, ncar

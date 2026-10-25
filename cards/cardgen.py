# -*- coding: utf-8 -*-
"""装备图鉴卡（武器）HTML 生成器 —— 参考用户手做的「轰击晨星 / 愿望杯」卡面。

数据来源：崩坏学园2_装备图鉴_国服13.4.1_完整版.xlsx（满级数值/技能/觉醒/图标文件名/升格材料/亲密度上限）
          tsv_all/partnerposterdata.txt + textmap（觉醒角色身高/三围/生日/爱好/介绍/台词）
          tsv_all/stackmaterialdata.txt + textmap（升格材料名称与图标 ID）
图片：     崩坏学园2图鉴/图标/*.png、崩坏学园2图鉴/觉醒立绘/*.png
          升格材料图标按 DisplayImage 从 mihoyo 静态 CDN 拉取并缓存到 卡牌实验/assets/mat_<id>.png

技能数值展开规则（已用轰击晨星 / 愿望杯 的全部数字验证）：
  解包文本给出的是 1 级值 + 每级增量 + 每破增量，写作 `基础(+a每级/+b每破)`
  满级 X = 基础 + a × (MaxLv − 1)
  满破 Y = X + b × 10
  卡面显示 `X(Y)`
"""

import glob
import html
import os
import re
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bh2data as B
import openpyxl
from PIL import Image
import paths as P

DIR = P.TABLES
XLSX = P.XLSX
MDIR = P.MATERIALS
OUT = P.BUILD
ASSETS = os.path.join(OUT, 'assets')
TSV = P.TSV_DIR

os.makedirs(ASSETS, exist_ok=True)

tm = B.load_textmap()
CTRL = re.compile(r'</?color[^>]*>|#[a-zA-Z]')


def clean(t):
    """去掉 textmap 富文本标记：#n 转换行，其余 #x 控制码与 color 标签剥离。"""
    t = (t or '').replace('#n', '\n')
    t = re.sub(r'#?<color=[^>]*>', '', t)
    t = re.sub(r'</color>', '', t)
    t = CTRL.sub('', t)
    return t


def T0(v):
    """textmap 解析。"""
    if v is None:
        return ''
    v = str(v).strip()
    if v.upper().startswith('TEXT'):
        v = v[4:]
    return clean(tm.get(v, '')) if v.isdigit() else v


_, PRS = B.read_tsv(os.path.join(TSV, 'partnerposterdata.txt'))
POSTER = {}
for r in PRS:
    try:
        POSTER[int(float(r['PosterID']))] = r
    except (ValueError, KeyError):
        pass

# 升格材料 ID -> (名称, 图标 DisplayImage)
_, MATS = B.read_tsv(os.path.join(TSV, 'stackmaterialdata.txt'))
MAT = {}
for r in MATS:
    try:
        MAT[int(float(r['ID']))] = (T0(r.get('DisplayTitle')), r.get('DisplayImage') or '')
    except (ValueError, KeyError):
        pass

# 觉醒（拟人）素材需求表：personatedata.txt，EquipID = 武器「内部ID」，Material1..5 为材料 ID（0 表示空位）
_, PERS = B.read_tsv(os.path.join(TSV, 'personatedata.txt'))
PERSONA = {}
for r in PERS:
    try:
        eid = int(float(r['EquipID']))
    except (ValueError, KeyError):
        continue
    lst = []
    for i in range(1, 6):
        v = (r.get('Material%d' % i) or '').strip()
        if v and v != '0':
            lst.append(int(float(v)))
    if lst:
        PERSONA[eid] = lst

# PosterID -> FigureID（partnerposterdata）。立绘ID 列存的是 PosterID，贴图文件名用的是 FigureID
_, POSTERS = B.read_tsv(os.path.join(TSV, 'partnerposterdata.txt'))
POSTER_FIG = {}
for r in POSTERS:
    try:
        POSTER_FIG[int(float(r['PosterID']))] = int(float(r['FigureID']))
    except (TypeError, ValueError, KeyError):
        pass

MAT_CDN = 'http://static.image.mihoyo.com/hsod2_webview/images/broadcast_top/equip_icon/png/'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'}


def T(v):
    return T0(v)


def mat_icon(icon_id):
    """把材料图标缓存到 assets/ 并返回文件名（先查本地 图标/，缺了走 CDN）。"""
    if not icon_id:
        return None
    name = 'mat_%s.png' % icon_id
    dest = os.path.join(ASSETS, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return name
    url = MAT_CDN + '%s.png' % icon_id
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
    except Exception as e:
        print('  ! 材料图标下载失败 %s: %s' % (icon_id, e))
        return None
    with open(dest, 'wb') as f:
        f.write(data)
    return name


def equip_icon(icon_id):
    """武器/装备图标：本地 图标/<id>.png 优先，缺了按 CDN 的 equip_icon/png/<id>.png 补。"""
    if not icon_id:
        return None
    name = '%s.png' % int(num(icon_id))
    local = os.path.join(MDIR, '图标', name)
    if os.path.exists(local):
        return name
    dest = os.path.join(ASSETS, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return name
    try:
        data = urllib.request.urlopen(
            urllib.request.Request(MAT_CDN + name, headers=UA), timeout=30).read()
    except Exception as e:
        print('  ! 装备图标下载失败 %s: %s' % (icon_id, e))
        return None
    with open(dest, 'wb') as f:
        f.write(data)
    return name


# 表情差分：解包里每个拟人 bundle 除了整幅立绘，还带 5 张 256×256 的表情脸，
# Sprite 名 `<FigureID>_001`~`_005`，由 export_faces.py 导出到 觉醒立绘同级的 表情差分/。
FACE_DIR = os.path.join(MDIR, '表情差分')



def _face_square(src, dest):
    """表情差分的原始 Sprite 是 256×256，但内容可能只占中间一小块（旧角色只有脸部），
    也可能撑满整幅。统一裁到不透明包围盒再补成正方形，卡面上才大小一致。"""
    im = Image.open(src).convert('RGBA')
    box = im.getbbox()
    if box:
        im = im.crop(box)
    w, h = im.size
    s = max(w, h)
    canvas = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    canvas.paste(im, ((s - w) // 2, (s - h) // 2))
    canvas.save(dest)


def face_files(fig_id):
    """返回该立绘的表情差分文件名列表（按 _001.._005 排序），并复制到 assets/。"""
    if not fig_id:
        return []
    out = []
    for p in sorted(glob.glob(os.path.join(FACE_DIR, '%s_*.png' % fig_id))):
        name = os.path.basename(p)
        dest = os.path.join(ASSETS, name)
        if not os.path.exists(dest):
            _face_square(p, dest)
        out.append(name)
    return out


# ---------------- 数据 ----------------
def load_rows():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb['武器']
    hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(hdr)}
    rows = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        dn = str(row[idx['游戏内ID']])
        rarity = row[idx['稀有度']] or 0
        cur = rows.get(dn)
        if cur is None or (rarity or 0) > (cur[idx['稀有度']] or 0):
            rows[dn] = row
    return idx, rows


IDX, ROWS = load_rows()


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# 数值型技能参数：把 "100(+4每破)" / "20.4(+0.2每级/+1每破)" 展开成 满级值(满破值)
PH = re.compile(r'(\d+(?:\.\d+)?)\(([^()]*每[级破][^()]*)\)')


def trim(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return s if s else '0'


def expand_params(text, maxlv):
    def rep(m):
        base = float(m.group(1))
        add_lv = 0.0
        add_bk = 0.0
        for val, kind in re.findall(r'([+-]?\d+(?:\.\d+)?)\s*每([级破])', m.group(2)):
            if kind == '级':
                add_lv += float(val)
            else:
                add_bk += float(val)
        lv_val = base + add_lv * (maxlv - 1)
        full = lv_val + add_bk * 10
        if abs(full - lv_val) < 1e-9:
            return trim(lv_val)
        return '%s(%s)' % (trim(lv_val), trim(full))
    return PH.sub(rep, text)


NUMRE = re.compile(r'(\d+(?:\.\d+)?)')


def hl(s):
    s = html.escape(s)
    return NUMRE.sub(r'<b class="n">\1</b>', s)


def split_skills(raw):
    out = []
    for line in (raw or '').split('\n'):
        line = line.strip()
        if not line:
            continue
        title, _, body = line.partition('：')
        out.append((title.strip(), body.strip() or title.strip()))
    return out


def poster_bio(poster_id):
    pr = POSTER.get(int(poster_id or 0))
    if not pr:
        return None
    # 新装备的占位看板行（PosterName 形如「看板No.2202 Name」；短介绍/初见 都是模板字串）→ 不显示觉醒块
    raw_name = (T(pr.get('PosterName')) or '').strip()
    if re.match(r'^看板\s*No\.', raw_name) or raw_name in ('Name', '名字'):
        return None
    talks = [T(x) for x in (pr.get('TalkList') or '').split(';') if x.strip()]

    def na(v):
        s = (v or '').strip()
        if s in ('-', '--', '—', '0'):
            return ''
        if s and not set(s) - set('?/ '):  # ?? / ??/??/?? 这类占位值等同空
            return ''
        return s
    return {
        'name': T(pr.get('PosterName')),
        'height': na((pr.get('height') or '').replace('cm', '')),
        'threesize': na(pr.get('threesize')),
        'birthday': na(pr.get('brithday') or pr.get('birthday')),
        'hobby': T(pr.get('hobby')),
        'desc': T(pr.get('description')),
        'first': T(pr.get('FirstSightDialogue')),
        'talks': [t for t in talks if t],
    }


# ---------------- 系列胶囊 ----------------
# 客户端「系列图标」的 Sprite 不在本地解包副本里（988 个 Sprite 无 Serie*，CDN 也无 equip_series），
# 因此按用户要求改用文字胶囊：系列全称，放在属性块之后。
NO_SERIES = {'', 'None', 'none', 'NONE', '无'}


def series_chip(series):
    s = (series or '').strip()
    if s in NO_SERIES:
        return ''
    return '<span class="schip">%s</span>' % html.escape(s)


def build(dn):
    row = ROWS[str(dn)]
    g = lambda k: row[IDX[k]]
    maxlv = int(num(g('最大等级'), 1))
    dmg = g('满级伤害')
    ammo = g('满级载弹')
    rate = g('满级射速')
    crit = num(g('暴击率'))
    stats = [('负重', trim(num(g('负重'))))]
    if num(dmg) > 0:
        stats.append(('攻击力', trim(num(dmg))))
    if num(ammo) > 0:
        stats.append(('载弹', trim(num(ammo))))
    if num(rate) > 0:
        stats.append(('攻速', trim(num(rate)) + '<span class="unit">/ 秒</span>'))
    if crit > 0:
        stats.append(('暴击率', trim(crit * 100) + '%'))
    if num(g('亲密度上限')) > 0:
        stats.append(('亲密度上限', trim(num(g('亲密度上限')))))

    icon_file = g('图标文件')
    fig_file = g('觉醒立绘文件')
    pid = int(num(g('立绘ID')))
    # xlsx 里少数新装备的图标/立绘文件名留空：图标按图标ID 走 CDN，立绘按「立绘ID_*.png」在目录里找
    if not icon_file:
        icon_file = equip_icon(g('图标ID'))
    fig_small = False
    if not fig_file and pid:
        # 立绘ID 是 PosterID，必须先换成 FigureID 再找图，否则会撞名（如 21105 立绘ID=1028 被当成 1028_轰击晨星）
        fid = POSTER_FIG.get(pid)
        if fid:
            cand = glob.glob(os.path.join(MDIR, '觉醒立绘', '%d_*.png' % fid))
            if cand:
                fig_file = os.path.basename(sorted(cand)[0])
            else:
                # 大图没随包下发的新角色：退回「看板小图」（134×162，图鉴里就是这张）
                small = os.path.join(MDIR, '看板小图', '%d.png' % fid)
                if os.path.exists(small):
                    fig_file = 'small_%d.png' % fid
                    fig_small = True
                    shutil.copyfile(small, os.path.join(ASSETS, fig_file))
    for src, dest in ((os.path.join(MDIR, '图标', icon_file or ''), os.path.join(ASSETS, icon_file or '')),
                      (os.path.join(MDIR, '觉醒立绘', fig_file or ''), os.path.join(ASSETS, fig_file or ''))):
        if src and os.path.exists(src) and not os.path.exists(dest):
            shutil.copyfile(src, dest)
    # 表情差分的文件名前缀就是 FigureID（例 1275_米梅.png → 1275）
    fig_id = os.path.basename(fig_file).split('_')[0] if fig_file else ''
    faces = face_files(fig_id) if fig_file else []

    mats = []
    for mid in PERSONA.get(int(num(g('内部ID'))), []):
        name, icon_id = MAT.get(mid, ('', ''))
        f = mat_icon(icon_id)
        if f:
            mats.append({'name': name, 'file': f, 'count': 1})
    # 同名材料合并计数，保留首次出现顺序
    merged = []
    for m in mats:
        for n in merged:
            if n['name'] == m['name']:
                n['count'] += 1
                break
        else:
            merged.append(m)
    mats = merged

    bio = poster_bio(int(num(g('立绘ID'))))
    skills = [(t_, expand_params(b_, maxlv)) for t_, b_ in split_skills(g('技能（解包原文）'))]
    return {
        'name': g('名称'),
        'rarity': int(num(g('稀有度'))),
        'type': g('武器类型') or '',
        'series': g('系列') or '',
        'maxlv': maxlv,
        'stats': stats,
        'skills': skills,
        'note': clean(g('描述（解包原文）') or ''),
        'icon': icon_file,
        'figure': fig_file,
        'fig_small': fig_small,
        'faces': faces,
        'mats': mats,
        'bio': bio,
    }


# ---------------- 渲染 ----------------
CSS = """
* { box-sizing:border-box; margin:0; padding:0; }
html,body { background:#eceef2; }
body { font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif; -webkit-font-smoothing:antialiased; }
.card { position:relative; width:1080px; margin:0 auto; padding:44px 64px 34px;
  background:linear-gradient(180deg,#fffefb 0%,#fdf7ee 48%,#fdf8f2 100%); overflow:hidden; }
.card:before { content:""; position:absolute; inset:0; pointer-events:none; opacity:.9;
  background:
   radial-gradient(circle at 90% 6%, rgba(246,196,120,.10) 0 40px, rgba(246,196,120,.30) 40px 42px, transparent 43px),
   radial-gradient(circle at 7% 12%, rgba(160,205,240,.10) 0 30px, rgba(160,205,240,.28) 30px 32px, transparent 33px),
   radial-gradient(circle at 96% 36%, rgba(150,205,240,.10) 0 36px, rgba(150,205,240,.30) 36px 38px, transparent 39px),
   radial-gradient(circle at 3% 58%, rgba(240,175,205,.10) 0 32px, rgba(240,175,205,.26) 32px 34px, transparent 35px),
   radial-gradient(circle at 94% 76%, rgba(170,215,170,.10) 0 28px, rgba(170,215,170,.26) 28px 30px, transparent 31px),
   radial-gradient(circle at 24% 94%, rgba(160,205,240,.08) 0 34px, rgba(160,205,240,.24) 34px 36px, transparent 37px),
   radial-gradient(circle at 78% 97%, rgba(246,196,120,.08) 0 30px, rgba(246,196,120,.24) 30px 32px, transparent 33px);
}
.card:after { content:""; position:absolute; inset:0; pointer-events:none; opacity:.55;
  background-image:radial-gradient(rgba(150,175,205,.20) 1.4px, transparent 1.5px);
  background-size:26px 26px; z-index:0; }
.card > * { position:relative; z-index:1; }
.title { position:relative; text-align:center; font-size:47px; font-weight:900; letter-spacing:2px;
  color:#f7a41c; -webkit-text-stroke:4px #fff; paint-order:stroke fill;
  text-shadow:0 2px 0 rgba(247,164,28,.14); }
.head { position:relative; display:flex; gap:22px; margin-top:26px; align-items:flex-start; }
.icon { width:150px; height:150px; flex:0 0 auto; border-radius:16px; padding:8px;
  background:linear-gradient(150deg,#d778e4 0%,#a840cc 55%,#8b2fb4 100%);
  box-shadow:0 3px 8px rgba(90,20,120,.28), inset 0 0 0 3px rgba(255,255,255,.45); }
.icon img { width:100%; height:100%; object-fit:contain; display:block; }
.hinfo { padding-top:6px; flex:1 1 auto; }
.wrow { display:flex; align-items:center; gap:10px; }
.wname { font-size:41px; font-weight:900; color:#2b2b2b; letter-spacing:1px; }
.stars { margin-top:6px; color:#ffb400; font-size:40px; letter-spacing:5px;
  -webkit-text-stroke:3px #fff; paint-order:stroke fill; }
.lvrow { margin-top:8px; display:flex; align-items:center; gap:14px; }
.lv { color:#f7941e; font-weight:900; font-size:35px; letter-spacing:1px; }
.ptype { color:#e8890c; font-weight:800; font-size:34px; }
.schip { display:inline-block; padding:5px 20px 7px; border-radius:24px; font-size:29px;
  font-weight:900; color:#fff; letter-spacing:2px;
  background:linear-gradient(160deg,#b667e0 0%,#8f45c9 60%,#7a33b0 100%);
  box-shadow:0 2px 5px rgba(90,30,130,.28), inset 0 0 0 2px rgba(255,255,255,.30);
  text-shadow:0 1px 2px rgba(70,20,100,.35); }
.chipline { position:relative; margin:18px 12px 0; }
.note { position:relative; margin:16px 4px 0; font-size:27px; color:#e08320; font-weight:800; letter-spacing:.5px; white-space:pre-line; }
.stats { position:relative; display:grid; grid-template-columns:1fr 1fr; gap:10px 26px; margin:26px 12px 4px; }
.stat { display:flex; align-items:baseline; gap:16px; font-size:36px; }
.stat .k { color:#3d6fa4; font-weight:900; min-width:132px; }
.stat .v { color:#0aa6e8; font-weight:900; letter-spacing:.5px; }
.stat .unit { font-size:26px; color:#0aa6e8; font-weight:800; margin-left:3px; }
.sk { position:relative; margin-top:26px; }
.traits { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:12px 34px; margin:16px 12px 0; }
.traits .t { display:flex; align-items:center; gap:12px; font-size:36px; font-weight:900; color:#99a2b1; letter-spacing:1px; }
.traits .t img { width:52px; height:52px; display:block; }
.skmeta { position:relative; margin:10px 2px 0; font-size:28px; font-weight:800; color:#98a1b0; letter-spacing:.5px; }
.skbar .kind { position:absolute; right:14px; top:50%; transform:translateY(-50%); font-size:23px; font-weight:900;
  color:#fff; letter-spacing:1px; padding:3px 14px 5px; border-radius:14px;
  background:linear-gradient(160deg,#8fd0f0 0%,#5fb6e3 100%); box-shadow:0 1px 3px rgba(40,120,170,.25); }
.skbar { position:relative; height:54px; border-radius:4px; border-left:9px solid #35a3e0;
  background:linear-gradient(102deg,#f0f9fe 0%,#d8eefb 26%,#b9dff5 58%,#d9eefc 80%,#eff8fd 100%);
  box-shadow:inset 0 0 0 1px #cfe6f4, 0 1px 2px rgba(0,0,0,.05); }
.skbar .sn { position:absolute; left:16px; top:50%; transform:translateY(-50%); white-space:nowrap;
  font-size:34px; font-weight:900; color:#fff; letter-spacing:1px;
  -webkit-text-stroke:4.5px #6fbde8; paint-order:stroke fill;
  text-shadow:0 2px 3px rgba(40,120,170,.18); }
.sbody { position:relative; font-size:32px; line-height:1.58; color:#333; margin:14px 2px 0; text-align:justify; }
.n { color:#0aa6e8; font-weight:900; }
.mats { position:relative; display:flex; gap:22px; justify-content:center; margin-top:26px; }
.mat { position:relative; width:110px; height:110px; border-radius:15px; padding:7px;
  background:linear-gradient(150deg,#cf7ce0 0%,#a840cc 60%,#8a2eb2 100%);
  box-shadow:0 2px 6px rgba(90,20,120,.25), inset 0 0 0 3px rgba(255,255,255,.42); }
.mat img { width:100%; height:100%; object-fit:contain; display:block; }
.mat .cnt { position:absolute; right:-8px; bottom:-8px; min-width:38px; height:38px; padding:0 6px;
  border-radius:19px; display:flex; align-items:center; justify-content:center;
  font-size:24px; font-weight:900; color:#fff; line-height:1;
  background:linear-gradient(160deg,#6a46b8 0%,#4a2b8f 100%); box-shadow:0 2px 4px rgba(40,10,80,.35); }
.aw { position:relative; margin-top:30px; border-top:2px dashed #f0d9b8; padding-top:20px; }
.awname { font-size:35px; font-weight:900; color:#f7941e; letter-spacing:1px; }
.awgrid { display:grid; grid-template-columns:1fr 1fr; gap:2px 34px; margin:12px 0 4px; font-size:27px; }
.awgrid .k { color:#3d6fa4; font-weight:900; }
.awgrid .v { color:#2c2c2c; font-weight:800; }
.awhobby { font-size:27px; margin:2px 0 10px; }
.awhobby .k { color:#3d6fa4; font-weight:900; }
.awhobby .v { color:#2c2c2c; font-weight:800; }
.awdesc { font-size:25px; line-height:1.58; color:#3a3a3a; text-align:justify; white-space:pre-line; }
.quote { margin-top:14px; font-size:27px; color:#2e9adb; font-weight:800; }
.figure { margin-top:20px; text-align:center; }
.figure img { width:100%; display:block; margin:0 auto; }
.figure.small img { width:170px; }
.faces { display:flex; flex-wrap:wrap; justify-content:center; gap:16px; margin-top:22px; }
.faces .face { width:226px; height:226px; border-radius:14px; overflow:hidden; background:#fff;
  box-shadow:0 3px 9px rgba(120,90,160,.18), inset 0 0 0 2px rgba(255,255,255,.7); }
.faces .face img { width:100%; height:100%; object-fit:cover; display:block; }
"""


def render(card):
    s = card
    stars = '★' * s['rarity']
    stat_html = ''.join('<div class="stat"><span class="k">%s</span><span class="v">%s</span></div>' % (k, v)
                        for k, v in s['stats'])
    sk_html = ''
    for item in s['skills']:
        t_, b_ = item[0], item[1]
        meta = item[2] if len(item) > 2 else None
        kind = item[3] if len(item) > 3 else None
        meta_html = '<div class="skmeta">%s</div>' % html.escape(meta) if meta else ''
        kind_html = '<span class="kind">%s</span>' % html.escape(kind) if kind else ''
        sk_html += ('<div class="sk"><div class="skbar"><span class="sn">%s</span>%s</div>%s'
                    '<div class="sbody">%s</div></div>' % (hl(t_), kind_html, meta_html, hl(b_)))
    tr_html = ''
    if s.get('traits'):
        tr_html = ('<div class="traits">%s</div>'
                   % ''.join('<div class="t"><img src="assets/%s"><span>%s</span></div>'
                             % (t['file'], html.escape(t['name'])) for t in s['traits']))
    mat_html = ''
    if s['mats']:
        # 与手做参考卡一致：一个材料画一个格子（2 个同种材料就画 2 格），不额外标数量
        tiles = []
        for m in s['mats']:
            for _ in range(m['count']):
                tiles.append('<div class="mat"><img src="assets/%s" alt="%s" title="%s"></div>'
                             % (m['file'], html.escape(m['name']), html.escape(m['name'])))
        mat_html = '<div class="mats">%s</div>' % ''.join(tiles)
    chip = series_chip(s['series'])
    chip_html = '<div class="chipline">%s</div>' % chip if chip else ''
    note = '<div class="note">%s</div>' % hl(s['note']) if s['note'] else ''
    aw = ''
    b = s['bio']
    if b:
        rows = []
        if b['height']:
            rows.append(('身高', b['height'] + 'cm'))
        if b['threesize']:
            rows.append(('三围', b['threesize']))
        if b['birthday']:
            rows.append(('生日', b['birthday']))
        grid = ''.join('<div><span class="k">%s：</span><span class="v">%s</span></div>' % (k, html.escape(v))
                       for k, v in rows)
        hobby = ('<div class="awhobby"><span class="k">爱好：</span><span class="v">%s</span></div>'
                 % html.escape(b['hobby'])) if b['hobby'] else ''
        quote = ('<div class="quote">「%s」</div>' % html.escape(b['first'] or (b['talks'][0] if b['talks'] else ''))
                 if (b['first'] or b['talks']) else '')
        fig_html = ('<div class="figure%s"><img src="assets/%s"></div>'
                    % (' small' if s.get('fig_small') else '', s['figure'])) if s['figure'] else ''
        faces = s.get('faces') or []
        faces_html = ''
        if faces and s['figure']:
            faces_html = ('<div class="faces">%s</div>'
                          % ''.join('<div class="face"><img src="assets/%s"></div>' % f for f in faces))
        aw = ('<div class="aw"><div class="awname">%s</div><div class="awgrid">%s</div>%s'
              '<div class="awdesc">%s</div>%s%s%s</div>'
              % (html.escape(b['name']), grid, hobby, html.escape(b['desc']), quote, fig_html, faces_html))
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>%s - 崩坏学园2 装备图鉴卡</title>
<style>%s</style></head><body><div class="card">
<div class="title">崩坏学园2 装备图鉴卡</div>
<div class="head">
  <div class="icon"><img src="assets/%s"></div>
  <div class="hinfo">
    <div class="wrow"><span class="wname">%s</span></div>
    <div class="stars">%s</div>
    <div class="lvrow"><span class="lv">LV.%d</span><span class="ptype">%s</span></div>
  </div>
</div>
%s
<div class="stats">%s</div>
%s
%s
%s
%s
%s
</div></body></html>""" % (s['name'], CSS, s['icon'], html.escape(s['name']), stars,
                           s['maxlv'], html.escape(s['type']),
                           note, stat_html, tr_html, chip_html, sk_html, mat_html, aw)


def main(dns):
    for dn in dns:
        card = build(dn)
        path = os.path.join(OUT, 'card_%s.html' % dn)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render(card))
        print('wrote', path, os.path.getsize(path), '| 觉醒:', bool(card['bio'] and card['figure']),
              '| 材料:', [m['name'] for m in card['mats']])


if __name__ == '__main__':
    main(sys.argv[1:] or ['897', '3298'])

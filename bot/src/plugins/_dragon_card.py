# -*- coding: utf-8 -*-
"""群龙王榜的统计与出图核心（不依赖 nonebot，便于单独测试）。

表：
  msg_stat(group_id, qq, week, cnt)     每周每人条数，week = 该周周一日期
  dragon_name(group_id, qq, name)       昵称缓存
  dragon_week(group_id, week, settled, settled_at)  结算标记
"""
import asyncio
import os
import sqlite3
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

import httpx

try:
    from . import _config
except ImportError:                      # 独立脚本导入
    import _config

ROOT = Path(_config.MATERIAL_ROOT) / '龙王榜'
AV_DIR = ROOT / 'avatars'
OUT_DIR = ROOT / 'out'
DB = str(_config.DB)
CHROME = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
KEEP_FILES = 60
FONT = os.environ.get(
    'DRAGON_FONT',
    '"WenQuanYi Zen Hei","Noto Sans CJK SC","Microsoft YaHei",sans-serif')

SVG_CROWN = ('<svg class="crown" width="30" height="24" viewBox="0 0 30 24">'
             '<path d="M3 21h24v-2H3v2z" fill="#e9a017"/>'
             '<path d="M3 17l1.6-11 5.9 5.2L15 3l4.5 8.2L25.4 6 27 17H3z" fill="#ffcf4d" '
             'stroke="#e9a017" stroke-width="1.6" stroke-linejoin="round"/></svg>')

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#eef1f6;font-family:@FONT@;padding:22px}
.card{width:952px;background:#fdfbf6;border-radius:24px;padding:32px 38px 24px;
      box-shadow:0 2px 12px rgba(120,110,95,.08);
      background-image:radial-gradient(#efe6d8 1.1px, transparent 1.1px);
      background-size:26px 26px}
h1{text-align:center;font-size:43px;font-weight:800;color:#f0a23c;letter-spacing:2px;
   text-shadow:0 2px 0 #fff}
.sub{text-align:center;margin-top:9px;font-size:19px;color:#9aa3b0}
.sub b{color:#1296d6;font-weight:700}
.list{margin-top:22px}
.row{display:flex;align-items:center;gap:16px;padding:10px 16px;border-radius:15px;
     background:#fff;border:2px solid #efe7da;margin-bottom:9px}
.rk{width:50px;height:50px;flex:none;border-radius:13px;display:flex;align-items:center;
    justify-content:center;font-size:25px;font-weight:800;color:#fff;background:#c3cbd6}
.av{width:62px;height:62px;flex:none;border-radius:13px;object-fit:cover;background:#eef1f6;
    border:2px solid #efe7da;display:flex;align-items:center;justify-content:center;
    font-size:28px;font-weight:700;color:#b9c1cd}
.nm{flex:1;font-size:25px;font-weight:700;color:#3d4450;white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis}
.ct{flex:none;font-size:27px;font-weight:800;color:#1296d6;min-width:118px;text-align:right}
.ct em{font-style:normal;font-size:17px;font-weight:700;color:#a8b0bb;margin-left:4px}
.crown{flex:none}
.r1{background:linear-gradient(90deg,#fffaf0,#fffdf9);border-color:#f0d69b;
    box-shadow:0 3px 0 #f7e8c8}
.r1 .rk{background:linear-gradient(160deg,#ffd777,#e9a017)}
.r2 .rk{background:linear-gradient(160deg,#dbe2ea,#9fa9b8)}
.r3 .rk{background:linear-gradient(160deg,#f0c39c,#c4864f)}
.ft{margin-top:14px;text-align:center;font-size:17px;color:#b7ac9e}
"""


# ---------------- 数据库 ----------------
def _conn():
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def ensure():
    conn = _conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS msg_stat (
        group_id TEXT NOT NULL, qq TEXT NOT NULL, week TEXT NOT NULL,
        cnt INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (group_id, qq, week))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS dragon_week (
        group_id TEXT PRIMARY KEY, week TEXT NOT NULL,
        settled INTEGER NOT NULL DEFAULT 0, settled_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS dragon_name (
        group_id TEXT NOT NULL, qq TEXT NOT NULL, name TEXT NOT NULL,
        PRIMARY KEY (group_id, qq))""")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_stat_lookup '
                 'ON msg_stat (group_id, week, cnt DESC)')
    conn.commit()
    conn.close()


def week_key(d=None):
    d = d or date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def week_range(week):
    a = date.fromisoformat(week)
    return a, a + timedelta(days=6)


def incr(group_id, qq):
    try:
        conn = _conn()
        conn.execute('INSERT INTO msg_stat(group_id, qq, week, cnt) VALUES(?,?,?,1) '
                     'ON CONFLICT(group_id, qq, week) DO UPDATE SET cnt = cnt + 1',
                     (str(group_id), str(qq), week_key()))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def top(group_id, week, limit=10):
    conn = _conn()
    rows = conn.execute('SELECT qq, cnt FROM msg_stat WHERE group_id=? AND week=? '
                        'ORDER BY cnt DESC, qq ASC LIMIT ?',
                        (str(group_id), week, limit)).fetchall()
    total = conn.execute('SELECT COALESCE(SUM(cnt),0) FROM msg_stat '
                         'WHERE group_id=? AND week=?',
                         (str(group_id), week)).fetchone()[0]
    conn.close()
    return rows, int(total or 0)


def groups_this_week(week):
    conn = _conn()
    rows = conn.execute('SELECT DISTINCT group_id FROM msg_stat WHERE week=?',
                        (week,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def mark_settled(group_id, week):
    conn = _conn()
    conn.execute("INSERT INTO dragon_week(group_id, week, settled, settled_at) "
                 "VALUES(?,?,1,datetime('now','localtime')) "
                 "ON CONFLICT(group_id) DO UPDATE SET week=excluded.week, settled=1, "
                 "settled_at=excluded.settled_at", (str(group_id), week))
    conn.commit()
    conn.close()


def cached_name(group_id, qq):
    try:
        conn = _conn()
        r = conn.execute('SELECT name FROM dragon_name WHERE group_id=? AND qq=?',
                         (str(group_id), str(qq))).fetchone()
        conn.close()
    except sqlite3.Error:
        return str(qq)
    return (r[0] if r and r[0] else str(qq))


def save_name(group_id, qq, name):
    try:
        conn = _conn()
        conn.execute('INSERT INTO dragon_name(group_id, qq, name) VALUES(?,?,?) '
                     'ON CONFLICT(group_id, qq) DO UPDATE SET name=excluded.name',
                     (str(group_id), str(qq), name))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


# ---------------- 头像 ----------------
def cached_avatar(qq):
    p = AV_DIR / ('%s.png' % qq)
    return p if p.exists() and p.stat().st_size > 1000 else None


async def fetch_avatar(qq):
    p = cached_avatar(qq)
    if p:
        return p
    AV_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as cli:
            r = await cli.get('https://q1.qlogo.cn/g?b=qq&nk=%s&s=100' % qq)
        if r.status_code == 200 and len(r.content) > 800:
            p = AV_DIR / ('%s.png' % qq)
            p.write_bytes(r.content)
            return p
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------- 出图 ----------------
def _html(entries, week, group_name, total):
    a, b = week_range(week)
    blocks = []
    for i, qq, name, cnt, av in entries:
        cls = 'r1' if i == 1 else ''
        crown = SVG_CROWN if i == 1 else ''
        if av:
            avh = '<img class="av" src="file://%s">' % str(av).replace('\\', '/')
        else:
            avh = '<div class="av">%s</div>' % (name[:1] if name else '?')
        blocks.append(
            '<div class="row %s"><div class="rk">%d</div>%s%s'
            '<span class="nm">%s</span><span class="ct">%d<em>条</em></span></div>'
            % (cls, i, avh, crown, name, cnt))
    sub = '%s — %s' % (a.strftime('%Y.%m.%d'), b.strftime('%Y.%m.%d'))
    if group_name:
        sub += ' · ' + group_name
    if total:
        sub += ' · 本周共 <b>%d</b> 条' % total
    return ('<html><head><meta charset="utf-8"><style>%s</style></head><body>'
            '<div class="card"><h1>崩坏学园2 · 群龙王榜</h1>'
            '<div class="sub">%s</div><div class="list">%s</div>'
            '<div class="ft">统计口径：本周群消息条数 · 每周日 22:00 刷新</div>'
            '</div></body></html>' % (CSS.replace('@FONT@', FONT), sub, ''.join(blocks)))


def crop(png):
    from PIL import Image
    im = Image.open(png).convert('RGB')
    w, h = im.size
    px = im.load()
    bottom = h
    for y in range(h - 1, 0, -1):
        blank = True
        for x in range(0, w, 11):
            c = px[x, y]
            if not (abs(c[0] - 238) < 10 and abs(c[1] - 241) < 10 and abs(c[2] - 246) < 10):
                blank = False
                break
        if not blank:
            bottom = min(h, y + 44)
            break
    if bottom < h - 4:
        im.crop((0, 0, w, bottom)).save(png)


def shoot(html, png):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fd, hp = tempfile.mkstemp(suffix='.html', dir=str(OUT_DIR))
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(html)
    cmd = [CHROME, '--headless=new', '--no-sandbox', '--disable-gpu',
           '--disable-dev-shm-usage', '--hide-scrollbars', '--no-first-run',
           '--force-device-scale-factor=2', '--window-size=1000,1500',
           '--screenshot=' + png, 'file://' + hp]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    os.remove(hp)
    if not os.path.exists(png):
        raise RuntimeError('chrome 截图失败')
    crop(png)


async def render_board(bot, group_id, week=None):
    """出图。bot=None 时用缓存昵称/头像（测试用）。返回 (png, 行数)。"""
    week = week or week_key()
    rows, total = top(group_id, week, 10)
    if not rows:
        return None, 0
    entries = []
    for i, (qq, cnt) in enumerate(rows, 1):
        if bot is not None:
            try:
                info = await bot.call_api('get_group_member_info', group_id=int(group_id),
                                          user_id=int(qq), no_cache=False)
                name = (info.get('card') or info.get('nickname') or str(qq)).strip() or str(qq)
            except Exception:  # noqa: BLE001
                name = cached_name(group_id, qq)
            save_name(group_id, qq, name)
            av = await fetch_avatar(qq)
        else:
            name = cached_name(group_id, qq)
            av = cached_avatar(qq)
        entries.append((i, qq, name, cnt, av))
    group_name = ''
    if bot is not None:
        try:
            info = await bot.call_api('get_group_info', group_id=int(group_id))
            group_name = (info.get('group_name') or '').strip()
        except Exception:  # noqa: BLE001
            pass
    html = _html(entries, week, group_name, total)
    png = OUT_DIR / ('dragon_%s_%s.png' % (group_id, week))
    await asyncio.to_thread(shoot, html, str(png))
    cleanup()
    return png, len(entries)


def cleanup():
    try:
        files = sorted(OUT_DIR.glob('dragon_*.png'), key=lambda p: p.stat().st_mtime,
                       reverse=True)
        for p in files[KEEP_FILES:]:
            p.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass

# -*- coding: utf-8 -*-
"""批量（并行版）：58 只僵尸娘 → 资料卡 + 合并演示动图，落 materials/僵尸娘/。

每个 worker 用独立的 Edge user-data-dir，避免多实例抢 profile。
"""

import io
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import build_zombie as B
import paths as P

MAT = os.path.join(P.MATERIALS, '僵尸娘')
CARDS = os.path.join(MAT, 'cards')
GIFS = os.path.join(MAT, 'gif')
ICONS = os.path.join(MAT, 'icons')
for d in (MAT, CARDS, GIFS, ICONS):
    os.makedirs(d, exist_ok=True)

PROF = os.path.join(B.BASE, 'zombie_work', '_profile')
NPROC = 4

order = sorted(B.DATA.values(), key=lambda z: -int(z['id']))

def slot_dir():
    """线程内拿一个 profile 目录（用线程 id 取模即可）。"""
    import threading
    tid = threading.get_ident()
    d = os.path.join(PROF, str(abs(tid) % NPROC))
    os.makedirs(d, exist_ok=True)
    return d


_ORIG_RUN = B.subprocess.run


def run_edge(cmd, **kw):
    if cmd and str(cmd[0]).lower().endswith('msedge.exe'):
        cmd = list(cmd) + ['--user-data-dir=' + slot_dir(), '--no-sandbox']
        kw.setdefault('timeout', 240)
        r = _ORIG_RUN(cmd, **kw)
        if getattr(r, 'returncode', 0) not in (0, None):
            # Edge 偶尔会以 rc=21 退出且不出图，把 stderr 尾巴打出来便于排查
            print('  edge rc=%s %s' % (r.returncode,
                                       (r.stderr or b'')[-300:]), flush=True)
        return r
    return _ORIG_RUN(cmd, **kw)


B.subprocess.run = run_edge


def work(z):
    zid = int(z['id'])
    card = None
    for attempt in range(1, 4):
        try:
            card = B.build_card(z)
            break
        except Exception as e:  # noqa: BLE001
            print('  ! card fail %d/%d %s %s' % (attempt, 3, z['name'], repr(e)[:120]),
                  flush=True)
            time.sleep(2)
    if not card:
        raise RuntimeError('三次都没能渲染出卡片：%s' % z['name'])
    cname = 'zombie_%03d.png' % zid
    shutil.copyfile(card, os.path.join(CARDS, cname))
    shutil.copyfile(B.dl(z['icon'], 'icon_%s.png' % z['id']),
                    os.path.join(ICONS, '%03d.png' % zid))
    gname = ''
    if z['skills']:
        try:
            g = B.build_montage(z)
            if g:
                gname = 'zombie_%03d.gif' % zid
                shutil.copyfile(g, os.path.join(GIFS, gname))
        except Exception as e:  # noqa: BLE001
            print('  ! montage fail', z['name'], e, flush=True)
    return {
        'id': zid,
        'name': z['name'],
        'attack_mode': z.get('attack_mode') or '',
        'debut': z.get('debut') or '',
        'info': B.plain(z.get('info')),
        'card': 'cards/' + cname,
        'gif': ('gif/' + gname) if gname else '',
        'skills': [{'no': i, 'name': s['name'], 'desc': s['skill_desc'].strip(),
                    'gif': bool((s.get('display_img') or '').strip())}
                   for i, s in enumerate(z['skills'], 1)],
    }


if __name__ == '__main__':
    t0 = time.time()
    done = 0
    results = {}
    with ThreadPoolExecutor(max_workers=NPROC) as ex:
        futs = {ex.submit(work, z): z for z in order}
        for f in futs:
            z = futs[f]
            try:
                r = f.result()
                results[r['id']] = r
            except Exception as e:  # noqa: BLE001
                print('FAIL', z['name'], repr(e)[:200], flush=True)
            done += 1
            print('%2d/%d %-10s  (%.0fs)' % (done, len(order), z['name'],
                                             time.time() - t0), flush=True)

    index = [results[int(z['id'])] for z in order if int(z['id']) in results]
    json.dump(index, io.open(os.path.join(MAT, 'index.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump([{k: v for k, v in z.items() if k != '_list'} for z in order],
              io.open(os.path.join(MAT, 'zombie.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    nc = len(os.listdir(CARDS))
    ng = len(os.listdir(GIFS))
    ni = len(os.listdir(ICONS))
    sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(MAT) for f in fs)
    print('\nDONE cards=%d gif=%d icons=%d index=%d total=%.1fMB 用时%.0fs'
          % (nc, ng, ni, len(index), sz / 1048576, time.time() - t0))

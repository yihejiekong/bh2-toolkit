# -*- coding: utf-8 -*-
"""导出拟人（觉醒立绘）的表情差分。

解包依据：`menusv2_partner_allpartnerfigures_partner<PosterID>_*.unity3d` 里，
除了 1024×1024 的整幅立绘（Sprite 名 = FigureID），还带 5 张 256×256 的
表情差分 Sprite，名字形如 `1275_001` ~ `1275_005`。
partnerposterdata 的 `facelist` 列（例：`2;1;3;4;5;2;`）就是每句台词用第几号表情。

输出：<DIR>/表情差分/<FigureID>_001.png ...
运行环境：需要 UnityPy（Python313），不是 dsh 那个 python。
用法：python export_faces.py [PosterID ...]   # 不给参数=全部
"""

import glob
import os
import re
import sys

import UnityPy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

DIR = os.path.join(P.DATA, 'faces_src')
OUT = os.path.join(DIR, '表情差分')
PACKS = os.path.join(P.DATA, 'packs_dec', 'partner')
FACE = re.compile(r'^(\d+)_(\d{3})$')


def bundle_for(pid):
    pat = os.path.join(PACKS, '*partner%03d_*.unity3d' % pid)
    hit = glob.glob(pat)
    if not hit:  # 少数 bundle 的编号没有补零
        hit = glob.glob(os.path.join(PACKS, '*partner%d_*.unity3d' % pid))
    return hit[0] if hit else None


def export(pid):
    path = bundle_for(pid)
    if not path:
        return 0
    env = UnityPy.load(path)
    n = 0
    for o in env.objects:
        if int(o.type) != 28:  # Sprite
            continue
        d = o.read()
        m = FACE.match(getattr(d, 'm_Name', '') or '')
        if not m:
            continue
        dest = os.path.join(OUT, '%s_%s.png' % (m.group(1), m.group(2)))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            n += 1
            continue
        d.image.save(dest)
        n += 1
    return n


def main(pids):
    os.makedirs(OUT, exist_ok=True)
    if not pids:
        pids = []
        for p in glob.glob(os.path.join(PACKS, '*partner*_*.unity3d')):
            m = re.search(r'partner0*(\d+)_', os.path.basename(p))
            if m:
                pids.append(int(m.group(1)))
        pids = sorted(set(pids))
    total = 0
    for i, pid in enumerate(pids, 1):
        try:
            c = export(pid)
        except Exception as e:
            print('! %s: %s' % (pid, e))
            c = 0
        total += c
        if i % 50 == 0 or c == 0:
            print('  %d/%d  poster=%d faces=%d' % (i, len(pids), pid, c))
    print('done posters=%d faces=%d' % (len(pids), total))


if __name__ == '__main__':
    main([int(x) for x in sys.argv[1:]])

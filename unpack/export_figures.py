"""两阶段提取：先收集同名贴图的所有候选，再挑「完整立绘」。

优先 1024x1024（原生立绘规格），否则取面积最小的（避开 2048 的拆件图集）。
输出到 觉醒立绘\<FigureID>_<角色名>.png
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzzv2  # noqa: E402
gzzv2.install()
import UnityPy  # noqa: E402

ROOT = os.path.join(P.DATA, 'dev_bundles')
DEST = os.path.join(P.MATERIALS, '觉醒立绘')
LIST = os.path.join(P.MATERIALS, '觉醒立绘缺失清单.txt')


def names():
    """FigureID -> 角色名（可选：从清单文件里取，没有就用占位名）"""
    m = {}
    if not os.path.exists(LIST):
        return m
    for l in io.open(LIST, encoding='utf-8').read().splitlines()[7:]:
        nums = re.findall(r'\d{3,5}', l)
        if len(nums) >= 3:
            parts = re.split(r'\s{2,}', l.strip())
            m[nums[2]] = parts[-1].strip() if parts else ''
    return m


def main(ids):
    want = set(str(i) for i in ids)
    nm = names()
    cand = {}
    done = 0
    for dp, _, fs in os.walk(ROOT):
        for f in fs:
            if not f.endswith('.unity3d'):
                continue
            done += 1
            try:
                env = UnityPy.load(os.path.join(dp, f))
            except Exception:
                continue
            for o in env.objects:
                if o.type.name != 'Texture2D':
                    continue
                try:
                    d = o.read()
                except Exception:
                    continue
                n = str(d.m_Name)
                key = n[7:] if n.startswith('Figure_') else n
                if key not in want:
                    continue
                w, h = d.m_Width, d.m_Height
                if w < 512 or h < 512:
                    continue
                cand.setdefault(key, []).append((w * h, w, h, os.path.join(dp, f), n))
            if done % 500 == 0:
                print('... %d bundles, %d keys' % (done, len(cand)), flush=True)

    saved = 0
    for key, lst in sorted(cand.items()):
        # 优先 1024x1024，否则面积最小
        exact = [c for c in lst if c[1] == 1024 and c[2] == 1024]
        pick = exact[0] if exact else sorted(lst)[0]
        area, w, h, path, tex = pick
        env = UnityPy.load(path)
        for o in env.objects:
            if o.type.name != 'Texture2D':
                continue
            d = o.read()
            if str(d.m_Name) != tex:
                continue
            out = os.path.join(DEST, '%s_%s.png' % (key, nm.get(key) or '角色'))
            d.image.save(out)
            saved += 1
            print('OK %s %dx%d 候选%d -> %s' % (key, w, h, len(lst), os.path.basename(out)), flush=True)
            break
    print('DONE saved=%d keys=%d missing=%s' % (saved, len(cand), ' '.join(sorted(want - set(cand)))))


if __name__ == '__main__':
    main(sys.argv[1:])

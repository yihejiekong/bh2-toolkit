# -*- coding: utf-8 -*-
"""导出服装拆件图集：612 张整图 + 对应 .atlas 文本，并统计部件数。"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzzv2  # noqa: E402
gzzv2.install()
import UnityPy  # noqa: E402

SRC = os.path.join(P.DATA, 'upd', 'new184', 'Res', 'AssetBundles')
OUT = os.path.join(P.MATERIALS, '服装拆件图集')
ATL = os.path.join(OUT, '_atlas')
os.makedirs(OUT, exist_ok=True)
os.makedirs(ATL, exist_ok=True)


def count_regions(text):
    """libgdx atlas：每个 region 以空行分隔，首行是名字。"""
    n = 0
    for blk in text.split('\n\n'):
        lines = [l for l in blk.splitlines() if l.strip()]
        if not lines:
            continue
        head = lines[0].strip()
        if head and not head.startswith(('size:', 'format:', 'filter:', 'repeat:', 'pma:')):
            n += 1
    return n


fn = [f for f in os.listdir(SRC) if f.startswith('character_player_costumedata')][0]
path = os.path.join(SRC, fn)
env = UnityPy.load(path)

textures, atlases = {}, {}
for o in env.objects:
    try:
        if o.type.name == 'Texture2D':
            d = o.read()
            textures[str(d.m_Name)] = d
        elif o.type.name == 'TextAsset':
            d = o.read()
            nm = str(d.m_Name)
            if nm.endswith('.atlas'):
                s = d.m_Script
                if isinstance(s, bytes):
                    s = s.decode('utf-8', 'replace')
                atlases[nm[:-6]] = s
    except Exception:
        pass

print('贴图 %d，atlas %d' % (len(textures), len(atlases)))
meta = []
for cid, tex in textures.items():
    png = os.path.join(OUT, cid + '.png')
    tex.image.save(png)
    parts = 0
    at = atlases.get(cid)
    if at:
        parts = count_regions(at)
        with io.open(os.path.join(ATL, cid + '.atlas'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(at)
    meta.append({'id': cid, 'w': tex.m_Width, 'h': tex.m_Height,
                 'parts': parts, 'bytes': os.path.getsize(png)})

meta.sort(key=lambda m: (not m['id'].isdigit(), int(m['id']) if m['id'].isdigit() else 0))
with io.open(os.path.join(OUT, '_meta.json'), 'w', encoding='utf-8', newline='\n') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)

tot = sum(m['parts'] for m in meta)
print('导出 %d 张，部件合计 %d，最大图 %s' % (
    len(meta), tot,
    max(meta, key=lambda m: m['w'] * m['h'])['id']))
print('尺寸分布:', sorted({(m['w'], m['h']) for m in meta}, key=lambda t: -t[0] * t[1])[:5])
print('parts 最多的:', sorted(meta, key=lambda m: -m['parts'])[:5])

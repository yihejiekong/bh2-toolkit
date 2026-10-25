# -*- coding: utf-8 -*-
"""预渲染全部 58 张精英技能卡 + 抓 58 个动图，落到 materials/精英技能/{cards,gif}。"""

import io
import json
import os
import shutil
import sys

sys.path.insert(0, P.BUILD)
import build_skill_card as B  # noqa: E402
import paths as P

CARDS = os.path.join(B.MAT, 'cards')
os.makedirs(CARDS, exist_ok=True)

ok, fail = [], []
for sid in sorted(B.BY):
    try:
        png, gif = B.render(sid)
        dst = os.path.join(CARDS, '%02d_%s.png' % (sid, B.BY[sid]['name']))
        shutil.copyfile(png, dst)
        ok.append(dst)
    except Exception as e:  # noqa: BLE001
        fail.append((sid, repr(e)[:120]))

print('cards ok=%d fail=%d' % (len(ok), len(fail)))
for f in fail:
    print('  FAIL', f)
gifs = sorted(os.listdir(B.GIFDIR))
print('gifs=%d  ext gif=%d png=%d' % (len(gifs),
                                      sum(1 for g in gifs if g.endswith('.gif')),
                                      sum(1 for g in gifs if g.endswith('.png'))))
tot = sum(os.path.getsize(os.path.join(CARDS, f)) for f in os.listdir(CARDS))
tg = sum(os.path.getsize(os.path.join(B.GIFDIR, f)) for f in gifs)
print('cards %.1f MB   gifs %.1f MB' % (tot / 1048576, tg / 1048576))
io.open(os.path.join(B.MAT, 'index.json'), 'w', encoding='utf-8').write(
    json.dumps([{'id': int(x['id']), 'name': x['name'],
                 'card': '%02d_%s.png' % (int(x['id']), x['name']),
                 'gif': os.path.join('gif', [g for g in gifs
                                             if g.split('.')[0] == str(x['id'])][0])
                 if any(g.split('.')[0] == str(x['id']) for g in gifs) else None}
                for x in sorted(B.BY.values(), key=lambda y: int(y['id']))],
               ensure_ascii=False, indent=1))
print('index.json written')

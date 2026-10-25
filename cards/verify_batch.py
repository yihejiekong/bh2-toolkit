# -*- coding: utf-8 -*-
"""检查批量导出的 PNG 是否被窗口高度截断，以及 HTML 是否引用了缺失的图片。

用法：python _verify_batch.py            # 武器（装备卡）
     python _verify_batch.py 服装卡        # 服装
"""

import io
import os
import re
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardgen as C
import batch as Bt
import paths as P

kind = sys.argv[1] if len(sys.argv) > 1 else '装备卡'
if kind == '装备卡':
    rows, idx, build, root = C.ROWS, C.IDX, C.build, Bt.ROOT
elif kind == '徽章卡':
    import badge as Bd
    rows, idx, build, root = Bd.ROWS, Bd.IDX, Bd.build, os.path.join(os.path.dirname(Bt.ROOT), kind)
elif kind == '使魔卡':
    import pet as Pt
    rows, idx, build, root = Pt.ROWS, Pt.IDX, Pt.build, os.path.join(os.path.dirname(Bt.ROOT), kind)
else:
    import costume as Cz
    rows, idx, build, root = Cz.ROWS, Cz.IDX, Cz.build, os.path.join(os.path.dirname(Bt.ROOT), kind)

_, HTML_DIR, PNG_DIR, ASSET_DIR = Bt.dirs(root)

OUT = io.open(os.path.join(P.BUILD, '_verify_%s.txt') % kind, 'w', encoding='utf-8')
ids = Bt.select_ids(rows, idx)
clipped = []
missing = []
worst = []
noface = 0
for dn in ids:
    card = build(dn)
    if card['figure'] and not card.get('faces'):
        noface += 1
    base = Bt.fname(dn, card['name'])
    png = os.path.join(PNG_DIR, base + '.png')
    html_p = os.path.join(HTML_DIR, base + '.html')
    if not os.path.exists(html_p):
        missing.append(('html', base))
        continue
    if not os.path.exists(png):
        missing.append(('png', base))
        continue
    with Image.open(png) as im:
        w, h = im.size
    css_h = h / Bt.SCALE
    win = min(Bt.est_height(card) + 340, 7000)
    slack = win - css_h
    worst.append((slack, base, css_h, win))
    if slack < 12:
        clipped.append((base, css_h, win))
    t = io.open(html_p, encoding='utf-8').read()
    for m in re.findall(r'src="\.\./assets/([^"]+)"', t):
        if not os.path.exists(os.path.join(ASSET_DIR, m)):
            missing.append(('asset', base, m))

worst.sort()
OUT.write('cards=%d  clipped=%d  missing=%d  有立绘但无表情差分=%d\n'
          % (len(ids), len(clipped), len(missing), noface))
OUT.write('\n== 最紧的 15 张（像素余量）==\n')
for s, b, c, w in worst[:15]:
    OUT.write('slack=%.0f  %s  css_h=%.0f win=%d\n' % (s, b, c, w))
if clipped:
    OUT.write('\n== 疑似截断 ==\n')
    for b, c, w in clipped:
        OUT.write('%s  css_h=%.0f win=%d\n' % (b, c, w))
if missing:
    OUT.write('\n== 缺失 ==\n')
    for m in missing[:40]:
        OUT.write('%s\n' % (m,))
OUT.close()
print('done', kind)

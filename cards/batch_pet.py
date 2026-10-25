# -*- coding: utf-8 -*-
"""批量导出全部使魔图鉴卡：HTML -> 使魔卡/HTML，PNG -> 使魔卡/PNG。

用法与 batch.py 完全一致：
    python batch_pet.py
    python batch_pet.py --limit 20
    python batch_pet.py --ids 972,2853
"""

import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch as Bt
import pet as Pt
import paths as P

ROOT = os.path.join(P.MATERIALS, '装备卡', '使魔卡')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--ids', default='')
    ap.add_argument('--all', action='store_true', help='不做同名升星去重')
    ap.add_argument('--html-only', action='store_true')
    ap.add_argument('--png-only', action='store_true')
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()

    if a.ids:
        ids = [x.strip() for x in a.ids.split(',') if x.strip()]
    else:
        ids = Bt.select_ids(Pt.ROWS, Pt.IDX, a.all)
    if a.limit:
        ids = ids[:a.limit]
    Bt.run(ids, Pt.build, ROOT, a.workers, a.html_only, a.png_only)


if __name__ == '__main__':
    main()

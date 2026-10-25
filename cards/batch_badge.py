# -*- coding: utf-8 -*-
"""批量导出全部徽章图鉴卡：HTML -> 徽章卡/HTML，PNG -> 徽章卡/PNG。

用法与 batch.py 完全一致：
    python batch_badge.py
    python batch_badge.py --limit 20
    python batch_badge.py --ids 2853,2854
"""

import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch as Bt
import badge as Bd
import paths as P

ROOT = os.path.join(P.MATERIALS, '装备卡', '徽章卡')


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
        ids = Bt.select_ids(Bd.ROWS, Bd.IDX, a.all)
    if a.limit:
        ids = ids[:a.limit]
    Bt.run(ids, Bd.build, ROOT, a.workers, a.html_only, a.png_only)


if __name__ == '__main__':
    main()

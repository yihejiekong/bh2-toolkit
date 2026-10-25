# -*- coding: utf-8 -*-
"""在服务器上拉一次名片并渲染，打印结果（联调用）。"""
import json
import sys
import time
import urllib.request

import card

uid = int(sys.argv[1]) if len(sys.argv) > 1 else 12345678
t0 = time.time()
j = json.load(urllib.request.urlopen('http://127.0.0.1:8791/pull?uid=%d' % uid, timeout=30))
if not j.get('ok'):
    print('pull failed', j)
    sys.exit(1)
png, summ, det, n = card.render(bytes.fromhex(j['sum']), bytes.fromhex(j['det']), uid)
print('png:', png)
print('size:', __import__('os').path.getsize(png), 'bytes; careers', n, '%.2fs' % (time.time() - t0))
print('name:', summ['name'], '| guild:', summ['guild'], '| lv', summ['level'], '| vip', summ['vip'])
print('post', det['post'], 'emblem', det['emblem'], 'gold', det['gold'], 'roles', len(det['avatars']))
print('slots', {k: len(det[k]) for k in ('weapons', 'skills', 'costumes', 'pets', 'emblems')})

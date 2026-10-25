# -*- coding: utf-8 -*-
"""给 <root>/HTML 生成一个可搜索的目录页 <root>/index.html。

用法：python make_index.py            # 武器（装备卡）
     python make_index.py 服装卡       # 服装
"""

import io
import os
import sys
import paths as P

BASE = P.BUILD
TITLE = '崩坏学园2 装备图鉴卡'

name = sys.argv[1] if len(sys.argv) > 1 else '装备卡'
ROOT = os.path.join(BASE, name)
HD = os.path.join(ROOT, 'HTML')
if name != '装备卡':
    TITLE = '崩坏学园2 %s' % name

items = []
for fn in sorted(os.listdir(HD)):
    if not fn.endswith('.html'):
        continue
    base = fn[:-5]
    dn, _, nm = base.partition('_')
    items.append((int(dn) if dn.isdigit() else 10 ** 9, dn, nm, fn))
items.sort()

rows = ''.join(
    '<a class="row" href="HTML/%s" target="_blank" data-k="%s %s"><b>%s</b><span>%s</span></a>'
    % (fn, dn, nm.replace('"', ''), dn, nm)
    for _, dn, nm, fn in items)

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>%s · 目录</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f2f4f8;color:#222;padding:28px 32px 60px}
h1{font-size:26px;color:#f7941e;margin-bottom:6px}
p.sub{color:#666;font-size:14px;margin-bottom:18px}
input{width:100%%;max-width:520px;padding:10px 16px;font-size:16px;border:2px solid #cfe0ee;border-radius:10px;outline:none}
input:focus{border-color:#4aa8dd}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:18px}
.row{display:flex;gap:10px;align-items:baseline;padding:9px 14px;background:#fff;border-radius:9px;
  text-decoration:none;color:#333;font-size:15px;box-shadow:0 1px 3px rgba(0,0,0,.06);transition:.12s}
.row:hover{background:#eef7fd;transform:translateY(-1px);box-shadow:0 3px 9px rgba(50,120,180,.16)}
.row b{color:#4a90c2;font-weight:800;min-width:56px;font-size:14px}
.row span{color:#333}
.hide{display:none}
</style></head><body>
<h1>%s</h1>
<p class="sub">共 %d 张 · 点击打开对应的 HTML 卡（PNG 同名文件在 PNG/ 目录）</p>
<input id="q" placeholder="输入装备名或 ID 过滤…" autocomplete="off">
<div class="grid" id="g">%s</div>
<script>
var q=document.getElementById('q'),rows=[].slice.call(document.querySelectorAll('.row'));
q.addEventListener('input',function(){var v=q.value.trim().toLowerCase();
 rows.forEach(function(r){r.classList.toggle('hide', v && r.dataset.k.toLowerCase().indexOf(v)<0);});});
</script>
</body></html>""" % (TITLE, TITLE, len(items), rows)

with io.open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(HTML)
print('%s/index.html ->' % name, len(items), 'items')

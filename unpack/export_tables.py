"""把 data_all 里全部 TextAsset（配置表）导出成 .txt 到 tsv_all/。"""

import os
import sys
import time
from pathlib import Path

import UnityPy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

BUNDLE = os.path.join(P.DATA, 'packs_dec', 'data_all.unity3d')
DEST = P.TSV_DIR


def main():
    os.makedirs(DEST, exist_ok=True)
    t0 = time.time()
    env = UnityPy.load(BUNDLE)
    keys = sorted(env.container.keys())
    print(f"containers: {len(keys)}", flush=True)
    n = 0
    bytes_total = 0
    used = {}
    for i, k in enumerate(keys, 1):
        try:
            obj = env.container[k]
            if obj.type.name != "TextAsset":
                continue
            ta = obj.read()
            s = ta.m_Script
            raw = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
        except Exception as e:
            print(f"  FAIL {k}: {type(e).__name__}: {e}", flush=True)
            continue
        name = Path(k).name
        if name in used:
            used[name] += 1
            stem, ext = os.path.splitext(name)
            name = f"{stem}__{used[name]}{ext}"
        else:
            used[name] = 1
        with open(os.path.join(DEST, name), "wb") as f:
            f.write(raw)
        n += 1
        bytes_total += len(raw)
        if n % 1000 == 0:
            print(f"  {n} tables, {bytes_total/1048576:.1f} MB, {time.time()-t0:.0f}s", flush=True)
    print(f"done: {n} tables, {bytes_total/1048576:.1f} MB in {time.time()-t0:.0f}s -> {DEST}", flush=True)


if __name__ == "__main__":
    main()

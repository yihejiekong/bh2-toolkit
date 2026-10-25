"""批量导出 Res/AssetBundles 下所有 Texture2D 为 PNG（走 GGZV2 解密，无需先落地解密文件）。"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzzv2  # noqa: E402

gzzv2.install()

import UnityPy  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402


def export_textures(bundle_path, out_dir, log):
    env = UnityPy.load(str(bundle_path))
    n = 0
    for path, obj in env.container.items():
        if obj.type.name != "Texture2D":
            continue
        tex = obj.read()
        name = Path(path).stem                      # 例如 064 / 8948
        sub = Path(path).parts[-2] if len(Path(path).parts) > 1 else "misc"
        d = out_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        try:
            img = tex.image
        except Exception as e:
            log.append(f"  ! {name}: image() failed {type(e).__name__}: {e}")
            continue
        if img is None:
            log.append(f"  ! {name}: decoded image is None (fmt={getattr(tex,'m_TextureFormat','?')})")
            continue
        img.save(d / f"{name}.png")
        n += 1
    return n


def main(src_dir, png_dir):
    png_dir = Path(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)
    srcs = sorted(Path(src_dir).glob("*.unity3d"))
    print(f"{len(srcs)} bundles in {src_dir}")
    t0 = time.time()
    tot_png = 0
    for i, src in enumerate(srcs, 1):
        log = []
        try:
            n = export_textures(src, png_dir, log)
            tot_png += n
            print(f"[{i}/{len(srcs)}] {src.name[:70]:70s} {n:4d} tex")
        except Exception as e:
            print(f"[{i}/{len(srcs)}] {src.name[:70]:70s} FAIL {type(e).__name__}: {e}")
        for line in log[:3]:
            print(line)
    print(f"\ndone: {tot_png} textures, {time.time()-t0:.1f}s -> {png_dir}")


if __name__ == "__main__":
    main(*(sys.argv[1:3] if len(sys.argv) >= 3 else [
        os.path.join(P.DATA, 'dev_bundles', 'AssetBundles'),
        os.path.join(P.DATA, 'textures'),
    ]))

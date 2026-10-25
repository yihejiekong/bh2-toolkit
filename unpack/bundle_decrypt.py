"""Decrypt bh2 data_all.unity3d (AES-CBC) and export TextAsset config tables.

Cipher chain reverse-engineered locally:
  stage 1 (whole file): AES-256-CBC, key/iv from hg2_data_extractor.config
  stage 2 (per UnityFS compression block, v>=11.7): AES-CBC key=b"LPC@a*&^b19b61l/", iv=16*NUL  -> LZ4HC block
"""

import sys, collections, os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

RAW = Path(os.path.join(P.DATA, 'raw', 'data_all.unity3d'))
DEC = Path(os.path.join(P.DATA, 'raw', 'data_all_dec.unity3d'))
OUT = Path(os.path.join(P.DATA, 'tsv'))

AES_KEY = bytes.fromhex(
    "89 83 83 10 3a 0f d9 52 ea 9f 3c 14 50 9c 56 92 "
    "a4 6e ab bf 46 1a 54 ac b2 7e 82 a7 99 6d 35 b8"
)
AES_IV = bytes.fromhex("81 e0 ca d4 a5 df 51 da 37 ba 49 ee cc 8a 4f fe")

VERSION = "13.4.1"


def stage1():
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    data = RAW.read_bytes()
    print(f"[1] read {len(data)} bytes, entropy-encrypted={data[:4] != b'UnityF'}")
    dec = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(data)
    try:
        dec = unpad(dec, AES.block_size)
    except ValueError as e:
        print(f"    unpad failed ({e}); keeping raw (check if game pads differently)")
    DEC.write_bytes(dec)
    print(f"[1] wrote {DEC.name}: {len(dec)} bytes, magic={dec[:8]!r}")
    return dec


def stage2():
    import lz4.block
    import UnityPy
    from UnityPy.enums import CompressionFlags
    from UnityPy.helpers import CompressionHelper
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    KEY2 = b"LPC@a*&^b19b61l/"
    IV2 = b"\x00" * 16

    def patched(data: bytes, uncompressed_size: int) -> bytes:
        try:
            data = unpad(AES.new(KEY2, AES.MODE_CBC, IV2).decrypt(data), AES.block_size)
        except ValueError:
            pass
        return lz4.block.decompress(data, uncompressed_size=uncompressed_size)

    old = CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZ4HC]
    CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZ4HC] = patched
    try:
        env = UnityPy.load(str(DEC))
    finally:
        CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZ4HC] = old
    return env


def main():
    stage1()
    env = stage2()
    print(f"[2] objects={len(env.objects)} containers={len(env.container)}")
    c = collections.Counter(o.type.name for o in env.objects)
    for k, v in c.most_common(15):
        print(f"    {k}: {v}")

    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for asset, reader in env.container.items():
        names.append((Path(asset).stem.lower(), Path(asset).name, reader))
    print(f"[3] containers: {len(names)}")

    wanted = {
        "weapondatav3", "costumedatav2", "passiveskilldatav3",
        "specialattributedatav2", "petdata", "petskilldata",
    }
    found = {}
    for stem, full, reader in names:
        if stem in wanted:
            found[stem] = (full, reader)

    print(f"[3] matched {len(found)}/{len(wanted)} item tables: {sorted(found)}")
    if not found:
        lst = OUT / "container_names.txt"
        lst.write_text("\n".join(sorted(n[0] for n in names)), encoding="utf-8")
        print(f"    wrote all container stems -> {lst}")
        print("    sample:", [n[0] for n in names[:40]])
        return

    for stem, (full, reader) in sorted(found.items()):
        obj = reader.read()
        data = obj.m_Script.encode("utf-8", "surrogateescape")
        out = OUT / f"{obj.m_Name}.tsv"
        out.write_bytes(data)
        head = data[:300].decode("utf-8", "replace").replace("\n", "\\n")
        print(f"    {obj.m_Name}.tsv  {len(data)} bytes  head: {head[:200]}")


main()

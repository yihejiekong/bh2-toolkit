"""
崩坏学园2 (GGZ / HSoDv2) AssetBundle 解密器

块加密方案 = "GGZV2"（源自 Modder4869/StudioDev, AssetStudio/BundleFile.cs:934-977）
  key = 72 E6 5D AC A5 B7 9B 2A 42 8E 7F 64 C1 A4 0A 9E   (AES-128)
  block 明文 = LZ4( AES-CBC( key, iv, ct = block[:-16] ) )
  iv[j]    = block[-16+j] ^ (OFF_1643478[j] & 0xFF)
"""

import io
import struct
import sys
from pathlib import Path

import lz4.block
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

KEY_V2 = bytes([0x72, 0xE6, 0x5D, 0xAC, 0xA5, 0xB7, 0x9B, 0x2A,
                0x42, 0x8E, 0x7F, 0x64, 0xC1, 0xA4, 0x0A, 0x9E])

OFF_1643478 = [
    0x8F038C8C, 0xF859A1A1, 0x80098989, 0x171A0D0D,
    0xDA65BFBF, 0x31D7E6E6, 0xC6844242, 0xB8D06868,
    0xC3824141, 0xB0299999, 0x775A2D2D, 0x111E0F0F,
    0xCB7BB0B0, 0xFCA85454, 0xD66DBBBB, 0x3A2C1616,
]


def read_cstr(f):
    out = b""
    while True:
        c = f.read(1)
        if c in (b"\x00", b""):
            return out
        out += c


def parse_header(d):
    f = io.BytesIO(d)
    sig = read_cstr(f)
    if sig != b"UnityFS":
        raise ValueError(f"not a UnityFS bundle (sig={sig!r})")
    version = struct.unpack(">I", f.read(4))[0]
    unity = read_cstr(f)
    revision = read_cstr(f)
    size, csize, usize, flags = struct.unpack(">qIII", f.read(20))
    hdr_end = f.tell()
    bi_start = (hdr_end + 15) // 16 * 16
    storage = flags & 0x3F
    info = lz4.block.decompress(d[bi_start:bi_start + csize], uncompressed_size=usize) \
        if storage & 0x3F == 3 or storage & 0x3F == 2 else d[bi_start:bi_start + usize]
    p = 0
    data_hash = info[p:p + 16]; p += 16
    n = struct.unpack(">I", info[p:p + 4])[0]; p += 4
    blocks = []
    for _ in range(n):
        u, c, fl = struct.unpack(">IIH", info[p:p + 10]); p += 10
        blocks.append((u, c, fl))
    dir_info = info[p:]
    return dict(version=version, unity=unity, revision=revision, size=size,
                csize=csize, usize=usize, flags=flags, hdr_end=hdr_end,
                bi_start=bi_start, data_hash=data_hash, blocks=blocks,
                dir_info=dir_info, data_start=bi_start + csize)


def decrypt_block(blob, expected):
    if len(blob) < 32 or (len(blob) - 16) % 16 != 0:
        raise ValueError(f"block size {len(blob)} not compatible with GGZV2")
    tail = blob[-16:]
    iv = bytes(tail[j] ^ (OFF_1643478[j] & 0xFF) for j in range(16))
    plain = unpad(AES.new(KEY_V2, AES.MODE_CBC, iv).decrypt(blob[:-16]), 16)
    if len(plain) < 4:
        raise ValueError("too short after AES")
    try:
        out = lz4.block.decompress(plain, uncompressed_size=expected)
    except Exception:
        out = lz4.block.decompress(plain)
    if len(out) != expected:
        raise ValueError(f"lz4 wrote {len(out)} but expected {expected}")
    return out


def decrypt_bundle(path):
    d = Path(path).read_bytes()
    h = parse_header(d)

    off = h["data_start"]
    chunks = []
    for i, (u, c, fl) in enumerate(h["blocks"]):
        blob = d[off:off + c]
        off += c
        if len(blob) != c:
            raise ValueError(f"block {i}: short read {len(blob)}/{c}")
        if fl & 0x3F == 0:                       # uncompressed
            chunks.append(blob[:u])
        elif fl & 0x3F in (2, 3):                # LZ4 / LZ4HC
            chunks.append(decrypt_block(blob, u))
        else:
            raise ValueError(f"block {i}: unsupported compression flags {fl}")
    data = b"".join(chunks)

    # 重新打包成标准未压缩 UnityFS（flags=0x40，块压缩类型 0）
    total = len(data)
    new_info = (b"\x00" * 16
                + struct.pack(">I", 1)
                + struct.pack(">IIH", total, total, 0)
                + h["dir_info"])
    unity = h["unity"]
    revision = h["revision"]
    header_len = 8 + 4 + (len(unity) + 1) + (len(revision) + 1) + 8 + 4 + 4 + 4
    pad = (-header_len) % 16
    head_wo_size = (b"UnityFS\x00"
                    + struct.pack(">I", h["version"])
                    + unity + b"\x00"
                    + revision + b"\x00")
    total_size = header_len + pad + len(new_info) + total
    out = (head_wo_size
           + struct.pack(">q", total_size)
           + struct.pack(">I", len(new_info))     # compressed blocksInfo size
           + struct.pack(">I", len(new_info))     # uncompressed blocksInfo size
           + struct.pack(">I", 0x40)              # BlocksAndDirectoryInfoCombined, no compression
           + b"\x00" * pad
           + new_info
           + data)
    assert len(out) == total_size, (len(out), total_size)
    return out


def main(argv):
    dst_dir = Path(os.path.join(P.DATA, 'packs_dec'))
    dst_dir.mkdir(parents=True, exist_ok=True)
    srcs = []
    for a in argv:
        p = Path(a)
        if p.is_dir():
            srcs.extend(sorted(p.glob("*.unity3d")))
        else:
            srcs.append(p)
    ok = bad = 0
    for src in srcs:
        try:
            blob = decrypt_bundle(src)
            (dst_dir / src.name).write_bytes(blob)
            ok += 1
            print(f"OK   {src.name}  -> {len(blob)} B")
        except Exception as e:
            bad += 1
            print(f"FAIL {src.name}: {type(e).__name__}: {e}")
    print(f"\ndone: ok={ok} fail={bad} -> {dst_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])

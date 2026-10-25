"""GGZV2 解密器：让 UnityPy 能直接打开崩坏学园2 13.4.x 的 AssetBundle。

13.4 之后数据块不再是裸 LZ4，而是「AES-CBC 密文 + 16 字节尾」，
IV 由尾部 16 字节与固定表 TBL 异或得到。这里把处理函数挂进
UnityPy 的 DECOMPRESSION_MAP，后续 UnityPy.load() 就无需关心格式。

算法来源：Modder4869 / StudioDev 的 BundleFile.cs 与社区整理，
本项目仅做 Python 侧适配。
"""
import lz4.block
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

KEY_V2 = bytes.fromhex("72e65daca5b79b2a428e7f64c1a40a9e")
OFF_1643478 = [0x8F038C8C,0xF859A1A1,0x80098989,0x171A0D0D,0xDA65BFBF,0x31D7E6E6,0xC6844242,0xB8D06868,
               0xC3824141,0xB0299999,0x775A2D2D,0x111E0F0F,0xCB7BB0B0,0xFCA85454,0xD66DBBBB,0x3A2C1616]
TBL = bytes(x & 0xFF for x in OFF_1643478)


def gzzv2_block_to_plain(blob):
    """blob = ciphertext + 16-byte tail; returns LZ4 stream bytes."""
    blob = bytes(blob)
    tail = blob[-16:]
    iv = bytes(tail[j] ^ TBL[j] for j in range(16))
    pt = AES.new(KEY_V2, AES.MODE_CBC, iv).decrypt(blob[:-16])
    try:
        pt = unpad(pt, 16)
    except ValueError:
        pass
    return pt


def gzzv2_decompress(data, uncompressed_size):
    """UnityPy hook: blocksInfo is plain LZ4; data blocks are GGZV2."""
    data = bytes(data)
    if (len(data) - 16) % 16 == 0 and len(data) >= 32:
        try:
            return lz4.block.decompress(gzzv2_block_to_plain(data), uncompressed_size=uncompressed_size)
        except Exception:
            pass
    return lz4.block.decompress(data, uncompressed_size=uncompressed_size)


def install():
    from UnityPy.enums import CompressionFlags
    from UnityPy.helpers import CompressionHelper
    CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZ4] = gzzv2_decompress
    CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZ4HC] = gzzv2_decompress
    return CompressionHelper.DECOMPRESSION_MAP

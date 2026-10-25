"""Extract the in-APK AssetBundles from the 13.4.8 APK and classify them (plain vs encrypted)."""

import zipfile, os, re, struct, math, collections, lz4.block as lb
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402

APK = os.path.join(P.DATA, 'apk', 'bh2.apk')
OUT = os.path.join(P.DATA, 'apk1348')
os.makedirs(OUT, exist_ok=True)


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def cstr(d, i):
    j = d.index(b'\x00', i)
    return d[i:j].decode('utf-8', 'ignore'), j + 1


def analyse(path, data):
    tag = os.path.basename(path)
    if data[:8] != b'UnityFS\x00':
        return '%s: NOT UnityFS (magic %s, entropy %.3f)' % (tag[:60], data[:8].hex(), entropy(data[:4096]))
    i = 8
    ver = struct.unpack_from('>I', data, i)[0]; i += 4
    uver, i = cstr(data, i)
    rev, i = cstr(data, i)
    size = struct.unpack_from('>q', data, i)[0]; i += 8
    ci = struct.unpack_from('>I', data, i)[0]; i += 4
    ui = struct.unpack_from('>I', data, i)[0]; i += 4
    flags = struct.unpack_from('>I', data, i)[0]; i += 4
    if ver >= 7:
        i += 1
    dataoff = (i + 15) // 16 * 16
    bi = data[i:i + ci]
    status = 'blocksInfo'
    try:
        dec = lb.decompress(bi, uncompressed_size=ui)
        status = 'PLAIN blocksInfo OK (%d blocks)' % struct.unpack_from('>I', dec, 16)[0]
        cnt = struct.unpack_from('>I', dec, 16)[0]
        off = 20
        blocks = []
        for _ in range(cnt):
            u, c, f = struct.unpack_from('>IIH', dec, off); off += 10
            blocks.append((u, c, f))
        b0 = data[dataoff:dataoff + blocks[0][1]]
        ok = False
        for skip in (0, 4, 8):
            try:
                out = lb.decompress(b0[skip:], uncompressed_size=blocks[0][0])
                ok = True
                break
            except Exception:
                pass
        status += '; block0 %s (flags=%d, ent %.3f)' % ('PLAIN LZ4 OK' if ok else 'STILL ENCRYPTED', blocks[0][2], entropy(b0))
    except Exception as e:
        status = 'blocksInfo ENCRYPTED (%s)' % str(e)[:40]
    return '%s: ver=%d rev=%s csize=%d usize=%d flags=0x%x | %s' % (tag[:58], ver, rev, ci, ui, flags, status)


z = zipfile.ZipFile(APK)
names = [n for n in z.namelist() if n.startswith('assets/Res/') and z.getinfo(n).file_size > 0]
print('extract %d files' % len(names))
rows = []
for n in names:
    fn = os.path.join(OUT, os.path.basename(n))
    data = z.read(n)
    if not os.path.exists(fn):
        open(fn, 'wb').write(data)
    rows.append(analyse(fn, data))
open(os.path.join(OUT, '_report.txt'), 'w', encoding='utf-8').write('\n'.join(rows))
for r in rows:
    print(r)

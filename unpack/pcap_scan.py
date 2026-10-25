#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BH2 抓包分析器 —— 不需要 Wireshark，纯 Python 读 pcap / pcapng。

用途：拿到手机（PCAPdroid）或模拟器（Wireshark/tcpdump）录下的 pcap 后，
一条命令把「崩坏学园2 到底连了谁、发了什么字节」列出来。

用法：
    python pcap_scan.py capture.pcap                 # 概览：所有 TCP 连接
    python pcap_scan.py capture.pcap --port 15004    # 只看某端口
    python pcap_scan.py capture.pcap --dump 15004    # 把该端口的流按顺序打到磁盘
    python pcap_scan.py capture.pcap --hex 15004     # 直接打印前 40 个包的首字节

输出：
    每个连接一行：src:port -> dst:port  包数/字节数
    --dump 会在 pcap 同目录生成 stream_<n>_<dir>.bin（按 seq 重排后的裸字节）
    拿 stream_*.bin 再去喂 idcard_decode.py 就能看 protobuf 字段。
"""

import os


import argparse
import os
import struct
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cards'))  # 复用 cards/paths.py
import paths as P  # noqa: E402


# ────────────────────────── pcap / pcapng 读取 ──────────────────────────

def read_pcap(path):
    """返回 [(ts, src_ip, sport, dst_ip, dport, payload), ...]"""
    with open(path, "rb") as f:
        head = f.read(4)
        f.seek(0)
        if head == b"\x0a\x0d\x0d\x0a":
            return read_pcapng(f)
        return read_pcap_classic(f)


def read_pcap_classic(f):
    magic = f.read(4)
    if magic == b"\xd4\xc3\xb2\xa1":
        endian, nano = "<", False
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian, nano = ">", False
    elif magic == b"\x4d\x3c\xb2\xa1":
        endian, nano = "<", True
    elif magic == b"\xa1\xb2\x3c\x4d":
        endian, nano = ">", True
    else:
        raise SystemExit("不是 pcap 文件（magic=%r）" % magic)
    vmaj, vmin, tz, sf, snap, link = struct.unpack(endian + "HHiIII", f.read(20))
    pkts = []
    while True:
        hdr = f.read(16)
        if len(hdr) < 16:
            break
        ts_s, ts_u, incl, orig = struct.unpack(endian + "IIII", f.read(16) if False else hdr)
        data = f.read(incl)
        if len(data) < incl:
            break
        ts = ts_s + (ts_u / 1e9 if nano else ts_u / 1e6)
        p = parse_frame(data, link)
        if p:
            pkts.append((ts,) + p)
    return pkts


def read_pcapng(f):
    pkts = []
    links = []
    endian = "<"
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        if hdr[:4] == b"\x0a\x0d\x0d\x0a":
            bom = f.read(4)
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            f.read(16)  # version + section length
            continue
        btype = struct.unpack(endian + "I", hdr[:4])[0]
        blen = struct.unpack(endian + "I", hdr[4:8])[0]
        if blen < 12:
            break
        body = f.read(blen - 8)
        if len(body) < blen - 8:
            break
        if btype == 1:  # Interface Description
            link = struct.unpack(endian + "H", body[0:2])[0]
            links.append(link)
        elif btype == 6:  # Enhanced Packet
            iface, tsh, tsl, cap, orig = struct.unpack(endian + "IIIII", body[0:20])
            data = body[20:20 + cap]
            ts = ((tsh << 32) | tsl) / 1e6
            link = links[iface] if iface < len(links) else 1
            p = parse_frame(data, link)
            if p:
                pkts.append((ts,) + p)
        elif btype == 3:  # Simple Packet
            data = body[4:]
            link = links[0] if links else 1
            p = parse_frame(data, link)
            if p:
                pkts.append((0,) + p)
    return pkts


def parse_frame(data, link):
    if link == 1:  # Ethernet
        if len(data) < 14:
            return None
        et = struct.unpack(">H", data[12:14])[0]
        off = 14
        if et == 0x8100:
            off += 4
            et = struct.unpack(">H", data[16:18])[0]
        if et == 0x0800:
            return parse_ipv4(data[off:])
        if et == 0x86DD:
            return parse_ipv6(data[off:])
        return None
    if link == 101:  # Raw IP
        return parse_ipv4(data) if data[:1] and data[0] >> 4 == 4 else parse_ipv6(data)
    if link == 113:  # Linux SLL
        if len(data) < 16:
            return None
        return parse_ipv4(data[16:])
    return None


def parse_ipv4(data):
    if len(data) < 20:
        return None
    ihl = (data[0] & 0x0F) * 4
    proto = data[9]
    if proto != 6:
        return None
    src = ".".join(str(b) for b in data[12:16])
    dst = ".".join(str(b) for b in data[16:20])
    return parse_tcp(data[ihl:], src, dst)


def parse_ipv6(data):
    if len(data) < 40:
        return None
    if data[6] != 6:
        return None
    src = ":".join("%02x%02x" % (data[i], data[i + 1]) for i in range(8, 24, 2))
    dst = ":".join("%02x%02x" % (data[i], data[i + 1]) for i in range(24, 40, 2))
    return parse_tcp(data[40:], src, dst)


def parse_tcp(data, src, dst):
    if len(data) < 20:
        return None
    sport, dport, seq = struct.unpack(">HHI", data[0:8])
    off = (data[12] >> 4) * 4
    flags = data[13]
    payload = data[off:]
    return (src, sport, dst, dport, seq, flags, payload)


# ────────────────────────── 分析 ──────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--dump", type=int, default=None, help="把该端口的流写成文件")
    ap.add_argument("--hex", type=int, default=None, help="打印该端口前 40 个包的前 96 字节")
    ap.add_argument("--host", default=None, help="只看包含该子串的地址")
    args = ap.parse_args()

    pkts = read_pcap(args.pcap)
    print("packets: %d" % len(pkts))

    conns = {}
    for ts, src, sport, dst, dport, seq, flags, payload in pkts:
        if args.port and args.port not in (sport, dport):
            continue
        if args.host and args.host not in (src + dst):
            continue
        if not payload:
            continue
        key = (src, sport, dst, dport)
        c = conns.setdefault(key, {"n": 0, "bytes": 0, "segs": []})
        c["n"] += 1
        c["bytes"] += len(payload)
        c["segs"].append((seq, payload))

    print("\n== TCP 连接（有载荷的）==")
    for (src, sport, dst, dport), c in sorted(conns.items(), key=lambda kv: -kv[1]["bytes"]):
        print("  %-16s:%-5d -> %-16s:%-5d  pkts=%-4d bytes=%d"
              % (src, sport, dst, dport, c["n"], c["bytes"]))

    if args.dump:
        outdir = os.path.dirname(os.path.abspath(args.pcap))
        k = 0
        for (src, sport, dst, dport), c in conns.items():
            if args.dump not in (sport, dport):
                continue
            segs = sorted(c["segs"], key=lambda x: x[0])
            blob = bytearray()
            last_end = -1
            for seq, pay in segs:
                if last_end >= 0 and seq < last_end:
                    pay = pay[last_end - seq:]
                    seq = last_end
                    if not pay:
                        continue
                blob += pay
                last_end = seq + len(pay)
            name = os.path.join(outdir, "stream_%d_%s_%d_to_%s_%d.bin" % (k, src, sport, dst, dport))
            with open(name, "wb") as f:
                f.write(blob)
            print("wrote %s (%d bytes)" % (name, len(blob)))
            k += 1

    if args.hex:
        shown = 0
        for ts, src, sport, dst, dport, seq, flags, payload in pkts:
            if args.hex not in (sport, dport) or not payload:
                continue
            print("\n[%d] %s:%d -> %s:%d  len=%d flags=0x%02x" % (shown, src, sport, dst, dport, len(payload), flags))
            chunk = payload[:96]
            print("  " + chunk.hex(" "))
            shown += 1
            if shown >= 40:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())

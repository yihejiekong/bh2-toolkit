# -*- coding: utf-8 -*-
"""0x002a（摘要）与 0x02b3（详情）载荷解析。"""
import time

LIST_NAMES = ['weapons', 'skills', 'costumes', 'pets', 'emblems']


def parse_summary(pl):
    d = {}
    d['own'] = int.from_bytes(pl[0:4], 'big')
    d['uid'] = int.from_bytes(pl[6:10], 'big')
    d['level'] = int.from_bytes(pl[10:12], 'big')
    d['vip'] = pl[12]
    d['avatar'] = int.from_bytes(pl[35:37], 'big')   # playericondata.id
    d['server_ts'] = int.from_bytes(pl[13:17], 'big')
    # 字符串：u16 大端长度 + UTF-8，顺序 = [公会, 昵称]
    strs, i = [], 40
    while i + 2 < len(pl) and len(strs) < 4:
        ln = int.from_bytes(pl[i:i + 2], 'big')
        if 1 <= ln <= 64 and i + 2 + ln <= len(pl):
            try:
                s = pl[i + 2:i + 2 + ln].decode('utf-8')
            except UnicodeDecodeError:
                s = None
            if s and s.isprintable():
                strs.append(s)
                i += 2 + ln
                continue
        i += 1
    if len(strs) >= 2:
        d['guild'], d['name'] = strs[0], strs[1]
    elif strs:
        d['guild'], d['name'] = '', strs[0]
    else:
        d['guild'], d['name'] = '', ''
    return d


def _find_roles(pl):
    """定位「角色列表」：count 字节 + count 个 u32 大端（整包末尾 20 字节是计数区）。

    返回 ids 列表；找不到返回 []。
    注意：离线的玩家只会收到**精简版** 0x02b3（只有 159 字节、5 个展示列表全为空、
    count 落在偏移 34），所以不能用「偏移必须 >100」这类假设。
    """
    best = []
    for c in range(1, 80):
        off = len(pl) - 21 - 4 * c
        if off < 8 or off + 1 + 4 * c > len(pl):
            continue
        if pl[off] != c:
            continue
        vals = [int.from_bytes(pl[off + 1 + 4 * i:off + 5 + 4 * i], 'big') for i in range(c)]
        if all(1000 < v < 99999 for v in vals):
            if len(vals) > len(best):
                best = vals
    return best


def parse_detail(pl):
    """0x02b3：magic(ea60) + pad + uid + playedTime + 1 + 5 个展示列表(u8 count + u16 项)
    + 金/银/铜成就数 + 其他 + 角色列表(u8 count + u32) + … + 末尾 5 个 u32
    （post / emblem / hide1 / hide2 / hide3）。"""
    d = {}
    d['target'] = int.from_bytes(pl[4:8], 'big')
    d['played'] = int.from_bytes(pl[8:12], 'big')
    o = 16
    for nm in LIST_NAMES:
        c = pl[o]
        o += 1
        d[nm] = [int.from_bytes(pl[o + 2 * i:o + 2 * i + 2], 'big') for i in range(c)]
        o += 2 * c
    d['gold'] = int.from_bytes(pl[o:o + 4], 'big')
    d['silver'] = int.from_bytes(pl[o + 4:o + 8], 'big')
    d['copper'] = int.from_bytes(pl[o + 8:o + 12], 'big')
    d['avatars'] = _find_roles(pl)
    d['post'] = int.from_bytes(pl[-20:-16], 'big')
    d['emblem'] = int.from_bytes(pl[-16:-12], 'big')
    d['hide1'] = int.from_bytes(pl[-12:-8], 'big')
    d['hide2'] = int.from_bytes(pl[-8:-4], 'big')
    d['hide3'] = int.from_bytes(pl[-4:], 'big')
    return d


def _career_region(pl):
    """返回 (records_start, region_end) —— 履历区严格夹在「成就数」与「角色列表计数」之间。

    布局：… 金/银/铜(u32×3) | 履历数(u8) + 3 字节 0 | N 条履历 | 角色数(u8) + 角色u32… | 尾部 5×u32
    """
    o = 16
    for _ in LIST_NAMES:
        c = pl[o]
        o += 1 + 2 * c
    start = o + 12 + 4                    # 跳过 3 个成就数 + 「count + 3 pad」
    roles = _find_roles(pl)
    if not roles:
        return start, None
    end = len(pl) - 21 - 4 * len(roles)   # 角色数那一个字节的位置
    return start, end


def parse_careers(pl, cd):
    """尾部 _careerInfos：count(u8) + 3 pad，然后 N 条 23/27 字节记录。

    记录：ct(u8) + ts(u32) + flag(u8) + para1(u32) + val(u32) + …（23 或 27 字节）。
    用 DP 在「恰好消费完履历区」的前提下选每条的长度，避免老的盲扫误命中。
    """
    cd = cd or {}
    limit = time.time() + 86400
    p0, end = _career_region(pl)
    if end is None or end <= p0 or end > len(pl):
        return []
    cnt = pl[p0 - 4]
    if not (0 < cnt <= 200):
        return []

    def valid(p):
        if p + 14 > end:
            return False
        ct = pl[p]
        ts = int.from_bytes(pl[p + 1:p + 5], 'big')
        return 1 <= ct <= 40 and 1350000000 < ts <= limit

    # reach[i] = 记录 i 起始位置集合（记录长度 20~28 字节，随附属字段变化）
    STEPS = tuple(range(20, 29))
    reach = [set() for _ in range(cnt + 1)]
    reach[0].add(p0)
    for i in range(cnt):
        for p in reach[i]:
            if not valid(p):
                continue
            for step in STEPS:
                q = p + step
                if q > end:
                    continue
                if q == end or valid(q):
                    reach[i + 1].add(q)
    if end not in reach[cnt]:
        # 数量对不上：退化成「尽量多解析」
        for i in range(cnt, -1, -1):
            if end in reach[i]:
                cnt = i
                break
        else:
            return []

    out, p = [], p0
    for i in range(cnt):
        step = 23
        for s in STEPS:
            if (p + s) in reach[i + 1]:
                step = s
                break
        ct = pl[p]
        ts = int.from_bytes(pl[p + 1:p + 5], 'big')
        para1 = int.from_bytes(pl[p + 6:p + 10], 'big')
        val = int.from_bytes(pl[p + 10:p + 14], 'big')
        f = 4 if step >= 27 else 0
        tail = pl[p + 14 + f:p + 23 + f]
        displayed = len(tail) > 1 and (tail[1] == 1 or (len(tail) >= 6 and tail[4] == 1 and tail[5] == 1))
        if len(tail) >= 6 and tail[4] == 1 and tail[5] == 1:
            val = int.from_bytes(pl[p + 14:p + 18], 'big')
        tpl = cd.get('%d,%d' % (ct, para1))
        if tpl:
            txt = tpl.replace('#1', str(val)).replace('#2', str(val))
        else:
            txt = '未知履历（类型%d / 编号%d / %d）' % (ct, para1, val)
        out.append({'ts': ts, 'text': txt, 'displayed': displayed})
        p += step
    out.sort(key=lambda c: -c['ts'])
    return out

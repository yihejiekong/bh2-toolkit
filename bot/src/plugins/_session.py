# -*- coding: utf-8 -*-
"""共享会话存储：装备查询与立绘查询共用一个会话表，保证同一时刻只有一个活跃会话。

key = (group_id, user_id) -> {"type": "equip"|"illust", "items": [...], "page": 0, "expire": ts}
"""
import time

_sessions = {}


def set_session(key, type_, items, ttl):
    _sessions[key] = {"type": type_, "items": items, "page": 0, "expire": time.time() + ttl}


def get_session(key, type_):
    sess = _sessions.get(key)
    if not sess or time.time() > sess["expire"]:
        return None
    if sess["type"] != type_:
        return None
    return sess


def touch(sess, ttl):
    sess["expire"] = time.time() + ttl


def clear(key):
    _sessions.pop(key, None)

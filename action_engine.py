#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 动作解释器（数据驱动）

桌宠和工作台共用一份 `actions.json`。每个动作是「关键帧数组 + 缓动」，
解释器只做插值，不再有任何硬编码公式；工作台编辑完发布后，桌宠直接用
下发的关键帧覆盖本地默认值，断网时回落到 actions.json。

关键帧格式（7 个数）：
    [t, dx, dy, rot, sx, sy, flip]
    t    0..1      动作进度
    dx/dy          位移（桌宠逻辑像素）
    rot            旋转角度（度）
    sx/sy          横纵缩放
    flip           0/1 水平翻转；def.flip_random=true 时由播放方随机决定
"""

import json
import math
import re

KEY_RE = re.compile(r"^[a-z0-9_]{1,32}$")
LIMITS = {
    "dx": (-200.0, 200.0),
    "dy": (-200.0, 200.0),
    "rot": (-90.0, 90.0),
    "sx": (0.2, 2.5),
    "sy": (0.2, 2.5),
}
MAX_ACTIONS = 24
MAX_KEYS = 64


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(n):
        return default
    return max(lo, min(hi, n))


def normalize_defs(raw):
    """把任何来源（文件 / 工作台下发）的动作数据收敛成安全结构。"""
    items = raw.get("actions") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out = []
    seen = set()
    for a in items[:MAX_ACTIONS]:
        if not isinstance(a, dict):
            continue
        key = str(a.get("key") or "").strip().lower()
        if not KEY_RE.fullmatch(key) or key in seen:
            continue
        seen.add(key)
        keys = a.get("keys")
        if not isinstance(keys, list) or len(keys) < 2:
            continue
        clean = []
        last_t = -1.0
        for row in keys[:MAX_KEYS]:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            t = _num(row[0], 0.0, 1.0, -1.0)
            if t < 0 or t <= last_t:
                continue
            last_t = t
            vals = [_num(row[i], *LIMITS[k], 0.0 if k in ("dx", "dy", "rot") else 1.0)
                    for i, k in zip(range(1, 6), ("dx", "dy", "rot", "sx", "sy"))]
            flip = 1 if len(row) > 6 and bool(row[6]) else 0
            clean.append([round(t, 4)] + [round(v, 3) for v in vals] + [flip])
        if len(clean) < 2 or clean[0][0] > 0.0001:
            clean.insert(0, [0.0] + list(clean[0][1:7]))
        if clean[-1][0] < 0.9999:
            clean.append([1.0] + list(clean[-1][1:7]))
        out.append({
            "key": key,
            "name": str(a.get("name") or key)[:40],
            "duration": round(_num(a.get("duration"), 0.1, 10.0, 1.0), 2),
            "icon": str(a.get("icon") or "·")[:4],
            "trigger": str(a.get("trigger") or "custom")[:20],
            "idle_weight": int(_num(a.get("idle_weight"), 0, 5, 0)),
            "flip_random": bool(a.get("flip_random")),
            "keys": clean,
        })
    return out


def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return normalize_defs(json.load(f))
    except Exception:
        return []


def to_map(defs):
    return {a["key"]: a for a in defs}


def evaluate(action, t, flip=False):
    """按 cosine 缓动插值，返回 (dx, dy, rot, sx, sy, flip)。"""
    keys = action.get("keys") or []
    if len(keys) < 2:                 # 脏数据兜底：不做任何变换，不让桌宠崩
        return (0.0, 0.0, 0.0, 1.0, 1.0, False)
    t = max(0.0, min(1.0, float(t)))
    if t <= keys[0][0]:
        row = keys[0]
    elif t >= keys[-1][0]:
        row = keys[-1]
    else:
        lo, hi = 0, len(keys) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if keys[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        a, b = keys[lo], keys[hi]
        span = b[0] - a[0]
        u = 0.0 if span <= 0 else (t - a[0]) / span
        w = (1 - math.cos(math.pi * u)) / 2
        row = [t] + [a[i] + (b[i] - a[i]) * w for i in range(1, 6)] + [a[6]]
    use_flip = bool(flip) if action.get("flip_random") else bool(row[6])
    return (row[1], row[2], row[3], row[4], row[5], use_flip)


def idle_pool(defs, enabled):
    """按权重生成待机候选；权重 0 或工作台关掉的动作不会自己播。"""
    pool = []
    for a in defs:
        if enabled.get(a["key"], True) is False:
            continue
        pool.extend([a["key"]] * int(a["idle_weight"]))
    return pool

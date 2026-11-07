#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 动作解释器（数据驱动）

桌宠和工作台共用一份 `actions.json`。每个动作是「关键帧数组 + 缓动」，
解释器只做插值，不再有任何硬编码公式；工作台编辑完发布后，桌宠直接用
下发的关键帧覆盖本地默认值，断网时回落到 actions.json。

关键帧格式（前 7 个数固定，第 8 位可选）：
    [t, dx, dy, rot, sx, sy, flip]                  root 整体变换（旧格式）
    [t, dx, dy, rot, sx, sy, flip, {"hand_r": [...]}]  追加部件字典（新格式）
    t    0..1      动作进度
    dx/dy          位移（桌宠逻辑像素）
    rot            旋转角度（度）
    sx/sy          横纵缩放
    flip           0/1 水平翻转；def.flip_random=true 时由播放方随机决定
    第 8 位       部件名 → [dx, dy, rot, sx, sy]，作用在父层局部坐标系；
                  未写出的部件该帧视为静止，动作结束自动回正。
                  老数据没有第 8 位时行为完全不变（向后兼容）。
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
MAX_PARTS = 12
PART_LIMITS = {
    "dx": (-120.0, 120.0),
    "dy": (-120.0, 120.0),
    "rot": (-120.0, 120.0),
    "sx": (0.3, 2.0),
    "sy": (0.3, 2.0),
}
PART_ZERO = (0.0, 0.0, 0.0, 1.0, 1.0)
PART_CHANNELS = ("dx", "dy", "rot", "sx", "sy")


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(n):
        return default
    return max(lo, min(hi, n))


def _clean_parts(raw):
    """净化关键帧第 8 位：部件名 → 5 通道，非法项直接丢弃。"""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, vals in list(raw.items())[:MAX_PARTS]:
        if not isinstance(name, str) or not KEY_RE.fullmatch(name):
            continue
        if not isinstance(vals, (list, tuple)) or len(vals) < 5:
            continue
        clean = []
        for i, k in enumerate(PART_CHANNELS):
            default = 1.0 if k in ("sx", "sy") else 0.0
            clean.append(round(_num(vals[i], *PART_LIMITS[k], default), 3))
        out[name] = clean
    return out


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
            frame = [round(t, 4)] + [round(v, 3) for v in vals] + [flip]
            parts = _clean_parts(row[7]) if len(row) > 7 else {}
            if parts:
                frame.append(parts)
            clean.append(frame)
        if len(clean) < 2 or clean[0][0] > 0.0001:
            head = [0.0] + list(clean[0][1:7])
            if len(clean[0]) > 7:
                head.append(dict(clean[0][7]))
            clean.insert(0, head)
        if clean[-1][0] < 0.9999:
            tail = [1.0] + list(clean[-1][1:7])
            if len(clean[-1]) > 7:
                tail.append(dict(clean[-1][7]))
            clean.append(tail)
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


def _segment(keys, t):
    """定位 t 落在哪两帧之间，返回 (帧a, 帧b, cosine 权重)；边界时 a==b、w=0。"""
    t = max(0.0, min(1.0, float(t)))
    if t <= keys[0][0]:
        return keys[0], keys[0], 0.0
    if t >= keys[-1][0]:
        return keys[-1], keys[-1], 0.0
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
    return a, b, (1 - math.cos(math.pi * u)) / 2


def evaluate(action, t, flip=False):
    """root 整体变换，按 cosine 缓动插值，返回 (dx, dy, rot, sx, sy, flip)。"""
    keys = action.get("keys") or []
    if len(keys) < 2:                 # 脏数据兜底：不做任何变换，不让桌宠崩
        return (0.0, 0.0, 0.0, 1.0, 1.0, False)
    a, b, w = _segment(keys, t)
    vals = [a[i] + (b[i] - a[i]) * w for i in range(1, 6)]
    use_flip = bool(flip) if action.get("flip_random") else bool(a[6])
    return (vals[0], vals[1], vals[2], vals[3], vals[4], use_flip)


def evaluate_parts(action, t):
    """部件局部变换：{name: (dx, dy, rot, sx, sy)}。

    某帧没写某个部件时按 PART_ZERO 参与插值，因此动作播完部件自动回正；
    整条动作没有第 8 位时返回空 dict，绘制端等价于老版整图模式。
    """
    keys = action.get("keys") or []
    if len(keys) < 2:
        return {}
    a, b, w = _segment(keys, t)
    pa = a[7] if len(a) > 7 and isinstance(a[7], dict) else {}
    pb = b[7] if len(b) > 7 and isinstance(b[7], dict) else {}
    out = {}
    for name in set(pa) | set(pb):
        va = pa.get(name, PART_ZERO)
        vb = pb.get(name, PART_ZERO)
        out[name] = tuple(va[i] + (vb[i] - va[i]) * w for i in range(5))
    return out


def idle_pool(defs, enabled):
    """按权重生成待机候选；权重 0 或工作台关掉的动作不会自己播。"""
    pool = []
    for a in defs:
        if enabled.get(a["key"], True) is False:
            continue
        pool.extend([a["key"]] * int(a["idle_weight"]))
    return pool

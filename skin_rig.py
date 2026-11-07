#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关节皮肤 manifest 校验与骨架计算（纯标准库，桌宠 / 工作台共用）。

不做任何绘制：桌宠用 PySide6 按这里算出的父子链逐层画，工作台用原生 JS
按同一份数据生成嵌套层。规范见 tunshuo-pet-studio/JOINT_SPEC.md。
"""

import math
import re

NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
FILE_RE = re.compile(r"^[a-z0-9_][a-z0-9_./-]{0,96}\.png$")
FRAME_KEYS = ("idle", "blink", "happy", "sleep", "speak")
MAX_PARTS = 12
PART_ZERO = (0.0, 0.0, 0.0, 1.0, 1.0)


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(n):
        return default
    return max(lo, min(hi, n))


def _safe_file(v):
    if not isinstance(v, str) or not FILE_RE.fullmatch(v):
        return None
    if v.startswith("/") or ".." in v.split("/"):
        return None
    return v


def normalize_manifest(raw):
    """把任意来源的 manifest 收敛成安全结构；不合法返回 None。"""
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode", "flat")
    if mode not in ("flat", "rig"):
        mode = "flat"
    frames = {}
    src_frames = raw.get("frames") if isinstance(raw.get("frames"), dict) else {}
    for k in FRAME_KEYS:
        f = _safe_file(src_frames.get(k))
        if f:
            frames[k] = f
    if not frames.get("idle"):
        frames["idle"] = "pet.png" if mode == "flat" else "head.png"

    parts = []
    if mode == "rig":
        seen = set()
        raw_parts = raw.get("parts") if isinstance(raw.get("parts"), list) else []
        for item in raw_parts[:MAX_PARTS]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            if not NAME_RE.fullmatch(name) or name in seen:
                continue
            f = _safe_file(item.get("file"))
            if not f:
                continue
            pv = item.get("pivot") if isinstance(item.get("pivot"), dict) else {}
            parent = item.get("parent")
            if parent is not None:
                parent = str(parent).strip().lower()
                if not NAME_RE.fullmatch(parent):
                    parent = None
            seen.add(name)
            parts.append({
                "name": name,
                "file": f,
                "pivot": {"x": round(_num(pv.get("x"), -1.2, 1.2, 0.0), 3),
                          "y": round(_num(pv.get("y"), -1.2, 1.2, 0.0), 3)},
                "parent": parent,
                "z": int(_num(item.get("z"), 0, 100, 0)),
                "overlap": int(_num(item.get("overlap"), 0, 32, 0)),
            })
        if not _valid_tree(parts):
            return None
    return {
        "id": str(raw.get("id") or "default")[:40].strip().lower(),
        "name": str(raw.get("name") or "关节皮肤")[:60],
        "mode": mode,
        "version": str(raw.get("version") or "1.0.0")[:20],
        "frames": frames,
        "parts": parts,
        "placeholder": bool(raw.get("placeholder")),
    }


def _valid_tree(parts):
    """必须恰好一个 root，parent 都存在且不成环。"""
    names = {p["name"] for p in parts}
    roots = [p for p in parts if p["parent"] is None]
    if len(roots) != 1:
        return False
    for p in parts:
        if p["parent"] is not None and p["parent"] not in names:
            return False
    for start in names:
        cur, hops = start, 0
        while hops <= len(names):
            p = next((x for x in parts if x["name"] == cur), None)
            if p is None or p["parent"] is None:
                break
            cur = p["parent"]
            hops += 1
        else:
            return False
    return True


def root_name(parts):
    for p in parts:
        if p["parent"] is None:
            return p["name"]
    return None


def children_of(parts):
    out = {p["name"]: [] for p in parts}
    for p in parts:
        if p["parent"]:
            out[p["parent"]].append(p["name"])
    return out


def z_order(parts):
    return sorted(parts, key=lambda p: (p["z"], p["name"]))


def normalize_ref(raw):
    """工作台发布配置里的 skin 引用：只允许 id + mode，未知字段丢弃。"""
    if not isinstance(raw, dict):
        return {"id": "default", "mode": "flat"}
    sid = str(raw.get("id") or "default")[:40].strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", sid):
        sid = "default"
    return {"id": sid, "mode": "rig" if raw.get("mode") == "rig" else "flat"}


def bounding_radius(parts, transforms, pet_w, pet_h):
    """所有部件旋转/缩放后的保守覆盖半径（旋转不改变半径，故只看位移与缩放）。

    给窗口遮罩用：挥手、转头时部件伸到角色轮廓外，固定余量会把它裁掉。
    """
    r = math.hypot(pet_w / 2.0, pet_h / 2.0)
    for p in parts:
        dx, dy, _rot, sx, sy = transforms.get(p["name"], PART_ZERO)
        px = p["pivot"]["x"] * pet_w
        py = p["pivot"]["y"] * pet_h
        half = math.hypot(pet_w / 2.0 * sx, pet_h / 2.0 * sy)
        r = max(r, math.hypot(px + dx, py + dy) + half)
    return r

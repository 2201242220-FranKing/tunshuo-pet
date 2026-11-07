# -*- coding: utf-8 -*-
"""形象工作台同步（本地站 / 上线后同一套代码）

职责边界：
  · fetch()        在 QThread 里跑：拉 /api/published、把缺的配饰 PNG 下到本地
  · normalize()    补齐/夹逼字段，服务端给脏数据也不会让桌宠崩
  · build_pixmaps()在主线程跑：把配饰文件变成 QPixmap（QWidget 只能在主线程碰）

断网 / 工作台没开时：读 studio_cache.json 继续用上一次的形象，全程静默，不弹错。
"""

import json
import os
import re
import urllib.request

import action_engine as ae

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(APP_DIR, "studio_cache.json")
ACC_DIR = os.path.join(APP_DIR, "assets", "accessories")

DEFAULT_PHRASES = [
    "在的！有热帖我第一个告诉你～",
    "今天论坛好热闹，我蹲着呢",
    "双击我可以看热帖榜哦",
    "有新动态我会冒个泡～",
    "要不要看看闲置区？说不定有惊喜",
    "校园卡这周的优惠我帮你盯着呢",
]

# 与工作台 server.py 的 blank_config() 保持一致：默认即「没接工作台」时的行为
DEFAULT_STUDIO = {
    "revision": 0,
    "updated_at": "",
    "name": "豚说小豚 · 官方形象",
    "appearance": {"scale": 1.0, "tint": "#57B6EE"},
    "actions": {
        "idle_min": 4.5, "idle_max": 11.0, "speed": 1.0,
        "enabled": {},
        "weights": {"sway": 2, "look": 2, "stretch": 1, "hop": 1, "nod": 1},
        "defs": [],              # 工作台发布的动作定义；空 = 桌宠用 actions.json 默认值
    },
    "settings": {
        "notify": True, "auto_sleep_seconds": 180,
        "greeting": "点我看看热帖～右键有菜单",
        "phrases": list(DEFAULT_PHRASES),
    },
    "accessories": [],
}


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize(raw):
    """把服务端配置收敛成桌宠能安全使用的结构。"""
    d = json.loads(json.dumps(DEFAULT_STUDIO))
    if not isinstance(raw, dict):
        return d
    try:
        d["revision"] = int(raw.get("revision", 0))
    except (TypeError, ValueError):
        pass
    d["updated_at"] = str(raw.get("updated_at", ""))[:40]
    d["name"] = str(raw.get("name") or d["name"])[:60]

    ap = raw.get("appearance") if isinstance(raw.get("appearance"), dict) else {}
    d["appearance"]["scale"] = _num(ap.get("scale"), 0.7, 1.4, 1.0)

    ac = raw.get("actions") if isinstance(raw.get("actions"), dict) else {}
    lo = _num(ac.get("idle_min"), 1.0, 60.0, 4.5)
    hi = _num(ac.get("idle_max"), 1.0, 120.0, 11.0)
    d["actions"]["idle_min"], d["actions"]["idle_max"] = min(lo, hi), max(lo, hi)
    d["actions"]["speed"] = _num(ac.get("speed"), 0.5, 2.0, 1.0)
    d["actions"]["defs"] = ae.normalize_defs(ac.get("defs"))
    en = ac.get("enabled") if isinstance(ac.get("enabled"), dict) else {}
    wt = ac.get("weights") if isinstance(ac.get("weights"), dict) else {}
    for k, v in en.items():
        if isinstance(k, str):
            d["actions"]["enabled"][k] = bool(v)
    for k, v in wt.items():
        if isinstance(k, str):
            d["actions"]["weights"][k] = int(_num(v, 0, 5, 1))

    st = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    d["settings"]["notify"] = bool(st.get("notify", True))
    d["settings"]["auto_sleep_seconds"] = int(_num(st.get("auto_sleep_seconds"), 0, 7200, 180))
    d["settings"]["greeting"] = str(st.get("greeting") or d["settings"]["greeting"])[:120]
    phrases = st.get("phrases")
    if isinstance(phrases, list):
        cleaned = [str(x)[:120] for x in phrases[:20] if isinstance(x, str) and str(x).strip()]
        if cleaned:
            d["settings"]["phrases"] = cleaned

    accs = raw.get("accessories")
    if isinstance(accs, list):
        for a in accs[:12]:
            if not isinstance(a, dict) or not a.get("enabled"):
                continue
            src = a.get("src")
            if not isinstance(src, str) or not re.fullmatch(r"[\w\-.]+\.png", src):
                continue
            d["accessories"].append({
                "id": str(a.get("id") or "")[:40],
                "src": src,
                "name": str(a.get("name") or "配饰")[:40],
                "enabled": True,       # 保留字段，让 normalize 可重复调用
                "x": _num(a.get("x"), -1.2, 1.2, 0.0),
                "y": _num(a.get("y"), -1.2, 1.2, 0.0),
                "scale": _num(a.get("scale"), 0.1, 1.6, 0.5),
                "layer": "back" if a.get("layer") == "back" else "front",
                "follow": bool(a.get("follow", True)),
            })
    return d


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return normalize(json.load(f))
    except Exception:
        return normalize({})


def write_cache(data):
    tmp = CACHE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, CACHE_PATH)
    except Exception:
        pass


def _opener():
    """绕过系统 HTTP 代理：本地站地址绝不能走代理，否则 127.0.0.1 会被转发到外网。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(base_url):
    """线程内执行。返回规范化的配置 dict；失败抛异常由调用方静默处理。"""
    url = base_url.rstrip("/") + "/api/published"
    req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet/4.0"})
    with _opener().open(req, timeout=4) as r:
        raw = json.loads(r.read().decode("utf-8"))
    data = normalize(raw)
    os.makedirs(ACC_DIR, exist_ok=True)
    for a in data["accessories"]:
        local = os.path.join(ACC_DIR, a["src"])
        if os.path.isfile(local) and os.path.getsize(local) > 64:
            continue
        img_url = base_url.rstrip("/") + "/media/" + a["src"]
        req = urllib.request.Request(img_url, headers={"User-Agent": "TunshuoPet/4.0"})
        try:
            with _opener().open(req, timeout=6) as r:
                blob = r.read()
            if len(blob) < 64 or len(blob) > 4 * 1024 * 1024:
                continue
            tmp = local + ".tmp"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, local)
        except Exception:
            continue          # 单张配饰失败不影响其它配饰与配置生效
    return data


def build_pixmaps(data, pet_w):
    """主线程执行：把配饰图片变成可直接 drawPixmap 的 QPixmap。

    与角色一致，不做运行期 scaled，而是设置 devicePixelRatio 让系统按原始像素合成，
    避免 RGBA 透明区插值出黑边。
    """
    from PySide6.QtGui import QPixmap
    out = []
    for a in data["accessories"]:
        path = os.path.join(ACC_DIR, a["src"])
        if not os.path.isfile(path):
            continue
        pm = QPixmap(path)
        if pm.isNull():
            continue
        w = max(1.0, pet_w * a["scale"])
        if pm.width() > w:
            pm.setDevicePixelRatio(pm.width() / w)
        item = dict(a)
        item["pm"] = pm
        item["lw"] = pm.width() / (pm.devicePixelRatio() or 1.0)
        item["lh"] = pm.height() / (pm.devicePixelRatio() or 1.0)
        out.append(item)
    return out

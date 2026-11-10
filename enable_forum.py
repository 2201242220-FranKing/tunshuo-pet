#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说桌宠 · 真实论坛接口一键启用 / 回退工具。

默认是**预览模式**：只显示将改动的内容并做一次只读联调，不写任何文件。
必须显式加 --apply 才会改 config.json。令牌永远不写入配置。

用法（学校 ID 可以一个一个加，桌宠会同时监控列表里所有学校）：
  python3 enable_forum.py --list                                  # 看当前监控了哪些学校
  python3 enable_forum.py --add 圈子ID --name 学校简称             # 预览 + 只读联调
  python3 enable_forum.py --add 圈子ID --name 学校简称 --apply     # 正式加入
  python3 enable_forum.py --remove 圈子ID --apply                  # 移除某个学校
  python3 enable_forum.py --off --apply                           # 全部清空，回退演示数据

  旧写法仍可用：
  python3 enable_forum.py --circle-id 学校圈子ID --apply         # 只监控一个学校
  python3 enable_forum.py --all --apply                          # 全站（不推荐）
  python3 enable_forum.py --circle-id 学校圈子ID --no-verify     # 跳过联网联调
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import forum_api as fa  # noqa: E402

CONFIG = ROOT / "config.json"
TMP = ROOT / "config.json.tmp"


def arg(name):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def has(flag):
    return flag in sys.argv


def read_cfg():
    if not CONFIG.is_file():
        return {}
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError) as e:
        sys.exit("读取 config.json 失败：%s" % e)


def show_status(cfg):
    base = str(cfg.get("forum_base") or "").strip()
    circle = str(cfg.get("forum_circle_id") or "").strip()
    print("config.json：", CONFIG)
    print("  forum_base       =", repr(base))
    print("  forum_circle_id  =", repr(circle))
    print("  forum_allow_all  =", bool(cfg.get("forum_allow_all", False)))
    circles = current_circles(cfg) if base else []
    print("  监控学校 (%d)     =" % len(circles))
    for c in circles:
        print("      - %-10s %s" % (c["name"] or "(未命名)", c["id"] or "全站"))
    print("  auto_poll        =", bool(cfg.get("auto_poll", False)),
          "（自动轮询默认且建议保持关闭）")
    print("  当前状态         =", "已启用真实接口" if base else "未启用（演示数据）")
    print("  令牌环境变量     =", "已设置" if os.environ.get(fa.TOKEN_ENV) else "未设置",
          "（只从环境变量读，脚本不会写进配置）")


def show_diff(cfg, changes):
    print("将改动的字段：")
    for k, v in changes.items():
        old = cfg.get(k, "<不存在>")
        print("  %-18s %r -> %r" % (k, old, v))
    untouched = [k for k in cfg if k not in changes]
    print("其余 %d 个字段保持不变：%s" % (len(untouched), ", ".join(sorted(untouched)) or "(无)"))


def verify(cfg):
    print("\n只读联调（不写盘）：")
    try:
        client = fa.ForumClient.from_config(cfg)
        adapter = fa.ForumAdapter(cfg, client=client)
        posts = adapter.fetch()
        print("  学校数 %d，取到 %d 条帖子，热度最高 %d，标签示例 %s"
              % (len(adapter.circles), len(posts),
                 max((p["heat"] for p in posts), default=0),
                 (posts[0]["tag"] or "动态") if posts else "-"))
        if adapter.last_errors:
            print("  部分学校未取到：", "；".join(adapter.last_errors[:3]))
        if adapter.last_warning:
            print("  降级提示：", adapter.last_warning)
        print("  联调通过。")
    except fa.ForumError as e:
        print("  联调失败：", e)
        print("  这不代表配置写不了，可能是网络或圈子 ID 不对；可加 --no-verify 跳过。")


def write_cfg(cfg):
    try:
        TMP.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(TMP, CONFIG)
    except OSError as e:
        try:
            TMP.unlink()
        except OSError:
            pass
        sys.exit("写入 config.json 失败：%s" % e)


def current_circles(cfg):
    """读当前学校列表，兼容旧的单值 forum_circle_id。"""
    return [dict(c) for c in fa.normalize_circles(cfg)[0] if c["id"]]


def valid_id(cid):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", cid or ""))


def build_add(cfg, circle_id, name):
    if not valid_id(circle_id):
        sys.exit("圈子 ID 看起来不对：%r（应是一串数字或字母，不要带空格/引号）" % circle_id)
    circles = current_circles(cfg)
    hit = [c for c in circles if c["id"] == circle_id]
    if hit:
        if name:
            for c in hit:
                if not c["name"]:
                    c["name"] = name[:12]
        print("这个学校已在列表里，只更新名称：", circle_id)
    else:
        if len(circles) >= fa.MAX_CIRCLES:
            sys.exit("最多同时监控 %d 个学校，请先 --remove 一个。" % fa.MAX_CIRCLES)
        circles.append({"id": circle_id, "name": (name or "")[:12]})
        print("加入学校：%s %s（共 %d 所）" % (name or "(未命名)", circle_id, len(circles)))
    return {"forum_base": fa.KNOWN_BASE,
            "forum_circles": circles,
            "forum_circle_id": circles[0]["id"],
            "forum_allow_all": False}


def build_remove(cfg, circle_id):
    circles = current_circles(cfg)
    left = [c for c in circles if c["id"] != circle_id]
    if len(left) == len(circles):
        sys.exit("列表里没有这个 ID：%s（用 --list 查看）" % circle_id)
    if not left:
        print("移除后列表为空，将回退到演示数据。")
        return {"forum_base": "", "forum_circles": [],
                "forum_circle_id": "", "forum_allow_all": False}
    print("移除学校：%s（剩 %d 所）" % (circle_id, len(left)))
    return {"forum_base": fa.KNOWN_BASE, "forum_circles": left,
            "forum_circle_id": left[0]["id"], "forum_allow_all": False}


def main():
    cfg = read_cfg()

    if has("--status") or has("--list"):
        show_status(cfg)
        return

    if has("--off"):
        changes = {"forum_base": "", "forum_circle_id": "",
                   "forum_allow_all": False, "forum_circles": []}
        print("回退到演示数据（清空学校列表，保留其他所有配置）。")
    elif has("--add"):
        changes = build_add(cfg, (arg("--add") or "").strip(),
                            (arg("--name") or "").strip())
    elif has("--remove"):
        changes = build_remove(cfg, (arg("--remove") or "").strip())
    else:
        circle = (arg("--circle-id") or "").strip()
        allow_all = has("--all")
        if not circle and not allow_all:
            print(__doc__)
            sys.exit("\n请提供 --add <圈子ID> --name <学校简称>，或用 --list 查看当前列表。")
        if allow_all:
            print("注意：--all 会拉全站帖子，不按学校筛选，仅建议临时试跑。")
        changes = {"forum_base": fa.KNOWN_BASE,
                   "forum_circle_id": circle,
                   "forum_circles": [],
                   "forum_allow_all": allow_all}

    show_diff(cfg, changes)
    merged = dict(cfg, **changes)

    if not has("--apply"):
        if not has("--no-verify") and not has("--off"):
            verify(merged)
        print("\n这是预览，没有写入任何文件。确认后加 --apply 才会生效。")
        return

    write_cfg(merged)
    print("\n已写入", CONFIG)
    show_status(merged)
    print("\n下一步（脚本不会替你做）：")
    if not merged.get("forum_base"):
        print("  退出并重启桌宠，即恢复演示数据。")
    else:
        print("  1. 退出并重启桌宠 .app（新配置只在启动时读取）")
        print("  2. 右键「立即刷新」拉取真实帖子；首次刷新只建基线、不会误报新帖")
        print("  3. 若要定时播报，再单独把 auto_poll 设为 true（需另行确认）")
    print("  加学校：python3 enable_forum.py --add <ID> --name <简称> --apply")
    print("  回退命令：python3 enable_forum.py --off --apply")


if __name__ == "__main__":
    main()

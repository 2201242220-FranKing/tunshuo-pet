#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说桌宠 · 真实论坛接口一键启用 / 回退工具。

默认是**预览模式**：只显示将改动的内容并做一次只读联调，不写任何文件。
必须显式加 --apply 才会改 config.json。令牌永远不写入配置。

用法：
  python3 enable_forum.py --status
  python3 enable_forum.py --circle-id 学校圈子ID                 # 预览 + 只读联调
  python3 enable_forum.py --circle-id 学校圈子ID --apply         # 写入 config.json
  python3 enable_forum.py --all --apply                          # 不按学校筛选（全站，不推荐）
  python3 enable_forum.py --off --apply                          # 回退到演示数据
  python3 enable_forum.py --circle-id 学校圈子ID --no-verify     # 跳过联网联调
"""

import json
import os
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
        print("  取到 %d 条帖子，热度最高 %d，标签示例 %s"
              % (len(posts), max((p["heat"] for p in posts), default=0),
                 (posts[0]["tag"] or "动态") if posts else "-"))
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


def main():
    cfg = read_cfg()

    if has("--status"):
        show_status(cfg)
        return

    if has("--off"):
        changes = {"forum_base": "", "forum_circle_id": "", "forum_allow_all": False}
        print("回退到演示数据（保留其他所有配置）。")
    else:
        circle = (arg("--circle-id") or "").strip()
        allow_all = has("--all")
        if not circle and not allow_all:
            print(__doc__)
            sys.exit("\n请提供 --circle-id <学校圈子ID>，或用 --all 明确选择不按学校筛选。")
        if allow_all:
            print("注意：--all 会拉全站帖子，不按你的学校圈子筛选，仅建议临时试跑。")
        changes = {"forum_base": fa.KNOWN_BASE,
                   "forum_circle_id": circle,
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
    if has("--off"):
        print("  退出并重启桌宠，即恢复演示数据。")
    else:
        print("  1. 退出并重启桌宠 .app（新配置只在启动时读取）")
        print("  2. 右键「立即刷新」拉取真实帖子；首次刷新只建基线、不会误报新帖")
        print("  3. 若要定时播报，再单独把 auto_poll 设为 true（需另行确认）")
    print("  回退命令：python3 enable_forum.py --off --apply")


if __name__ == "__main__":
    main()

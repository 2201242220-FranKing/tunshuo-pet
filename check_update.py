#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 版本与更新检查（只读，不自动更新）

    python3 check_update.py              # 状态行 + 给用户的固定提示话术
    python3 check_update.py --quiet      # 只输出状态行，供 agent / 脚本解析
    python3 check_update.py --version    # 只输出本地版本号

状态行：UPDATE_AVAILABLE / UP_TO_DATE / UNKNOWN / NO_GIT

只调用仓库已有的 git 远端做 fetch / rev-list / show：不 pull、不改工作区、
不写配置、不引入任何新的接口或第三方依赖。断网、ZIP 分发、没有 upstream
都会安静降级，绝不影响桌宠本身的使用。
"""

import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WIN = sys.platform.startswith("win")

# 唯一一份「更新提示话术」：AGENTS.md 直接引用这里，避免两处文案漂移。
# {version} 本地版本 / {remote_version} 线上版本 / {behind} 落后提交数。
UPDATE_PROMPT = (
    "豚说小豚有新版本可用（本地 v{version}，线上 v{remote_version}，"
    "落后 {behind} 个提交）。\n"
    "建议现在更新：让 agent 执行 git pull --ff-only，再运行 "
    "python3 bootstrap.py --setup，最后从托盘退出并重新启动小豚即可生效。\n"
    "若本地改过 config.json 等文件，agent 会先告知你，不会强行覆盖。"
)
BUBBLE_PROMPT = "小豚有新版本啦～\n让 agent 跑 git pull 就能更新"

STATUS = {
    "update": "UPDATE_AVAILABLE",
    "up_to_date": "UP_TO_DATE",
    "unknown": "UNKNOWN",
    "no_git": "NO_GIT",
}


def read_version():
    """读仓库根的 VERSION；ZIP 分发 / 文件缺失时给兜底值。"""
    try:
        with open(os.path.join(APP_DIR, "VERSION"), "r", encoding="utf-8") as f:
            return f.readline().strip() or "4.2.0"
    except OSError:
        return "4.2.0"


def _git(*args, timeout=8):
    """在工作区里跑只读 git 命令；Windows 下不弹控制台黑窗。"""
    kw = dict(cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if IS_WIN:
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.run(["git"] + list(args), **kw)


def check(timeout=8):
    """返回检查结果 dict。字段：

    state           update / up_to_date / unknown / no_git
    version         本地版本字符串
    remote_version  线上 VERSION（旧远端没有此文件时为 "unknown"）
    local / remote  短 commit hash
    behind          落后提交数
    dirty           本地是否有未提交改动（pull 前必须提醒用户）
    subject         线上最新提交标题
    prompt          给用户的固定提示话术（仅 update 时非空）
    message         人读/CLI 用的完整文本
    """
    version = read_version()
    r = {"state": "unknown", "version": version, "remote_version": "",
         "local": "", "remote": "", "behind": 0, "dirty": False,
         "subject": "", "prompt": "", "message": ""}

    if not os.path.isdir(os.path.join(APP_DIR, ".git")):
        r["state"] = "no_git"
        r["message"] = "ZIP 版无法自动检查更新，重新 git clone 后即可启用"
        return r

    try:
        r["local"] = _git("rev-parse", "--short", "HEAD", timeout=3).stdout.strip() or "unknown"
    except Exception:
        r["local"] = "unknown"
    try:
        r["dirty"] = bool(_git("status", "--porcelain", timeout=3).stdout.strip())
    except Exception:
        pass

    try:
        fetched = _git("fetch", "--quiet", "--prune", "origin", timeout=timeout)
    except Exception:
        fetched = None
    if fetched is None or fetched.returncode != 0:
        r["message"] = "暂时连不上仓库，跳过更新检查（不影响使用）"
        return r

    try:
        cnt = _git("rev-list", "--count", "HEAD..@{u}", timeout=3)
        r["behind"] = int(cnt.stdout.strip() or 0) if cnt.returncode == 0 else 0
        r["remote"] = _git("rev-parse", "--short", "@{u}", timeout=3).stdout.strip() or "unknown"
        r["subject"] = _git("log", "-1", "--pretty=%s", "@{u}", timeout=3).stdout.strip()
        show = _git("show", "@{u}:VERSION", timeout=3)
        lines = show.stdout.strip().splitlines() if show.returncode == 0 else []
        r["remote_version"] = lines[0].strip() if lines else "unknown"
    except Exception:
        r["message"] = "远端信息读取失败，跳过更新检查（不影响使用）"
        return r

    if r["behind"] > 0:
        r["state"] = "update"
        r["prompt"] = UPDATE_PROMPT.format(
            version=version, remote_version=r["remote_version"], behind=r["behind"])
        r["message"] = r["prompt"]
        if r["subject"]:
            r["message"] += "\n线上最新提交：%s" % r["subject"][:60]
        if r["dirty"]:
            r["message"] += "\n注意：本地有未提交改动，请先确认再更新。"
    else:
        r["state"] = "up_to_date"
        r["message"] = "已是最新版本 v%s" % version
    return r


def main():
    args = sys.argv[1:]
    r = check()
    if "--version" in args:
        print(r["version"])
        return 0
    print(STATUS.get(r["state"], "UNKNOWN"))
    if "--quiet" not in args:
        if r["state"] == "update":
            print(r["prompt"])
            if r["subject"]:
                print("线上最新提交：%s" % r["subject"][:60])
            if r["dirty"]:
                print("注意：本地有未提交改动，请先确认再更新。")
        else:
            print(r["message"])
        print("本地版本 v%s（%s）" % (r["version"], r["local"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

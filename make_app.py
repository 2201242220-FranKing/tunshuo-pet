#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把豚说小豚打包成 macOS .app（免终端、可放 Dock/启动台/应用程序文件夹）

仅 macOS 可用；Windows 用 start_windows.bat，Linux / 通用安装用 bootstrap.py。
主程序 tunshuo_pet_pro.py 三个平台共用同一份代码。

用法：
    python3 make_app.py            # 生成并安装到 ~/Applications/豚说小豚.app
    TUNSHUO_INSTALL_DIR=/some/path python3 make_app.py   # 自定义安装位置

运行时可通过环境变量覆盖：
    TUNSHUO_PET_DIR   源码目录（换机器/换路径时不用重新打包）
    PET_PYTHON        Python 解释器路径
    TUNSHUO_INSTALL_DIR（仅打包时）  .app 安装位置

说明：这是轻量方案，依赖本机已装好的 Python + PySide6；启动器会优先用打包时记录的
解释器，找不到时自动探测 .venv / PET_PYTHON / PATH。要拷给别人用，在对方机器上
重新执行一次 make_app.py 即可；若要完全自包含，需要另走 PyInstaller 路线（体积约 200MB）。
"""

import os
import plistlib
import shutil
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "豚说小豚.app"
INSTALL_DIR = os.environ.get("TUNSHUO_INSTALL_DIR") or os.path.expanduser("~/Applications")
BUILD_DIR = os.path.join(APP_DIR, "build")
BUNDLE_ID = "online.tunshuo.pet"


def read_version():
    try:
        with open(os.path.join(APP_DIR, "VERSION"), "r", encoding="utf-8") as f:
            return f.readline().strip() or "4.2.0"
    except OSError:
        return "4.2.0"

LAUNCHER = """#!/bin/sh
# 豚说小豚 启动器（由 make_app.py 生成）
# 换机器请重新执行一次 make_app.py；也可用环境变量覆盖源码目录和安装位置。
PET_DIR="${{TUNSHUO_PET_DIR:-{pet_dir}}}"
LOG="$HOME/Library/Logs/tunshuo-pet.log"
mkdir -p "$(dirname "$LOG")"

# 单实例保护：已经在跑就不再开第二只
if pgrep -f "$PET_DIR/tunshuo_pet_pro.py" >/dev/null 2>&1; then
  exit 0
fi

# 解释器：优先用打包时记录的（本机一定可用）；文件不存在（换机器/升级 Python）
# 时依次探测项目 venv、PET_PYTHON 环境变量、PATH 里的 python3。
PY="{python}"
if [ ! -x "$PY" ]; then
  if [ -x "$PET_DIR/.venv/bin/python3" ]; then
    PY="$PET_DIR/.venv/bin/python3"
  elif [ -n "$PET_PYTHON" ] && [ -x "$PET_PYTHON" ]; then
    PY="$PET_PYTHON"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  fi
fi

if ! "$PY" -c 'import PySide6' >/dev/null 2>&1; then
  echo "PySide6 不可用，请先安装依赖：\\"$PY\\" -m pip install -r requirements.txt" >>"$LOG"
  exit 1
fi

cd "$PET_DIR" || exit 1
exec "$PY" "$PET_DIR/tunshuo_pet_pro.py" >>"$LOG" 2>&1
"""


def make_icns(src_png, out_icns):
    """用 sips + iconutil 从 PNG 生成 .icns 图标集。"""
    iconset = os.path.join(BUILD_DIR, "pet.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            px = size * scale
            dst = os.path.join(iconset, "icon_%dx%d%s.png" % (size, size, suffix))
            subprocess.run(["sips", "-z", str(px), str(px), src_png, "--out", dst],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out_icns],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(iconset, ignore_errors=True)
    return out_icns


def build():
    if sys.platform != "darwin":
        sys.exit("make_app.py 只用于 macOS 生成 .app。\n"
                 "Windows 请双击 start_windows.bat，或执行 py -3 bootstrap.py；\n"
                 "Linux 请执行 python3 bootstrap.py。")
    app_path = os.path.join(BUILD_DIR, APP_NAME)
    shutil.rmtree(app_path, ignore_errors=True)
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    res_dir = os.path.join(app_path, "Contents", "Resources")
    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    # 1) 图标
    icns = make_icns(os.path.join(APP_DIR, "assets", "pet.png"),
                     os.path.join(res_dir, "pet.icns"))

    # 2) Info.plist
    info = {
        "CFBundleName": "豚说小豚",
        "CFBundleDisplayName": "豚说小豚",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": "launcher",
        "CFBundleIconFile": "pet",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": read_version(),
        "CFBundleShortVersionString": read_version(),
        "LSUIElement": True,          # 不显示 Dock 图标（菜单栏托盘已够用）
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    }
    with open(os.path.join(app_path, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(info, f)

    # 3) 启动器
    launcher = os.path.join(macos_dir, "launcher")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER.format(pet_dir=APP_DIR, python=sys.executable))
    os.chmod(launcher, 0o755)

    # 4) ad-hoc 签名（本机运行足够，避免 Gatekeeper 提示）
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5) 安装到 ~/Applications
    os.makedirs(INSTALL_DIR, exist_ok=True)
    target = os.path.join(INSTALL_DIR, APP_NAME)
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(app_path, target, symlinks=True)
    print("已安装:", target)
    return target


if __name__ == "__main__":
    build()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把豚说小豚打包成 macOS .app（免终端、可放 Dock/启动台/应用程序文件夹）

用法：
    python3 make_app.py            # 生成并安装到 ~/Applications/豚说小豚.app

产物结构：
    豚说小豚.app/Contents/
        Info.plist            LSUIElement=true（不在 Dock 显示、不占 Cmd+Tab）
        MacOS/launcher        启动脚本（内部调 python 跑主程序，无终端窗口）
        Resources/pet.icns    从 assets/pet.png 生成的图标

说明：这是"本机自用"的轻量方案，体积 ~0MB，依赖本机已装好的 Python + PySide6。
要拷给别人用，需要另一条路线（PyInstaller 打包自带解释器，体积 ~200MB）。
"""

import os
import plistlib
import shutil
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "豚说小豚.app"
INSTALL_DIR = os.path.expanduser("~/Applications")
BUILD_DIR = os.path.join(APP_DIR, "build")
BUNDLE_ID = "online.tunshuo.pet"

LAUNCHER = """#!/bin/sh
# 豚说小豚 启动器（由 make_app.py 生成）
PET_DIR="{pet_dir}"
PY="{python}"
LOG="$HOME/Library/Logs/tunshuo-pet.log"
mkdir -p "$(dirname "$LOG")"

# 单实例保护：已经在跑就不再开第二只
if pgrep -f "$PET_DIR/tunshuo_pet_pro.py" >/dev/null 2>&1; then
  exit 0
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
        "CFBundleVersion": "3.0",
        "CFBundleShortVersionString": "3.0",
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

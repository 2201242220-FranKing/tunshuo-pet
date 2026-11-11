#!/bin/sh
# 双击即可运行（macOS）。会打开终端窗口，跑完 bootstrap 后终端可以关闭。
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 Python 3，请先安装 3.9~3.13：https://www.python.org/downloads/"
  read -r _
  exit 1
fi
python3 bootstrap.py

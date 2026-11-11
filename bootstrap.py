#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 一键环境准备 + 启动（macOS / Windows / Linux 通用）

    python3 bootstrap.py             # 补依赖并后台启动（命令立即返回）
    python3 bootstrap.py --setup     # 只补依赖，不启动
    python3 bootstrap.py --check     # 只读体检：不建 venv、不装包、不写文件

做四件事：
  1. 校验 Python 版本（3.9~3.13，64 位）
  2. 缺 .venv 就建；当前不在虚拟环境里就用 .venv 的解释器重新执行自己
  3. 缺 PySide6 / Pillow 就自动 pip install -r requirements.txt
  4. 后台启动 tunshuo_pet_pro.py（Windows 用 pythonw，不弹黑窗）

全程不需要用户回答任何问题。只写 .venv/ 与 logs/ 两个目录（都已加入 .gitignore），
不改 config.json、不写令牌、不调用除 PyPI 与已有 git 远端之外的任何服务。
"""

import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
VENV_DIR = os.path.join(APP_DIR, ".venv")
VENV_PY = (os.path.join(VENV_DIR, "Scripts", "python.exe") if IS_WIN
           else os.path.join(VENV_DIR, "bin", "python"))
VENV_PYW = (os.path.join(VENV_DIR, "Scripts", "pythonw.exe") if IS_WIN
            else VENV_PY)
LOG_DIR = os.path.join(APP_DIR, "logs")
REQ = os.path.join(APP_DIR, "requirements.txt")
MAIN = os.path.join(APP_DIR, "tunshuo_pet_pro.py")
MARKER = "TUNSHUO_BOOTSTRAP_VENV"

MIN_PY = (3, 9)
MAX_PY = (3, 13)
DEPS_PROBE = ("import PySide6, PIL; "
              "from PySide6 import QtCore, QtGui, QtWidgets")


def say(*parts):
    print(*parts, flush=True)


def python_ok():
    return MIN_PY <= sys.version_info[:2] <= MAX_PY and sys.maxsize > 2 ** 32


def read_version():
    try:
        with open(os.path.join(APP_DIR, "VERSION"), "r", encoding="utf-8") as f:
            return f.readline().strip() or "?"
    except OSError:
        return "?"


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=APP_DIR, **kw)


def ensure_venv():
    if os.path.isfile(VENV_PY):
        return True
    say("[1/3] 创建虚拟环境 .venv ...")
    try:
        run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    except Exception as ex:
        say("创建虚拟环境失败：%s" % str(ex)[:120])
        if not IS_WIN and not IS_MAC:
            say("Debian/Ubuntu 请先执行：sudo apt install python3-venv")
        say("也可跳过虚拟环境，直接执行：pip install -r requirements.txt")
        return False
    return os.path.isfile(VENV_PY)


def deps_ok(py):
    try:
        return run([py, "-c", DEPS_PROBE], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=60).returncode == 0
    except Exception:
        return False


def install_deps(py):
    say("[2/3] 正在补齐缺失依赖（首次约 1~3 分钟，需能访问 PyPI）...")
    r = run([py, "-m", "pip", "install", "--disable-pip-version-check",
             "-r", REQ])
    if r.returncode != 0:
        say("依赖安装失败，常见原因：")
        say("  · 无法访问 PyPI（检查网络 / 公司代理 / 防火墙）")
        say("  · Python 版本不在 3.9~3.13 或为 32 位")
        say("  · 磁盘空间不足（约需 300MB）")
        return False
    return deps_ok(py)


def setup(py):
    if not ensure_venv():
        return False
    if not deps_ok(py):
        if not install_deps(py):
            return False
    say("[3/3] 依赖就绪：PySide6-Essentials + Pillow")
    return True


def launch(py):
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "pet.log")
    log = open(log_path, "ab", buffering=0)
    if IS_WIN:
        exe = VENV_PYW if os.path.isfile(VENV_PYW) else py
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen([exe, MAIN], cwd=APP_DIR,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             creationflags=flags, close_fds=True)
    else:
        p = subprocess.Popen([py, MAIN], cwd=APP_DIR,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True)
    say("已启动小豚（PID %d）。日志：%s" % (p.pid, log_path))
    say("退出：点系统托盘 → 退出。重复启动会出现第二只，先退出再启动。")
    if IS_MAC:
        say("想要双击免终端运行，可再执行一次：python3 make_app.py")
    return True


def check_only():
    say("平台      ：%s（%s）" % (sys.platform,
                                "64 位" if sys.maxsize > 2 ** 32 else "32 位"))
    say("Python    ：%s" % sys.version.split()[0])
    say("桌宠版本  ：v%s" % read_version())
    say("解释器    ：%s" % sys.executable)
    say("虚拟环境  ：%s" % (VENV_PY if os.path.isfile(VENV_PY) else "未创建"))
    probe = VENV_PY if os.path.isfile(VENV_PY) else sys.executable
    ok = deps_ok(probe)
    say("依赖      ：%s" % ("齐全" if ok else "缺失，运行 python3 bootstrap.py 即可补齐"))
    if not python_ok():
        say("结论      ：Python 版本不符，需要 3.9~3.13 的 64 位 Python")
        return 1
    say("结论      ：%s" % ("ENV_OK 环境已就绪" if ok else "ENV_MISSING 需要补齐依赖"))
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if "--check" in args:
        return check_only()
    if not python_ok():
        say("Python 版本不符：需要 3.9~3.13 的 64 位版本，当前是 %s"
            % sys.version.split()[0])
        say("请到 https://www.python.org/downloads/ 安装后重试。")
        return 2

    # 不在项目 venv 里 → 先建 venv，再用 venv 解释器重跑自己，保证依赖装对位置
    if (os.environ.get(MARKER) != "1"
            and os.path.abspath(sys.executable) != os.path.abspath(VENV_PY)):
        if not ensure_venv():
            return 2
        env = dict(os.environ)
        env[MARKER] = "1"
        return run([VENV_PY, os.path.abspath(__file__)] + args, env=env).returncode

    if not setup(sys.executable):
        return 2
    if "--setup" in args:
        say("环境已就绪。运行 python3 tunshuo_pet_pro.py 或再跑一次 bootstrap.py 即可启动。")
        return 0
    return 0 if launch(sys.executable) else 2


if __name__ == "__main__":
    sys.exit(main())

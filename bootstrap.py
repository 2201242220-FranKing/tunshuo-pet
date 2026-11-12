#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 一键环境准备 + 启动（macOS / Windows / Linux 通用）

    python3 bootstrap.py             # 补依赖并后台启动（命令立即返回）
    python3 bootstrap.py --setup     # 只补依赖，不启动
    python3 bootstrap.py --check     # 只读体检：不建 venv、不装包、不写文件
    python3 bootstrap.py --fix-certs # 显式修复本机 Python 根证书（仅体检报 CERT_MISSING 时）

做六件事：
  1. 校验 Python 版本（3.9~3.13，64 位）
  2. 缺 .venv 就建；当前不在虚拟环境里就用 .venv 的解释器重新执行自己
  3. 缺 PySide6 / Pillow 就自动 pip install -r requirements.txt
  4. 做一次只读 HTTPS 探活，检查本机 Python 能否验证论坛证书
  5. 调用 make_shortcut.py，本机动生成桌面 / 应用启动图标（幂等、失败不影响安装）
  6. 后台启动 tunshuo_pet_pro.py（Windows 用 pythonw，不弹黑窗）

全程不需要用户回答任何问题。不写 config.json、不写令牌；只读访问 PyPI、
论坛公开接口与已有 git 远端。图标只在本机创建，已存在就跳过，绝不覆盖或删除用户文件。

证书修复是**显式命令**，不会在安装流程里自动执行（不擅自改动用户本机 Python 安装）；
agent 在体检输出里看到 CERT_MISSING 时，按 AGENTS.md 执行 --fix-certs 即可。
"""

import json
import os
import subprocess
import sys
import urllib.request

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
CONFIG = os.path.join(APP_DIR, "config.json")
DEFAULT_BASE = "https://alumni.qiyuanheshan.com"
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


def _diagnose_module():
    """复用 diagnose.py 里的纯函数；import 本身不联网、不写盘。"""
    try:
        if APP_DIR not in sys.path:
            sys.path.insert(0, APP_DIR)
        import diagnose
        return diagnose
    except Exception:
        return None


def cert_probe(timeout=6):
    """只读一次 HTTPS 探活，判断本机 Python 能否验证论坛证书。

    返回 (state, detail)：OK / CERT_MISSING / UNKNOWN。
    网络不通或超时只报 UNKNOWN，绝不误判成证书问题。
    """
    base = DEFAULT_BASE
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            base = str(json.load(f).get("forum_base") or base).strip().rstrip("/")
    except Exception:
        pass
    url = base + "/app/dynamic/page?pageNum=1&pageSize=1&type=dynamic"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet-Bootstrap/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(256)
        return "OK", "HTTPS 证书校验通过"
    except Exception as e:
        s = str(e).lower()
        if "certificate" in s or "cafile" in s or ("ssl" in s and "verify" in s):
            return "CERT_MISSING", str(e)[:160]
        return "UNKNOWN", str(e)[:120]


def report_cert():
    """打印证书体检结果；CERT_MISSING 时给出 agent 可直接执行的动作。"""
    dg = _diagnose_module()
    if dg:
        try:
            flag, path, detail = dg.certificate_state()
            say("证书文件  ：%s%s" % (path or "（由系统提供）",
                                  "" if flag == "OK" else "  ← %s" % detail))
        except Exception:
            pass
    state, detail = cert_probe()
    if state == "OK":
        say("证书链    ：正常（HTTPS 校验通过）")
    elif state == "CERT_MISSING":
        say("证书链    ：CERT_MISSING 本机 Python 缺根证书 → 刷新会失败")
        say("            %s" % detail[:120])
        say("ACTION_REQUIRED：执行 python3 bootstrap.py --fix-certs"
            "（Windows 用 py -3 bootstrap.py --fix-certs）")
        say("            修完从托盘退出并重启小豚；.venv 不用重建，也不改项目依赖。")
    else:
        say("证书链    ：本次未能验证（%s），不影响安装；可稍后跑 python3 diagnose.py"
            % detail[:80])
    return state


def fix_certs():
    """显式修复入口：找到 macOS python.org 官方脚本才执行，之后复检。

    不在安装流程里自动调用，避免擅自修改用户本机 Python 安装。
    """
    dg = _diagnose_module()
    script = dg.find_install_certificates_script() if dg else ""
    if not script:
        say("CERT_FIX_NOT_FOUND 未找到 Python 官方 Install Certificates.command。")
        say("手工修复：运行 /Applications/Python 3.x/Install Certificates.command"
            "（macOS python.org 版 Python）")
        say("或经用户同意后 pip install certifi，把 SSL_CERT_FILE 指向 certifi.where()。")
        say("Windows / Linux 一般不会出现此问题；如确有，请跑 python3 diagnose.py 看分类建议。")
        return 1
    say("将执行 Python 官方证书脚本：%s" % script)
    cmd = [script] if os.access(script, os.X_OK) else ["/bin/sh", script]
    try:
        r = subprocess.run(cmd, cwd=APP_DIR, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=180, text=True)
        for line in (r.stdout or "").strip().splitlines()[-3:]:
            say("  " + line)
        if r.returncode != 0:
            say("CERT_FIX_FAILED 官方脚本返回 %d，请把上面的输出发给维护者。" % r.returncode)
            return 1
    except Exception as ex:
        say("CERT_FIX_FAILED 执行失败：%s" % str(ex)[:160])
        say("可手工运行：\"%s\"" % script)
        return 1
    state, detail = cert_probe()
    if state == "OK":
        say("CERT_FIX_OK 证书已修复，HTTPS 校验通过。从托盘退出并重启小豚即可。")
        return 0
    say("CERT_FIX_UNVERIFIED 脚本已执行，但复检仍为 %s：%s" % (state, detail[:120]))
    say("请跑 python3 diagnose.py 看完整建议。")
    return 1


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


def ensure_shortcut():
    """best-effort：生成本机启动图标。图标失败绝不能让安装或启动失败。"""
    try:
        r = run([sys.executable, os.path.join(APP_DIR, "make_shortcut.py")],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=90, text=True)
        lines = (r.stdout or "").strip().splitlines()
        keys = ("SHORTCUT_", "已在桌面", "桌面快捷方式", "应用图标", "桌面图标",
                "生成 .app 失败", "快捷方式创建失败")
        for line in [x for x in lines if x.startswith(keys)][-6:]:
            say("  " + line)
        return r.returncode == 0
    except Exception as ex:
        say("启动图标生成跳过：%s（可手动跑 python3 make_shortcut.py）" % str(ex)[:100])
        return False


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
    say("以后可直接双击桌面 / 应用里的「豚说小豚」图标启动，不用再开终端。")
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
    cert_state = report_cert()
    if not python_ok():
        say("结论      ：Python 版本不符，需要 3.9~3.13 的 64 位 Python")
        return 1
    if cert_state == "CERT_MISSING":
        say("结论      ：ENV_CERT_MISSING 依赖已就绪，但本机 Python 缺根证书；"
            "先执行 python3 bootstrap.py --fix-certs 再启动")
        return 1
    say("结论      ：%s" % ("ENV_OK 环境已就绪" if ok else "ENV_MISSING 需要补齐依赖"))
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if "--check" in args:
        return check_only()
    if "--fix-certs" in args:
        return fix_certs()
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
    report_cert()
    ensure_shortcut()
    if "--setup" in args:
        say("环境已就绪。双击桌面 / 应用里的「豚说小豚」图标，或再跑一次 bootstrap.py 即可启动。")
        return 0
    return 0 if launch(sys.executable) else 2


if __name__ == "__main__":
    sys.exit(main())

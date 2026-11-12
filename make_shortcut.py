#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 自动生成桌面 / 应用启动图标（macOS / Windows / Linux）

    python3 make_shortcut.py            # 幂等创建；已存在就跳过，不覆盖、不删除
    python3 make_shortcut.py --check    # 只报告会做什么，完全不写盘

设计原则：
  - 只用标准库 + 系统自带能力（macOS make_app.py / Windows PowerShell COM /
    Linux .desktop）；不新增依赖、不下载任何东西、不引入新框架。
  - 图标在**本机生成**，指向本机源码目录与本机 Python，绝不拷别人的 .app / .exe。
  - 幂等：目标已存在就跳过；版本变化才会重建 macOS .app；失败不影响桌宠启动。

对方 agent 不需要调用本脚本：`bootstrap.py` 在 `--setup` 与默认启动流程里会自动
best-effort 调用一次。手动重跑可修复被误删的图标。
"""

import base64
import os
import plistlib
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "豚说小豚"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")


def say(*parts):
    print(*parts, flush=True)


def read_version():
    try:
        with open(os.path.join(APP_DIR, "VERSION"), "r", encoding="utf-8") as f:
            return f.readline().strip() or "?"
    except OSError:
        return "?"


def desktop_dir():
    """桌面路径。TUNSHUO_DESKTOP_DIR 仅供离线自测重定向，正常安装不用设置。"""
    override = os.environ.get("TUNSHUO_DESKTOP_DIR")
    if override:
        return override
    if IS_WIN:
        return None                      # 由 PowerShell 问系统要，兼容 OneDrive 重定向
    return os.path.expanduser("~/Desktop")


def make_icon_win():
    """用已有的 Pillow 把 pet.png 转成 .ico，失败则退回解释器自带图标。"""
    out = os.path.join(APP_DIR, "build", "pet.ico")
    try:
        from PIL import Image
        os.makedirs(os.path.dirname(out), exist_ok=True)
        img = Image.open(os.path.join(APP_DIR, "assets", "pet.png")).convert("RGBA")
        img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return out
    except Exception:
        return ""                        # 图标是锦上添花，不能让安装失败


def ps_str(value):
    """PowerShell 单引号字符串（单引号双写即可，路径里的中文/空格都安全）。"""
    return "'" + str(value).replace("'", "''") + "'"


def build_mac(check=False):
    """macOS：生成 ~/Applications/豚说小豚.app，并在桌面放一个符号链接。"""
    import make_app

    app_path = os.path.join(make_app.INSTALL_DIR, make_app.APP_NAME)
    plist = os.path.join(app_path, "Contents", "Info.plist")
    version = read_version()
    installed_version = ""
    try:
        with open(plist, "rb") as f:
            installed_version = str(plistlib.load(f).get("CFBundleShortVersionString") or "")
    except Exception:
        pass

    need_build = not os.path.isdir(app_path) or installed_version != version
    link = os.path.join(desktop_dir(), make_app.APP_NAME)
    say("应用图标  ：%s%s" % (app_path,
                              "（需生成）" if need_build else "（已是 v%s）" % version))
    say("桌面图标  ：%s%s" % (link, "（已存在，跳过）" if os.path.lexists(link) else "（需创建）"))
    if check:
        return True

    if need_build:
        try:
            app_path = make_app.build()
        except Exception as e:
            say("生成 .app 失败：%s（不影响桌宠运行）" % str(e)[:120])
            return False

    if os.path.lexists(link):
        return True                      # 不覆盖、不删除用户桌面上的任何东西
    if not os.path.isdir(desktop_dir()):
        say("桌面目录不存在，跳过桌面图标；可从启动台 / ~/Applications 打开。")
        return True
    try:
        os.symlink(app_path, link)
        say("已在桌面创建启动图标。")
    except OSError as e:
        say("桌面图标创建失败：%s（不影响 ~/Applications 里的 .app）" % str(e)[:120])
    return True


def build_win(check=False):
    """Windows：用系统自带 PowerShell 的 WScript.Shell 创建桌面 .lnk。"""
    venv_pyw = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
    venv_py = os.path.join(APP_DIR, ".venv", "Scripts", "python.exe")
    target = next((p for p in (venv_pyw, venv_py, sys.executable) if os.path.isfile(p)),
                  sys.executable)
    bootstrap = os.path.join(APP_DIR, "bootstrap.py")
    icon = make_icon_win() if not check else ""
    lnk_name = APP_NAME + ".lnk"
    say("快捷方式  ：桌面 / %s" % lnk_name)
    say("启动目标  ：%s bootstrap.py" % target)
    if check:
        return True

    # -EncodedCommand 传 UTF-16LE，中文快捷方式名与中文路径都不会乱码；
    # 不写 .ps1 文件，不依赖 PyInstaller 或任何第三方工具。
    ps = """
$ErrorActionPreference = 'Stop'
$desktop = %s
$lnk = Join-Path $desktop %s
if (Test-Path -LiteralPath $lnk) {
  Write-Output 'SKIP'
} else {
  $w = New-Object -ComObject WScript.Shell
  $s = $w.CreateShortcut($lnk)
  $s.TargetPath = %s
  $s.Arguments = %s
  $s.WorkingDirectory = %s
  $s.IconLocation = %s
  $s.Description = %s
  $s.Save()
  Write-Output 'OK'
}
""" % (ps_str(desktop_dir()) if desktop_dir()
       else "[Environment]::GetFolderPath('Desktop')",
       ps_str(lnk_name), ps_str(target), ps_str('"%s"' % bootstrap),
       ps_str(APP_DIR), ps_str(icon or target), ps_str("豚说小豚 桌宠"))
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", encoded],
                           cwd=APP_DIR, capture_output=True, text=True, timeout=45)
        out = (r.stdout or "").strip()
        if r.returncode == 0 and ("OK" in out or "SKIP" in out):
            say("桌面快捷方式：%s" % ("已存在，跳过" if "SKIP" in out else "已创建"))
            return True
        say("快捷方式创建失败：%s" % ((out or r.stderr or "").strip()[:160]))
    except Exception as e:
        say("快捷方式创建失败：%s" % str(e)[:160])
    say("不影响使用：双击 start_windows.bat 或运行 py -3 bootstrap.py 一样能启动。")
    return False


def build_linux(check=False):
    """Linux：桌面 + 应用菜单各放一个 .desktop（标准 freedesktop 写法）。"""
    py = os.path.join(APP_DIR, ".venv", "bin", "python")
    if not os.path.isfile(py):
        py = sys.executable
    icon = os.path.join(APP_DIR, "assets", "pet.png")
    content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=" + APP_NAME,
        "Comment=豚说校园论坛桌面宠物",
        'Exec="%s" "%s"' % (py, os.path.join(APP_DIR, "bootstrap.py")),
        "Path=" + APP_DIR,
        "Icon=" + icon,
        "Terminal=false",
        "Categories=Utility;",
        "",
    ])
    targets = []
    d = desktop_dir()
    if os.path.isdir(d):
        targets.append(os.path.join(d, APP_NAME + ".desktop"))
    menu = os.path.expanduser("~/.local/share/applications")
    targets.append(os.path.join(menu, APP_NAME + ".desktop"))
    for t in targets:
        say("启动图标  ：%s%s" % (t, "（已存在，跳过）" if os.path.exists(t) else "（需创建）"))
    if check:
        return True
    ok = True
    for t in targets:
        if os.path.exists(t):
            continue
        try:
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with open(t, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(t, 0o755)
        except OSError as e:
            say("写入失败 %s：%s" % (t, str(e)[:100]))
            ok = False
    return ok


def main():
    check = "--check" in sys.argv[1:]
    say("豚说小豚 · 启动图标（v%s，%s）" % (read_version(), sys.platform))
    say("-" * 52)
    try:
        if IS_MAC:
            ok = build_mac(check)
        elif IS_WIN:
            ok = build_win(check)
        else:
            ok = build_linux(check)
    except Exception as e:
        say("启动图标生成跳过：%s（不影响桌宠运行）" % str(e)[:160])
        return 0                          # best-effort：绝不因为图标让安装失败
    say("SHORTCUT_%s" % ("CHECK_OK" if check else ("OK" if ok else "PARTIAL")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豚说小豚 · 拉取失败一键诊断

只读、不写文件、不改 config.json、不新增依赖、不打印任何令牌值。
依次检查：运行环境（含代理 / VPN）→ DNS → 一次 HTTPS 请求 → 一次真实聚合拉取。
检测到代理且默认请求失败时，会额外做一次「绕过代理直连」对照，直接判定是不是 VPN 导致。

用法：
    python3 diagnose.py
    .venv/bin/python diagnose.py          # Windows 用 .venv/Scripts/python.exe
    python3 diagnose.py --selftest        # 只测错误分类，完全不联网

最后一行一定是 DIAGNOSIS_OK 或 DIAGNOSIS_FAIL，并附带可直接照做的修复建议。
把完整输出复制给维护者即可定位，不需要截图气泡。
"""

import json
import os
import platform
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DEFAULT_BASE = "https://alumni.qiyuanheshan.com"


def mask_proxy(value):
    """代理地址可能带账号密码，只打印主机部分。"""
    return re.sub(r"(?<=://)[^/@]+@", "***@", str(value))


def proxy_state(host):
    """返回 (是否对该域名生效, 生效代理字典, 环境变量名列表)。

    Python 的 urlopen 会自动继承 HTTP_PROXY / HTTPS_PROXY（macOS 还会读系统
    代理设置，Windows 还会读注册表），VPN 客户端常常就是改这几处。
    """
    env_names = sorted(k for k in os.environ
                       if k.lower().endswith("_proxy") and k.lower() != "no_proxy"
                       and os.environ[k].strip())
    try:
        proxies = urllib.request.getproxies() or {}
    except Exception:
        proxies = {}
    try:
        bypassed = bool(urllib.request.proxy_bypass(host))
    except Exception:
        bypassed = False
    active = bool(proxies) and not bypassed
    return active, proxies, env_names


def direct_probe(url, timeout):
    """绕过代理做一次只读直连对照；只影响本进程，不改系统设置或配置。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet-Diagnose/1.0"})
    with opener.open(req, timeout=timeout) as r:
        return r.status, r.read(512)


def classify(msg, has_proxy=False, direct_ok=False):
    """把底层异常归成一句人话 + 一组可执行的修复建议。"""
    s = str(msg or "").lower()          # 失败路径传进来的是异常对象，不是字符串
    if direct_ok or (has_proxy and any(k in s for k in (
            "proxy", "407", "connection refused", "tunnel connection failed",
            "timed out", "timeout", "getaddrinfo", "nodename"))):
        return "代理 / VPN 网络环境", [
            "当前开着代理或 VPN，Python 会自动继承它；论坛域名走代理后不通，"
            "4 所学校全部失败才会整体提示「拉取失败」。",
            "最快验证：退出 VPN 或把代理切到直连 / 换一个节点，再跑一次 python3 diagnose.py。",
            "必须开代理时：把该域名加入代理软件的直连 / 白名单规则，"
            "或设置环境变量 NO_PROXY=alumni.qiyuanheshan.com 后重启小豚。",
            "若代理做了 HTTPS 证书替换，会表现为证书错误；同样先排除代理，"
            "不要关闭证书校验（verify=False），也不要改 config.json。",
        ]
    if "certificate" in s or "ssl" in s or "cafile" in s:
        return "证书验证失败", [
            "浏览器能打开、Python 打不开，通常是本机 Python 缺根证书，不是论坛挂了。",
            "macOS 若用 python.org 安装包：运行 /Applications/Python 3.x/Install Certificates.command，然后重建 .venv。",
            "通用做法：pip install certifi，再设环境变量 SSL_CERT_FILE 指向 certifi.where() 后重启小豚。",
            "不要改成关闭证书校验（verify=False），会牺牲安全性。",
        ]
    if "timed out" in s or "timeout" in s:
        return "请求超时", [
            "网络慢或校园网/公司网有拦截，稍后重试一次。",
            "确认浏览器能打开论坛地址；能开但这里超时，检查是否走代理。",
            "可在 config.json 把 forum_timeout 调到 30（上限 30）后重启小豚。",
        ]
    if "getaddrinfo" in s or "nodename" in s or "nameresolution" in s or "name or service" in s:
        return "域名解析失败", [
            "当前网络解析不了论坛域名：换一个网络（如手机热点）再试。",
            "检查 DNS、代理、hosts 是否被改过；公司/校园网可能拦截该域名。",
            "浏览器也打不开 = 网络或服务端问题，不是桌宠的问题。",
        ]
    if "proxy" in s or "407" in s:
        return "代理设置问题", [
            "检查系统代理与 HTTP_PROXY / HTTPS_PROXY 环境变量是否指向可用代理。",
            "临时关掉代理再跑一次本诊断，确认是不是代理导致的。",
        ]
    if "http 4" in s or "http 5" in s or "connection refused" in s or "forbidden" in s:
        return "服务端或防火墙拒绝", [
            "论坛返回了错误状态或被本机防火墙拦截，稍后重试。",
            "把本诊断的完整输出发给维护者，附上你所在的地区和网络环境。",
        ]
    return "其他错误", [
        "把本诊断的完整输出复制给维护者（不要截图气泡，气泡会被截断）。",
        "同时提供 logs/pet.log 的最后几行，里面有完整异常。",
    ]


def _fail(detail, base, has_proxy=False, direct_ok=False):
    reason, tips = classify(detail, has_proxy=has_proxy, direct_ok=direct_ok)
    print("-" * 56)
    if direct_ok:
        print("结论      ：绕过代理可访问 → 确认是代理 / VPN 导致，不是论坛或桌宠故障")
    print("DIAGNOSIS_FAIL %s" % reason)
    print("原始错误：%s" % str(detail)[:300])
    print("\n建议按顺序尝试：")
    for i, tip in enumerate(tips, 1):
        print("  %d. %s" % (i, tip))
    if reason == "代理 / VPN 网络环境":
        print("\n注意：桌宠本身已内置「代理失败自动直连重试」，所以即便这里判定代理不通，"
              "桌宠刷新仍可能正常出榜——本诊断如实反映网络环境，不影响使用。")
    print("\n快速二分：用浏览器打开 %s" % base)
    print("浏览器能开但这里失败 = 本机 Python / 证书 / 代理问题；浏览器也开不了 = 网络或服务端问题。")
    return 1


def _selftest():
    # (错误文本, 期望分类, 是否检测到代理, 直连对照是否成功)
    cases = [
        ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "证书验证失败", False, False),
        ("timed out", "请求超时", False, False),
        ("[Errno 8] nodename nor servname provided", "域名解析失败", False, False),
        ("ProxyError: Cannot connect to proxy", "代理设置问题", False, False),
        ("接口 HTTP 502", "服务端或防火墙拒绝", False, False),
        ("一些没见过的异常", "其他错误", False, False),
        ("<urlopen error [Errno 61] Connection refused>", "代理 / VPN 网络环境", True, False),
        ("timed out", "代理 / VPN 网络环境", True, False),
        ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "代理 / VPN 网络环境", True, True),
        ("接口 HTTP 502", "代理 / VPN 网络环境", False, True),
    ]
    ok = 0
    for msg, want, has_proxy, direct_ok in cases:
        got = classify(msg, has_proxy=has_proxy, direct_ok=direct_ok)[0]
        if got == want:
            ok += 1
        else:
            print("  FAIL %s（proxy=%s direct=%s）-> %s（期望 %s）"
                  % (msg, has_proxy, direct_ok, got, want))
    # 代理地址脱敏 + 失败路径传异常对象（而不是字符串）不能崩
    extra = [
        (mask_proxy("http://user:pwd@127.0.0.1:7890") == "http://***@127.0.0.1:7890",
         "mask_proxy 未脱敏"),
        (classify(urllib.error.URLError("Connection refused"),
                  has_proxy=True)[0] == "代理 / VPN 网络环境",
         "异常对象未正确分类"),
    ]
    for good, label in extra:
        if good:
            ok += 1
        else:
            print("  FAIL %s" % label)
    total = len(cases) + len(extra)
    print("DIAGNOSE_SELFTEST_OK %d/%d" % (ok, total))
    return 0 if ok == total else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()

    print("豚说小豚 · 拉取失败诊断（只读，不写盘）")
    print("-" * 56)
    print("平台      ：%s %s" % (platform.system(), platform.release()))
    print("Python    ：%s" % platform.python_version())
    print("解释器    ：%s" % sys.executable)
    try:
        print("证书链    ：%s" % (ssl.get_default_verify_paths().cafile or "（由系统提供）"))
    except Exception as e:
        print("证书链    ：读取失败 %s" % e)

    cfg = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        print("配置      ：读取成功")
    except Exception as e:
        print("配置      ：读取失败 %s（将用默认地址继续）" % e)

    base = str(cfg.get("forum_base") or DEFAULT_BASE).strip().rstrip("/")
    circles = cfg.get("forum_circles") or []
    try:
        timeout = max(3, min(30, float(cfg.get("forum_timeout") or 15)))
    except (TypeError, ValueError):
        timeout = 15
    print("论坛地址  ：%s" % base)
    print("监控圈子  ：%d 所" % len(circles))
    print("超时设置  ：%g 秒" % timeout)
    host = urllib.parse.urlparse(base).hostname or ""
    proxy_active, proxies, env_names = proxy_state(host)
    direct_ok = False
    if proxies:
        pairs = ["%s=%s" % (k, mask_proxy(proxies[k]))
                 for k in ("https", "http") if proxies.get(k)]
        source = ("，环境变量 %s" % ", ".join(env_names)) if env_names else "，来自系统代理设置"
        print("代理      ：%s%s" % (", ".join(pairs) or "（已设置）", source))
        print("直连规则  ：%s" % ("该域名在绕过列表内，不走代理" if not proxy_active
                                else "该域名会走代理（VPN 开启时常见）"))
    else:
        print("代理      ：未检测到（直连）")
    print("令牌      ：%s" % ("环境变量已设置（值不打印）"
                            if os.environ.get("TUNSHUO_FORUM_TOKEN") else "未使用，匿名只读"))
    print("-" * 56)

    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})[:3]
        print("DNS       ：OK %s -> %s" % (host, ", ".join(ips)))
    except Exception as e:
        print("DNS       ：FAIL %s" % e)
        return _fail(e, base, has_proxy=proxy_active)

    first = circles[0] if circles and isinstance(circles[0], dict) else {}
    circle_id = str(first.get("id") or cfg.get("forum_circle_id") or "")
    q = {"pageNum": 1, "pageSize": 1, "type": "dynamic"}
    if circle_id:
        q["circleId"] = circle_id
    url = base + "/app/dynamic/page?" + urllib.parse.urlencode(q)
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet-Diagnose/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, body = r.status, r.read(2048)
        print("HTTPS     ：OK HTTP %d，%.2fs，%d 字节"
              % (status, time.monotonic() - t0, len(body)))
    except Exception as e:
        print("HTTPS     ：FAIL %s" % e)
        if proxy_active:
            try:
                status, _ = direct_probe(url, timeout)
                direct_ok = status == 200
                print("直连对照  ：OK HTTP %d（绕过代理可以访问）" % status)
            except Exception as e2:
                print("直连对照  ：FAIL %s（代理不是唯一原因）" % str(e2)[:120])
        return _fail(e, base, has_proxy=proxy_active, direct_ok=direct_ok)

    try:
        import forum_api as fa
        adapter = fa.ForumAdapter(cfg)
        posts = adapter.fetch()
        print("聚合拉取  ：OK %d 条" % len(posts))
        if adapter.last_warning:
            print("降级提示  ：%s" % str(adapter.last_warning)[:140])
    except Exception as e:
        print("聚合拉取  ：FAIL %s" % e)
        return _fail(e, base, has_proxy=proxy_active, direct_ok=direct_ok)

    print("-" * 56)
    print("DIAGNOSIS_OK 论坛接口可正常访问。")
    print("若桌宠仍提示拉取失败：退出小豚后重启一次，并把 logs/pet.log 最后几行发给维护者。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

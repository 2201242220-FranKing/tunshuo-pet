#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说小豚 · 面板、播报与拉取失败提示离线自测（45 项）。

  python3 selftest_panel.py

检查「最新 / 最热」切换、时间解析、榜单渲染、新帖播报与单击播报口径。
与 forum_api.py --selftest 一样：不联网、不读配置、不写任何文件、不发通知；
用离屏 QApplication 把真实的 HotPanel 创建出来检查，不会在桌面弹窗、不会打扰
正在运行的桌宠。改过排序或播报文案后跑一遍即可确认没有回归。
"""

import os
import sys
import unittest.mock as mock_lib

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QLabel
    import tunshuo_pet_pro as m
except ImportError as e:
    sys.exit("缺少依赖，请先执行：pip install -r requirements.txt\n%s" % e)

app = QApplication([])
ok = 0


def check(name, cond, extra=""):
    global ok
    assert cond, "FAIL %s %s" % (name, extra)
    ok += 1
    print("  OK  %s" % name)


def meta_text(panel, i):
    item = panel.list.item(i)
    w = panel.list.itemWidget(item)
    return w.findChildren(QLabel)[1].text()


print("1) 时间解析与展示")
check("真实绝对时间可直接排序", m.post_time_key("2026-11-10 13:04:24") == "2026-11-10 13:04:24")
check("缺秒补零", m.post_time_key("2026-11-10 13:04") == "2026-11-10 13:04:00")
check("斜杠 + 个位月日", m.post_time_key("2026/11/9 9:03:07") == "2026-11-09 09:03:07")
check("纯日期", m.post_time_key("2026-11-10") == "2026-11-10 00:00:00")
check("相对时间不参与排序", m.post_time_key("5分钟前") == "")
check("相对串原样展示", m.short_post_time("5分钟前") == "5分钟前")
check("绝对时间压成短格式", m.short_post_time("2026-11-10 13:04:24") == "11-10 13:04")
check("空值不崩", m.post_time_key("") == "" and m.short_post_time(None) == "")
check("带时区也能解析", m.post_time_key("2026-11-10T13:04:24+08:00") != "")
check("脏数据不崩", m.post_time_key("not a time") == "")

posts = [
    {"id": "a", "title": "甲校旧帖热度很高", "author": "甲", "tag": "浙外·活动",
     "heat": 900, "time": "2026-11-10 09:00:00", "url": None},
    {"id": "b", "title": "甲校刚发的新帖", "author": "甲", "tag": "浙外·求助",
     "heat": 5, "time": "2026-11-11 17:30:00", "url": None},
    {"id": "c", "title": "乙校昨天的帖子", "author": "乙", "tag": "浙工大·二手",
     "heat": 400, "time": "2026-11-10 20:00:00", "url": None},
    {"id": "d", "title": "演示相对时间帖", "author": "丙", "tag": "活动",
     "heat": 700, "time": "5分钟前", "url": None},
]

print("2) 面板默认行为零回归")
panel = m.HotPanel(None, lambda: None)
panel.set_posts(posts)
check("默认模式是最热", panel.mode == "hot")
check("默认标题是热帖榜", panel.title.text() == "豚说 · 热帖榜")
check("最热按 heat 降序", [p["id"] for p in panel.posts] == ["a", "d", "c", "b"],
      str([p["id"] for p in panel.posts]))
check("渲染出 4 行", panel.list.count() == 4)
check("最热 meta 仍是热度", "热度 900" in meta_text(panel, 0))
check("最热 tab 选中", panel.tab_hot.isChecked() and not panel.tab_new.isChecked())

print("3) 切到最新")
panel.set_mode("new")
check("模式与标题切换", panel.mode == "new" and panel.title.text() == "豚说 · 最新动态")
check("最新按时间降序（跨学校重排）",
      [p["id"] for p in panel.posts] == ["b", "c", "a", "d"],
      str([p["id"] for p in panel.posts]))
check("最新 meta 显示时间", "11-11 17:30" in meta_text(panel, 0), meta_text(panel, 0))
check("最新 meta 不挤热度", "热度" not in meta_text(panel, 0))
check("相对时间帖沉底", "5分钟前" in meta_text(panel, 3))
check("最新 tab 选中", panel.tab_new.isChecked() and not panel.tab_hot.isChecked())
check("原始批次未被破坏", [p["id"] for p in panel.raw_posts] == ["a", "b", "c", "d"])

print("4) 切回 / 重复切换 / 演示数据")
panel.set_mode("hot")
check("切回最热恢复热度序", [p["id"] for p in panel.posts] == ["a", "d", "c", "b"])
panel.set_mode("hot")
check("重复切同一模式无副作用", panel.list.count() == 4)
panel.set_mode("nonsense")
check("非法模式被忽略", panel.mode == "hot")
mock_posts = [{"id": str(i), "title": "演示帖%d" % i, "author": "甲", "tag": "活动",
               "heat": 100 - i, "time": "%d分钟前" % i, "url": None} for i in range(4)]
panel.set_posts(mock_posts)
panel.set_mode("new")
check("演示数据最新模式保持拉取顺序不乱跳",
      [p["id"] for p in panel.posts] == ["0", "1", "2", "3"],
      str([p["id"] for p in panel.posts]))

print("5) 新帖播报口径")
new = posts[:3]
top = max(new, key=lambda p: m.post_time_key(p.get("time")))
check("播报取时间最新而非热度最高", top["id"] == "b" and top["heat"] == 5, top["id"])
check("气泡时间展示可用", m.short_post_time(top.get("time")) == "11-11 17:30")

print("6) 真实 _on_posts 代码路径")


class FakePanel:
    def isVisible(self):
        return False

    def set_posts(self, posts):
        pass


class FakePet:
    _on_posts = m.PetWindow._on_posts
    on_click = m.PetWindow.on_click
    _on_fetch_fail = m.PetWindow._on_fetch_fail

    def __init__(self):
        self.seen = set()
        self.rig = None
        self._press_local = None
        self._click_times = []
        self.studio = {"settings": {"phrases": ["随便一句"]}}
        self.first_load = False
        self.paused = False
        self.panel = FakePanel()
        self.sleeping = False
        self.said = []
        self.notified = []
        self.on_event = lambda name: False
        self.play = lambda name: None
        self.say = lambda text, ms=6200: self.said.append(text)
        self._notify = lambda title, msg: self.notified.append(msg)


pet = FakePet()
pet._on_posts(posts[:3])
check("气泡播报的是时间最新那条", "甲校刚发的新帖" in pet.said[0], pet.said[0])
check("气泡显示时间、不再显示热度",
      "11-11 17:30" in pet.said[0] and "热度" not in pet.said[0], pet.said[0])
check("系统通知也带时间", "11-11 17:30" in pet.notified[0], pet.notified[0])
check("seen 去重逻辑未受影响", len(pet.seen) == 3)

print("7) 单击播报口径（真实 on_click 代码路径）")
click_pet = FakePet()
click_pet.posts = posts
with mock_lib.patch.object(m.random, "random", return_value=0.1):
    click_pet.on_click()
check("单击播报时间最新那条", "甲校刚发的新帖" in click_pet.said[-1], click_pet.said[-1])
check("单击文案不再提最火/热度",
      "最火" not in click_pet.said[-1] and "热度" not in click_pet.said[-1])
check("单击文案显示时间与作者",
      "11-11 17:30" in click_pet.said[-1] and "甲" in click_pet.said[-1])

print("8) 拉取失败提示（真实 _on_fetch_fail 代码路径）")
import contextlib
import io

fail_pet = FakePet()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    fail_pet._on_fetch_fail("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
check("气泡给出归类后的人话", "证书验证失败" in fail_pet.said[-1], fail_pet.said[-1])
check("气泡指引跑诊断脚本", "diagnose.py" in fail_pet.said[-1])
check("气泡不再塞完整英文异常", "CERTIFICATE_VERIFY_FAILED" not in fail_pet.said[-1])
check("完整原因写进日志", "CERTIFICATE_VERIFY_FAILED" in buf.getvalue())
check("分类：超时", m._failure_hint("timed out") == "请求超时")
check("分类：DNS", m._failure_hint("[Errno 8] nodename nor servname provided") == "连不上论坛（DNS）")
check("分类：代理", m._failure_hint("ProxyError") == "代理设置问题")
check("分类：HTTP 异常", m._failure_hint("接口 HTTP 502") == "论坛接口异常")
check("分类：兜底", m._failure_hint("没见过的异常") == "连不上论坛")

print("\nSELFTEST_PANEL_OK %d 项通过" % ok)

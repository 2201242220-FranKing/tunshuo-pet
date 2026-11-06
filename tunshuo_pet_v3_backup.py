#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豚说小豚 · 桌面宠物 v3（PySide6）
==================================
形象：豚说官方 IP 蓝色小鲸鱼（ψ）

v3 关键改动：
  1. 【不再抢焦点】气泡不再新建窗口，改为在宠物窗口内部绘制；
     窗口带 WindowDoesNotAcceptFocus + WA_ShowWithoutActivating，
     新帖提醒时不会打断你正在输入的任何应用。
  2. 形象换成官方 IP，透明精灵图 + 眨眼帧。
  3. alpha mask：只有角色轮廓区域接收鼠标，透明区域点击穿透到桌面。

交互：
  单击  → 晃一晃 + 气泡播报最热帖
  双击  → 热帖榜卡片
  右键  → 菜单（热帖 / 刷新 / 暂停提醒 / 退出）
  拖拽  → 移动位置
"""

import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.request

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF,
                            QSize, Qt, QThread, QTimer, QVariantAnimation,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(APP_DIR, "assets")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_url": "",
    "auto_poll": False,        # 关闭自动轮询：不再定时拉取/弹提醒
    "poll_interval_minutes": 3,
    "notify_system": True,
    "pet_width": 120,
}

MOCK_POOL = [
    "【闲置】出一台9成新iPad Air5，带笔，可小刀",
    "周三晚操场音乐会，有人组队一起去吗",
    "考研自习室占座攻略（附各楼层开放时间表）",
    "校园卡食堂充值满50送10，最后三天，冲！",
    "拼车回杭州，周六早上8点东门出发，还差2人",
    "求推荐校内打印哪家便宜又快",
    "校运会报名最后一天，4x100还缺一个女生",
    "二手教材免费送，期末了大家加油",
    "表白墙#2048：操场穿蓝色外套打羽毛球的男生",
    "失物招领：捡到一卡通一张，在二食堂门口",
    "今晚球馆免费开放，篮球3v3缺人，速来",
    "宿舍空调清洗拼单还差2人，人均立省30",
    "四六级准考证打印通道已开放，别忘了",
    "新开的奶茶店第二杯半价，测评来了",
]
MOCK_AUTHORS = ["阿豚不吃香菜", "图书馆钉子户", "4点睡的秃头人", "食堂评论家",
                "打工豚", "酸奶盖收藏家", "早八幸存者", "小肚腩战士"]
MOCK_TAGS = ["闲置", "活动", "学习", "优惠", "拼车", "求助", "表白", "失物"]

PHRASES = [
    "在的！有热帖我第一个告诉你～",
    "今天论坛好热闹，我蹲着呢",
    "双击我可以看热帖榜哦",
    "有新动态我会冒个泡～",
    "要不要看看闲置区？说不定有惊喜",
    "校园卡这周的优惠我帮你盯着呢",
]


# ----------------------------------------------------------------------
class DataSource:
    def __init__(self, cfg):
        self.cfg = cfg
        self.n = 0

    def fetch(self):
        url = (self.cfg.get("api_url") or "").strip()
        return self._api(url) if url else self._mock()

    def _api(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet/3.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        posts = data.get("posts") if isinstance(data, dict) else data
        out = []
        for i, p in enumerate(posts or []):
            if not isinstance(p, dict):
                continue
            out.append({
                "id": str(p.get("id", p.get("title", i))),
                "title": str(p.get("title", "(无标题)")),
                "author": str(p.get("author", "豚友")),
                "tag": str(p.get("tag", "")),
                "heat": int(p.get("heat", 0) or 0),
                "time": str(p.get("time", "")),
                "url": p.get("url"),
            })
        return out

    def _mock(self):
        self.n += 1
        posts = [{
            "id": "mock-%d-%d" % (i, random.randint(100, 999)),
            "title": random.choice(MOCK_POOL),
            "author": random.choice(MOCK_AUTHORS),
            "tag": random.choice(MOCK_TAGS),
            "heat": random.randint(30, 680),
            "time": "%d分钟前" % random.randint(2, 90),
            "url": None,
        } for i in range(8)]
        if self.n % 2 == 0:
            posts.insert(0, {
                "id": "new-%d" % time.time(),
                "title": random.choice(MOCK_POOL),
                "author": random.choice(MOCK_AUTHORS),
                "tag": random.choice(MOCK_TAGS),
                "heat": random.randint(120, 720),
                "time": "刚刚",
                "url": None,
            })
        return posts


class Fetcher(QThread):
    ok = Signal(list)
    fail = Signal(str)

    def __init__(self, source):
        super().__init__()
        self.source = source

    def run(self):
        try:
            self.ok.emit(self.source.fetch())
        except Exception as ex:
            self.fail.emit(str(ex)[:80])


# ----------------------------------------------------------------------
class PetWindow(QWidget):
    """单窗口桌宠：精灵 + 内部气泡，永不新建窗口抢焦点。"""

    BUBBLE_MAX_W = 268
    PAD = 8

    def __init__(self, cfg, source):
        super().__init__(None,
                         Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # macOS：Qt.Tool 窗口默认在 App 失去激活时自动隐藏（切到别的应用小豚就消失），
        # 这个属性强制它一直显示
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.cfg = cfg
        self.source = source
        self.posts = []
        self.seen = set()
        self.paused = False
        self.first_load = True

        # 素材
        self.pm_open = self._load("pet.png")
        self.pm_blink = self._load("pet_blink.png")
        self.blinking = False

        pet_w = self.pm_open.width()
        pet_h = self.pm_open.height()
        self.pet_w, self.pet_h = pet_w, pet_h
        # 气泡宽度随宠物大小自适应（太小则字号读不清，留可读下限）
        self.BUBBLE_MAX_W = int(max(198, min(268, pet_w * 2.7)))
        self._bubble_px = 12 if pet_w < 100 else 13
        self.win_w = max(self.BUBBLE_MAX_W + 24, pet_w + 40)
        self.bubble_h = 0            # 当前气泡高度，0 表示无气泡
        self.bubble_w = self.BUBBLE_MAX_W
        self.bubble_text = ""
        self._bubble_alpha = 0.0
        self.bubble_alpha_anim = None
        self.win_h = int(pet_h + 116)

        self.resize(self.win_w, self.win_h)
        self._pet_offset = QPoint((self.win_w - pet_w) // 2, self.win_h - pet_h)

        self.sprite_region = QRegion(self.pm_open.mask()).translated(
            self._pet_offset.x(), self._pet_offset.y())
        self._apply_mask()

        self._drag_pos = None
        self._press_at = None
        self._drag_moved = 0
        self._breath = 0.0
        self._bob = 0.0

        self.panel = HotPanel(self, self.refresh)
        self._place_bottom_right()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)

        self.blink_timer = QTimer(self)
        self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(random.randint(2800, 5600))

        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self._hide_bubble)

        QTimer.singleShot(1200, lambda: self.say("点我看看热帖～右键有菜单", 4200))

    # ---------- 素材与遮罩 ----------
    def _load(self, name):
        pm = QPixmap(os.path.join(ASSET_DIR, name))
        if pm.isNull():
            raise FileNotFoundError(os.path.join(ASSET_DIR, name))
        target_w = int(self.cfg.get("pet_width", 168))
        return pm.scaledToWidth(target_w, Qt.SmoothTransformation)

    def _apply_mask(self):
        region = QRegion(self.sprite_region)
        if self.bubble_h > 4:
            r = self._bubble_body()
            region = region.united(QRegion(QRectF(r.x(), r.y(),
                                                 r.width(), r.height() + 12).toRect()))
        self.setMask(region)

    def _bubble_body(self):
        w = self.bubble_w
        h = self.bubble_h
        x = (self.win_w - w) // 2
        y = max(2, self.win_h - self.pet_h - h - 6)
        return QRectF(x, y, w, h)

    def ensure_on_screen(self):
        """窗口被拖到屏幕外（或显示器变了）时拉回可见区域。"""
        screen = QApplication.screenAt(self.frameGeometry().center()) \
            or QApplication.primaryScreen()
        g = screen.availableGeometry()
        x = min(max(self.x(), g.left()), max(g.left(), g.right() - self.width()))
        y = min(max(self.y(), g.top()), max(g.top(), g.bottom() - self.height()))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def show_pet(self):
        self.ensure_on_screen()
        self.show()
        self._apply_mask()
        self.update()
        self.raise_()

    def hide_pet(self):
        self.hide()

    def set_pet_visible(self, visible):
        if visible:
            self.show_pet()
        else:
            self.hide_pet()

    def _place_bottom_right(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.win_w - 40, scr.bottom() - self.win_h - 10)

    # ---------- 动画 ----------
    def _tick(self):
        self._breath += 0.075
        self._bob = math.sin(self._breath) * 2.2
        self.update()

    def _blink(self):
        if not self.blinking:
            self.blinking = True
            self.update()
            QTimer.singleShot(130, self._unblink)
        self.blink_timer.start(random.randint(2600, 6200))

    def _unblink(self):
        self.blinking = False
        self.update()

    def wave(self):
        self._wave_seq = [2, -3, 2, -2, 1, 0]
        self._wave_i = 0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._wave_step)
        self._wave_timer.start(45)

    def _wave_step(self):
        if self._wave_i >= len(self._wave_seq):
            self._wave_timer.stop()
            return
        self._bob = self._wave_seq[self._wave_i] * 2.2
        self._wave_i += 1
        self.update()

    # ---------- 气泡（窗口内部绘制） ----------
    def say(self, text, ms=6200):
        self.bubble_text = text
        fm = QFontMetrics(self._bubble_font())
        rect = fm.boundingRect(0, 0, self.BUBBLE_MAX_W - 28, 600,
                               Qt.TextWordWrap | Qt.AlignLeft, text)
        self.bubble_w = max(150, min(self.BUBBLE_MAX_W, rect.width() + 30))
        self.bubble_h = min(rect.height() + 22, 96)
        self._bubble_alpha = 0.0
        self._apply_mask()
        self._fade_bubble(0.0, 1.0, 160)
        self.bubble_timer.start(ms)
        self.update()

    def _hide_bubble(self):
        self._fade_bubble(self._bubble_alpha, 0.0, 220, clear=True)

    def _fade_bubble(self, a, b, ms, clear=False):
        anim = QVariantAnimation(self)
        anim.setStartValue(float(a))
        anim.setEndValue(float(b))
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: self._set_alpha(float(v)))
        if clear:
            anim.finished.connect(self._clear_bubble)
        anim.start()
        self.bubble_alpha_anim = anim

    def _set_alpha(self, v):
        self._bubble_alpha = v
        self.update()

    def _clear_bubble(self):
        self.bubble_text = ""
        self.bubble_h = 0
        self._bubble_alpha = 0.0
        self._apply_mask()
        self.update()

    def _bubble_font(self):
        f = QFont("PingFang SC")
        f.setPixelSize(getattr(self, "_bubble_px", 13))
        return f

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self.bubble_text and self.bubble_h > 0:
            p.setOpacity(max(0.0, min(1.0, self._bubble_alpha)))
            self._paint_bubble(p)

        p.setOpacity(1.0)
        dy = int(round(self._bob))
        pm = self.pm_blink if self.blinking else self.pm_open
        p.drawPixmap(self._pet_offset.x(), self._pet_offset.y() + dy, pm)

    def _paint_bubble(self, p):
        body = self._bubble_body()
        x, y, w, h = body.x(), body.y(), body.width(), body.height()
        cx = self._pet_offset.x() + self.pet_w // 2
        cx = max(x + 20, min(cx, x + w - 20))
        tail = QPainterPath()
        tail.moveTo(cx - 9, body.bottom() - 2)
        tail.lineTo(cx, body.bottom() + 10)
        tail.lineTo(cx + 9, body.bottom() - 2)
        tail.closeSubpath()

        path = QPainterPath()
        path.addRoundedRect(body, 15, 15)
        shape = path.united(tail)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 246))
        p.drawPath(shape)
        p.setPen(QPen(QColor(186, 214, 240), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)

        p.setPen(QColor(44, 66, 88))
        p.setFont(self._bubble_font())
        p.drawText(body.adjusted(13, 10, -13, -10),
                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.bubble_text)

    # ---------- 鼠标 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_at = e.globalPosition().toPoint()
            self._drag_pos = self._press_at - self.frameGeometry().topLeft()
            self._drag_moved = 0
        elif e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            gp = e.globalPosition().toPoint()
            self._drag_moved = max(self._drag_moved, (gp - self._press_at).manhattanLength())
            self.move(gp - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._drag_moved < 6:
                self.on_click()
            self._drag_pos = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.toggle_panel()

    # ---------- 交互 ----------
    def on_click(self):
        self.wave()
        if self.posts and random.random() < 0.55:
            top = max(self.posts, key=lambda x: x["heat"])
            self.say("现在最火的是：\n「%s」\n热度 %d" % (top["title"][:18], top["heat"]))
        else:
            self.say(random.choice(PHRASES))

    def _menu(self, gp):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #D7E5F5;border-radius:10px;padding:6px;}"
            "QMenu::item{padding:6px 18px;border-radius:6px;color:#2C4258;font-size:13px;}"
            "QMenu::item:selected{background:#EFF6FD;}"
            "QMenu::separator{height:1px;background:#E6EFF9;margin:4px 8px;}")
        m.addAction("查看热帖榜", self.toggle_panel)
        m.addAction("立即刷新", self.refresh)
        a = QAction("暂停新帖提醒", m, checkable=True)
        a.setChecked(self.paused)
        a.toggled.connect(self._toggle_pause)
        m.addAction(a)
        m.addSeparator()
        m.addAction("退出小豚", self._quit)
        m.exec(gp)

    def _toggle_pause(self, on):
        self.paused = on
        self.say("好的，我先安静会儿" if on else "恢复啦，有新帖我喊你！")

    def _quit(self):
        self.panel.hide()
        QApplication.quit()

    def toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            if not self.posts:
                self.refresh()
            self.panel.set_posts(self.posts)
            self.panel.show_near_pet()

    # ---------- 数据 ----------
    def refresh(self):
        self._workers = [w for w in getattr(self, "_workers", []) if w.isRunning()]
        w = Fetcher(self.source)
        w.ok.connect(self._on_posts)
        w.fail.connect(lambda m: self.say("拉取失败：%s" % m))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    def _on_posts(self, posts):
        self.posts = posts
        new = [p for p in posts if p["id"] not in self.seen]
        for p in posts:
            self.seen.add(p["id"])
        self.first_load = False
        if new and not self.paused:
            top = max(new, key=lambda x: x["heat"])
            self.say("有新帖！\n「%s」\n%s · 热度 %d"
                     % (top["title"][:18], top["author"], top["heat"]), 6800)
            self._notify("豚说小豚", "新帖：%s（热度 %d）" % (top["title"][:22], top["heat"]))
        if self.panel.isVisible():
            self.panel.set_posts(posts)

    def _notify(self, title, msg):
        if not self.cfg.get("notify_system", True) or sys.platform != "darwin":
            return
        msg = msg.replace('"', "'")
        title = title.replace('"', "'")
        try:
            subprocess.Popen(
                ["osascript", "-e",
                 'display notification "%s" with title "%s" subtitle "论坛动态"' % (msg, title)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# ----------------------------------------------------------------------
class HotPanel(QWidget):
    def __init__(self, pet, on_refresh):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.pet = pet
        self.resize(336, 406)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 13, 15, 15)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("豚说 · 热帖榜")
        t.setFont(QFont("PingFang SC", 13, QFont.DemiBold))
        t.setStyleSheet("color:#2C4258;")
        head.addWidget(t)
        head.addStretch(1)
        btn = QPushButton("刷新")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{background:#E8F2FC;color:#3C6E9F;border:none;border-radius:9px;"
            "padding:4px 11px;font-size:12px;} QPushButton:hover{background:#D9EAFB;}")
        btn.clicked.connect(on_refresh)
        head.addWidget(btn)
        close = QPushButton("×")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedSize(20, 20)
        close.setStyleSheet("QPushButton{background:transparent;color:#9BB4CC;border:none;"
                            "font-size:16px;} QPushButton:hover{color:#3C6E9F;}")
        close.clicked.connect(self.hide)
        head.addWidget(close)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget{background:transparent;border:none;outline:none;}"
            "QListWidget::item{border-radius:10px;margin:2px 0;}"
            "QListWidget::item:hover{background:#F4F9FE;}"
            "QListWidget::item:selected{background:#E8F2FC;}"
            "QScrollBar:vertical{width:5px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#C9DDF2;border-radius:2px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        self.list.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.list, 1)

        tip = QLabel("双击条目打开原帖")
        tip.setStyleSheet("color:#A9BECF;font-size:11px;")
        lay.addWidget(tip)
        self.posts = []

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(213, 229, 245), 1.0))
        p.setBrush(QColor(255, 255, 255, 252))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 16, 16)

    def set_posts(self, posts):
        self.posts = sorted(posts, key=lambda x: -x["heat"])
        self.list.clear()
        title_font = QFont("PingFang SC", 12)
        fm = QFontMetrics(title_font)
        for post in self.posts[:60]:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(2)
            title = QLabel(post["title"])
            title.setFont(title_font)
            title.setStyleSheet("color:#2C4258;")
            title.setWordWrap(True)
            meta = QLabel("%s · %s · 热度 %d" % (post["tag"] or "动态", post["author"], post["heat"]))
            meta.setStyleSheet("color:#8FA6BE;font-size:11px;")
            v.addWidget(title)
            v.addWidget(meta)
            # 按实际换行行数算高度，避免文字被裁剪
            text_rect = fm.boundingRect(0, 0, 244, 300,
                                        Qt.TextWordWrap | Qt.AlignLeft, post["title"])
            item_h = text_rect.height() + 42
            item = QListWidgetItem(self.list)
            item.setSizeHint(QSize(0, max(44, item_h)))
            item.setData(Qt.UserRole, post.get("url"))
            self.list.addItem(item)
            self.list.setItemWidget(item, w)

    def _open(self, item):
        url = item.data(Qt.UserRole)
        if url:
            import webbrowser
            webbrowser.open(url)
        else:
            self.pet.say("这条是演示数据，还没有链接～")

    def show_near_pet(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x = self.pet.frameGeometry().left() - self.width() - 12
        if x < scr.left() + 8:
            x = min(self.pet.frameGeometry().right() + 12, scr.right() - self.width() - 8)
        y = max(scr.top() + 8,
                min(self.pet.frameGeometry().center().y() - self.height() // 2,
                    scr.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


# ----------------------------------------------------------------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cfg


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    pet = PetWindow(cfg, DataSource(cfg))
    pet.show()

    tray = QSystemTrayIcon(QIcon(QPixmap(os.path.join(ASSET_DIR, "pet.png"))))
    tray.setToolTip("豚说小豚")
    tm = QMenu()

    def _sync_label():
        toggle.setText("隐藏小豚" if pet.isVisible() else "显示小豚")

    toggle = tm.addAction("隐藏小豚", lambda: pet.set_pet_visible(not pet.isVisible()))
    tm.aboutToShow.connect(_sync_label)
    tm.addAction("回到右下角", lambda: (pet.show_pet(), pet._place_bottom_right()))
    tm.addAction("查看热帖榜", pet.toggle_panel)
    tm.addAction("立即刷新", pet.refresh)
    tm.addSeparator()
    tm.addAction("退出", pet._quit)
    tray.setContextMenu(tm)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

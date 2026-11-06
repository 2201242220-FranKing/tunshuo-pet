#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豚说小豚 · 桌面宠物 v4（PySide6）
==================================
形象：豚说官方 IP 蓝色小鲸鱼（ψ）

v4 关键改动：
  1. 【动作注册表】所有动作集中在 ACTIONS 里，加动作只需写一个函数 + @action 装饰器。
  2. 【待机行为调度】每隔几秒随机做一个动作（张望/摇摆/伸懒腰/蹦一下），不再呆站。
  3. 【互动增强】悬停反应、连点彩蛋、拖拽倾斜与边缘吸附、落地挤压、喂小鱼干、久坐会睡着。
  4. 保持 v3 的两个关键约束：气泡在窗口内绘制（不抢焦点）、macOS 工具窗口常显。

常用调整入口：
  · 动作幅度 / 时长   → ACTIONS 里对应函数 + @action("名字", 秒数)
  · 待机动作频率      → IDLE_INTERVAL_RANGE 与 IDLE_ACTIONS
  · 自动睡觉时长      → config.json 的 idle_sleep_seconds
"""

import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.request

from PySide6.QtCore import (QEasingCurve, QPoint, QRectF, QSize, Qt, QThread,
                            QTimer, QVariantAnimation, Signal)
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
    "auto_poll": False,          # 关闭自动轮询：不再定时拉取/弹提醒
    "poll_interval_minutes": 3,
    "notify_system": True,
    "pet_width": 60,
    "idle_sleep_seconds": 180,   # 无操作多久后自己睡着（0 = 永不）
    "fish": 0,                   # 喂过的小鱼干数量
}

# 待机随机动作的间隔区间（秒）
IDLE_INTERVAL_RANGE = (4.5, 11.0)
IDLE_ACTIONS = ["sway", "sway", "look", "look", "stretch", "hop", "nod"]

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


# ======================================================================
# 动作注册表
#   每个动作是一个函数 fn(pet, t)，t 在 0..1 之间表示动作进度；
#   返回 6 元组：(横向位移, 纵向位移, 旋转角度, 横向缩放, 纵向缩放, 是否水平翻转)
#   想加新动作：照抄下面任意一个，写个 @action("名字", 秒数) 即可，其它地方不用改。
# ======================================================================
ACTIONS = {}


def action(name, duration):
    def deco(fn):
        ACTIONS[name] = (duration, fn)
        return fn
    return deco


def _ease_out(t):
    return 1 - (1 - t) ** 3


@action("hop", 0.62)                 # 原地蹦一下（起跳压缩 + 落地挤压）
def _hop(pet, t):
    dy = -58 * math.sin(math.pi * t)
    squash = 1.0
    if t < 0.12:
        squash = 1 - 0.10 * math.sin(math.pi * t / 0.12)
    elif t > 0.86:
        squash = 1 - 0.13 * math.sin(math.pi * (t - 0.86) / 0.14)
    return 0, dy, 0, 1 / squash ** 0.5, squash, False


@action("sway", 1.6)                 # 左右摇摆（不倒翁）
def _sway(pet, t):
    decay = math.exp(-1.1 * t)
    return 0, -3 * abs(math.sin(2 * math.pi * t)), 12 * math.sin(2.4 * math.pi * t) * decay, 1, 1, False


@action("look", 2.0)                 # 左右张望（镜像转身 + 微微前倾）
def _look(pet, t):
    if t < 0.08 or t > 0.92:
        return 0, 0, 0, 1, 1, False
    lean = 4 * math.sin(math.pi * (t - 0.08) / 0.84)
    return 0, -1, lean, 1, 1, getattr(pet, "_look_flip", False)


@action("stretch", 1.3)              # 伸懒腰（拉长 + 变窄）
def _stretch(pet, t):
    k = math.sin(math.pi * t)
    return 0, -7 * k, 0, 1 - 0.08 * k, 1 + 0.11 * k, False


@action("nod", 0.9)                  # 点头两次
def _nod(pet, t):
    k = abs(math.sin(2 * math.pi * t))
    return 0, 9 * k, 0, 1 + 0.04 * k, 1 - 0.05 * k, False


@action("shake", 0.5)                # 被点时的抖动
def _shake(pet, t):
    return 11 * math.sin(8 * math.pi * t) * math.exp(-1.4 * t), 0, 0, 1, 1, False


@action("land", 0.34)                # 松手落地时的挤压
def _land(pet, t):
    k = math.sin(math.pi * t)
    return 0, 3 * k, 0, 1 + 0.10 * k, 1 - 0.12 * k, False


@action("dance", 1.5)                # 连蹦带歪（连点彩蛋）
def _dance(pet, t):
    hop = abs(math.sin(3 * math.pi * t))
    tilt = 11 * math.sin(3 * math.pi * t + 0.5) * math.exp(-0.6 * t)
    return 0, -24 * hop, tilt, 1, 1, False


@action("wobble", 0.8)               # 被拖动后的余震
def _wobble(pet, t):
    return 0, 0, 12 * math.sin(3 * math.pi * t) * math.exp(-2.4 * t), 1, 1, False


# ----------------------------------------------------------------------
class DataSource:
    def __init__(self, cfg):
        self.cfg = cfg
        self.n = 0

    def fetch(self):
        url = (self.cfg.get("api_url") or "").strip()
        return self._api(url) if url else self._mock()

    def _api(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet/4.0"})
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

    PAD = 8

    def __init__(self, cfg, source):
        # NoDropShadowWindowHint：关掉 macOS 给窗口加的系统投影。
        # 无边框透明窗口的投影是按「窗口矩形」模糊生成的，会在角色背后投出一个
        # 灰色方块/暗轮廓（动作播放时遮罩变矩形会更明显）。
        super().__init__(None,
                         Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # macOS：Qt.Tool 窗口默认在 App 失去激活时自动隐藏（切到别的应用小豚就消失）
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        self.cfg = cfg
        self.source = source
        self.posts = []
        self.seen = set()
        self.paused = False
        self.first_load = True
        self.fish = int(cfg.get("fish", 0) or 0)

        # 素材
        self.pm_open = self._load("pet.png")
        self.pm_blink = self._load("pet_blink.png")
        # 可选表情帧：assets 下放了 pet_happy.png / pet_sleep.png 就会自动启用
        self.frames = {"open": self.pm_open, "blink": self.pm_blink}
        for key, fname in (("happy", "pet_happy.png"), ("sleep", "pet_sleep.png")):
            pm = self._load_optional(fname)
            if pm is not None:
                self.frames[key] = pm
        self.blinking = False
        self.sleeping = False

        dpr = self.pm_open.devicePixelRatio() or 1.0
        pet_w = int(round(self.pm_open.width() / dpr))
        pet_h = int(round(self.pm_open.height() / dpr))
        self.pet_w, self.pet_h = pet_w, pet_h
        self.BUBBLE_MAX_W = int(max(198, min(268, pet_w * 2.7)))
        self._bubble_px = 12 if pet_w < 100 else 13
        self.win_w = max(self.BUBBLE_MAX_W + 24, pet_w + 40)
        self.bubble_h = 0
        self.bubble_w = self.BUBBLE_MAX_W
        self.bubble_text = ""
        self._bubble_alpha = 0.0
        self.bubble_alpha_anim = None
        self.win_h = int(pet_h + 124)

        self.resize(self.win_w, self.win_h)
        self._pet_offset = QPoint((self.win_w - pet_w) // 2, self.win_h - pet_h - 10)

        # 动画状态（必须在 _apply_mask 之前初始化）
        self._breath = 0.0
        self._bob = 0.0
        self._act = None            # (名字, 起始时间, 时长, 函数)
        self._act_active = False
        self._tf = (0.0, 0.0, 0.0, 1.0, 1.0, False)
        self._look_flip = False

        mask_src = QPixmap(os.path.join(ASSET_DIR, "pet.png")).scaledToWidth(
            pet_w, Qt.SmoothTransformation)
        self.sprite_region = QRegion(mask_src.mask()).translated(
            self._pet_offset.x(), self._pet_offset.y())
        self._apply_mask()

        # 交互状态
        self._drag_pos = None
        self._press_at = None
        self._drag_moved = 0
        self._dragging = False
        self._drag_lean = 0.0        # 当前显示角度（平滑后）
        self._lean_v = 0.0           # 平滑后的拖动速度 px/s
        self._last_gp = None         # 上一次鼠标全局坐标
        self._last_move_t = 0.0      # 上一次鼠标移动时间
        self._last_lean_t = 0.0      # 上一次倾斜插值时间
        self._move_hist = []         # 最近 100ms 的 (时间, x)，用来算平均速度
        self._click_times = []
        self._last_hover = 0.0
        self.last_interact = time.monotonic()

        self.panel = HotPanel(self, self.refresh)
        self._place_bottom_right()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)

        self.blink_timer = QTimer(self)
        self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(random.randint(2800, 5600))

        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._idle_pick)
        self.idle_timer.start(int(random.uniform(*IDLE_INTERVAL_RANGE) * 1000))

        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self._hide_bubble)

        QTimer.singleShot(1200, lambda: self.say("点我看看热帖～右键有菜单", 4200))

    # ---------- 素材与遮罩 ----------
    def _load(self, name):
        """按配置的逻辑宽度加载：不缩放像素，只设置 devicePixelRatio。

        运行期缩放 RGBA 会把透明区的颜色混进轮廓（就是那圈黑边），
        直接用高分辨率素材 + DPR 让系统合成，边缘才干净。
        """
        pm = QPixmap(os.path.join(ASSET_DIR, name))
        if pm.isNull():
            raise FileNotFoundError(os.path.join(ASSET_DIR, name))
        target = max(1, int(self.cfg.get("pet_width", 60)))
        if pm.width() > target:
            pm.setDevicePixelRatio(pm.width() / float(target))
        return pm

    def _load_optional(self, name):
        path = os.path.join(ASSET_DIR, name)
        if not os.path.exists(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        target = max(1, int(self.cfg.get("pet_width", 60)))
        if pm.width() > target:
            pm.setDevicePixelRatio(pm.width() / float(target))
        return pm

    def _current_frame(self):
        """按状态挑一张图：睡觉 > 开心（跳舞时）> 眨眼 > 常态。"""
        if self.sleeping:
            return self.frames.get("sleep") or self.pm_blink
        if self._act and self._act[0] in ("dance", "hop") and "happy" in self.frames:
            return self.frames["happy"]
        if self.blinking:
            return self.pm_blink
        return self.pm_open

    def _act_rect(self):
        """变换期间（跳动/倾斜/挤压）角色会超出正立轮廓，用一块留足余量的矩形兜住。

        余量按最大旋转 30°、跳跃 30px 估算：60x80 的角色绕中心转 30° 后，
        半宽从 30 涨到约 46、半高从 40 涨到约 50，所以左右各留 24px（半宽 54）、
        上方留 110px、下方留 62px 才不会被窗口遮罩裁掉。
        """
        return QRectF(max(0, self._pet_offset.x() - 24),
                      max(0, self._pet_offset.y() - 70),
                      self.pet_w + 48,
                      self.pet_h + 92).toRect()

    def _applying_transform(self):
        """是否处于会改变角色轮廓的状态（动作播放中 / 拖动倾斜中）。"""
        return bool(getattr(self, "_act_active", False)
                    or getattr(self, "_dragging", False)
                    or abs(getattr(self, "_drag_lean", 0.0)) > 0.5)

    def _apply_mask(self):
        region = QRegion(self.sprite_region)
        if self._applying_transform():
            region = region.united(QRegion(self._act_rect()))
        if self.bubble_h > 4:
            # 用「不含起跳位移」的基准位置，并向上多留 44px：
            # 气泡随角色上跳时不会被遮罩裁掉，同时不必每帧重建窗口形状
            # （macOS 上改窗口形状很贵，会造成卡顿和闪烁）
            w, h = self.bubble_w, self.bubble_h
            x = (self.win_w - w) // 2
            y = max(0, self._pet_offset.y() - h - 6 - 44)
            region = region.united(QRegion(QRectF(x, y, w, h + 56).toRect()))
        self.setMask(region)

    def _bubble_body(self):
        w, h = self.bubble_w, self.bubble_h
        x = (self.win_w - w) // 2
        # 角色跳起/拉伸时，气泡跟着往上让，避免被头顶穿过去
        lift = min(0.0, float(self._tf[1]) + float(self._bob))
        y = max(2, self._pet_offset.y() - h - 6 + lift)
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

    # ---------- 动作调度 ----------
    def play(self, name):
        if name not in ACTIONS or self.sleeping:
            return
        dur, fn = ACTIONS[name]
        self._act = (name, time.monotonic(), dur, fn)
        self._act_active = True
        self._apply_mask()
        self.touch()

    def _lean_target(self, vx):
        """把拖动速度(px/s)映射成倾斜角度(度)。

        用 log 曲线压缩，动态范围拉到 0~1200px/s：
        慢拖（10~30px/s）就有 10~13°，中速 200px/s 约 22°，
        真正甩起来（1200px/s 以上）才吃满 30°。
        只要在动就保底 20% 的角度，避免"轻轻拖没反应"。
        """
        MAXA, SOFT, FAST, FLOOR = 30.0, 8.0, 1200.0, 0.20
        a = abs(vx)
        if a < 1.5:                       # 基本没动，视为静止
            return 0.0
        k = math.log1p(a / SOFT) / math.log1p(FAST / SOFT)
        k = FLOOR + (1.0 - FLOOR) * min(1.0, k)
        return math.copysign(min(1.0, k) * MAXA, vx)

    def _update_lean(self):
        """按速度平滑更新倾斜角；鼠标停住时速度自然衰减、身体慢慢回正。"""
        now = time.monotonic()
        dt = now - self._last_lean_t if self._last_lean_t else 0.016
        self._last_lean_t = now
        # 用时间常数换算插值系数，保证 8ms 的鼠标事件和 60ms 的定时器步调一致
        alpha = 1.0 - math.exp(-max(0.0, dt) / 0.055)
        if self._dragging:
            quiet = now - self._last_move_t
            if quiet > 0.12:              # 停手 → 速度指数衰减（阈值要大于定时器 60ms）
                self._lean_v *= math.exp(-quiet / 0.12)
            target = self._lean_target(self._lean_v)
            self._drag_lean += (target - self._drag_lean) * alpha
        elif abs(self._drag_lean) > 0.15:
            self._drag_lean += (0.0 - self._drag_lean) * alpha   # 松手回弹
            if abs(self._drag_lean) <= 0.15:
                self._drag_lean = 0.0
                self._apply_mask()
        elif self._drag_lean:
            self._drag_lean = 0.0

    def _update_action(self):
        if not self._act:
            self._tf = (0.0, 0.0, self._drag_lean, 1.0, 1.0, False)
            return
        name, t0, dur, fn = self._act
        t = (time.monotonic() - t0) / dur
        if t >= 1.0:
            self._act = None
            self._act_active = False
            self._tf = (0.0, 0.0, 0.0, 1.0, 1.0, False)
            self._apply_mask()
            return
        self._tf = fn(self, max(0.0, t))

    def _idle_pick(self):
        if not (self._act or self.sleeping or self.panel.isVisible() or self._dragging):
            name = random.choice(IDLE_ACTIONS)
            if name == "look":
                self._look_flip = random.random() < 0.5
            self.play(name)
        self.idle_timer.start(int(random.uniform(*IDLE_INTERVAL_RANGE) * 1000))

    def _tick(self):
        self._breath += 0.075 if not self.sleeping else 0.035
        amp = 2.4 if not self.sleeping else 1.2
        self._bob = math.sin(self._breath) * amp
        self._update_lean()
        self._update_action()

        sleep_after = int(self.cfg.get("idle_sleep_seconds", 180) or 0)
        if (sleep_after and not self.sleeping and not self._act
                and not self._dragging and not self.panel.isVisible()
                and time.monotonic() - self.last_interact > sleep_after):
            self.sleep()
        self.update()

    def _blink(self):
        if not self.sleeping and not self.blinking:
            self.blinking = True
            self.update()
            QTimer.singleShot(130, self._unblink)
        self.blink_timer.start(random.randint(2600, 6200))

    def _unblink(self):
        self.blinking = False
        self.update()

    # ---------- 睡觉 / 唤醒 ----------
    def sleep(self):
        if self.sleeping:
            return
        self.sleeping = True
        self._act = None
        self._act_active = False
        self._apply_mask()
        self.update()

    def wake(self, say_it=True):
        if not self.sleeping:
            return
        self.sleeping = False
        self.touch()
        self.play("hop")
        if say_it:
            self.say(random.choice(["唔…我没睡！", "被叫醒啦～", "我在我在！"]))

    def touch(self):
        self.last_interact = time.monotonic()

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
        dx, dy, rot, sx, sy, flip = self._tf
        pm = self._current_frame()

        # 以「角色中心」为锚点做变换：旋转/挤压都在窗口内部完成，不会被裁切
        cx = self._pet_offset.x() + self.pet_w / 2.0 + dx
        cy = self._pet_offset.y() + self.pet_h / 2.0 + dy + self._bob
        p.save()
        p.translate(cx, cy)
        if rot:
            p.rotate(rot)
        if flip:
            p.scale(-1.0, 1.0)
        p.scale(sx, sy)
        p.drawPixmap(int(-self.pet_w / 2), int(-self.pet_h / 2), pm)
        p.restore()

        if self.sleeping:
            self._paint_zzz(p)

    def _paint_zzz(self, p):
        p.setFont(QFont("PingFang SC", 13, QFont.DemiBold))
        base_x = self._pet_offset.x() + self.pet_w - 4
        base_y = self._pet_offset.y() + 14
        for i in range(3):
            phase = (self._breath * 0.5 + i * 0.7) % 2.0
            alpha = int(190 * max(0.0, 1 - abs(phase - 1.0)))
            if alpha <= 0:
                continue
            p.setPen(QColor(120, 158, 196, alpha))
            p.drawText(int(base_x + i * 5), int(base_y - phase * 9), "z")

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
    def enterEvent(self, e):
        super().enterEvent(e)
        now = time.monotonic()
        if now - self._last_hover > 6.0 and not self.sleeping and not self._act:
            self._last_hover = now
            if random.random() < 0.5:
                self._look_flip = True
                self.play("look")

    def mousePressEvent(self, e):
        self.touch()
        if self.sleeping:
            self.wake()
            return
        if e.button() == Qt.LeftButton:
            self._press_at = e.globalPosition().toPoint()
            self._drag_pos = self._press_at - self.frameGeometry().topLeft()
            self._drag_moved = 0
            self._dragging = False
            self._lean_v = 0.0
            self._last_gp = self._press_at
            self._last_move_t = time.monotonic()
            self._move_hist = [(self._last_move_t, self._press_at.x())]
        elif e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            gp = e.globalPosition().toPoint()
            delta = gp - self._press_at
            self._drag_moved = max(self._drag_moved, delta.manhattanLength())
            if self._drag_moved > 6 and not self._dragging:
                # 刚进入拖动：打断正在播的动作，否则倾斜不会生效
                self._dragging = True
                self._act = None
                self._act_active = False
                self._last_gp = gp
                self._lean_v = 0.0
                self._move_hist = [(time.monotonic(), gp.x())]
                self._apply_mask()
            self.move(gp - self._drag_pos)

            # 用最近 100ms 的平均速度，而不是单次事件的瞬时速度：
            # 鼠标坐标是整数、事件间隔约 8ms，单次 1px 位移就会算出 125px/s，
            # 慢拖被误判成"甩"，这就是"一动就满格"的根因。
            now = time.monotonic()
            self._move_hist.append((now, gp.x()))
            while len(self._move_hist) > 2 and now - self._move_hist[0][0] > 0.10:
                self._move_hist.pop(0)
            t0, x0 = self._move_hist[0]
            span = now - t0
            if span >= 0.02:
                inst = (gp.x() - x0) / span
                self._lean_v += (inst - self._lean_v) * 0.55
            self._last_gp = gp
            self._last_move_t = now
            self._update_lean()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            was_drag = self._dragging
            self._dragging = False
            self._lean_v = 0.0          # 角度交给 _update_lean 平滑回正
            if was_drag:
                self._snap_to_edge()
                self.play("wobble")
            elif self._drag_moved < 6:
                self.on_click()
            self._drag_pos = None
            self._apply_mask()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.touch()
            self.toggle_panel()

    def _snap_to_edge(self):
        """拖到屏幕边缘附近时自动吸附。"""
        scr = QApplication.screenAt(self.frameGeometry().center()) \
            or QApplication.primaryScreen()
        g = scr.availableGeometry()
        margin = 16
        x, y = self.x(), self.y()
        if abs(x - g.left()) < margin:
            x = g.left()
        elif abs((x + self.width()) - g.right()) < margin:
            x = g.right() - self.width()
        if abs(y - g.top()) < margin:
            y = g.top()
        elif abs((y + self.height()) - g.bottom()) < margin:
            y = g.bottom() - self.height()
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ---------- 交互 ----------
    def on_click(self):
        now = time.monotonic()
        self._click_times = [t for t in self._click_times if now - t < 2.0]
        self._click_times.append(now)

        if len(self._click_times) >= 5:      # 连点彩蛋
            self._click_times = []
            self.play("dance")
            self.say("哇，你点我这么多下！\n那我跳个舞吧～", 5200)
            return

        self.play("shake")
        if self.posts and random.random() < 0.55:
            top = max(self.posts, key=lambda x: x["heat"])
            self.say("现在最火的是：\n「%s」\n热度 %d" % (top["title"][:18], top["heat"]))
        else:
            self.say(random.choice(PHRASES))

    def feed(self):
        self.fish += 1
        self._save_fish()
        self.touch()
        self.sleeping = False
        self.play("hop")
        self.say(random.choice([
            "小鱼干！这个我最喜欢了（已投喂 %d 条）" % self.fish,
            "嗷呜～谢谢！第 %d 条啦" % self.fish,
            "吃饱了就有力气帮你盯论坛了（%d 条）" % self.fish,
        ]))

    def _save_fish(self):
        try:
            self.cfg["fish"] = self.fish
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def do_random_action(self):
        if self.sleeping:
            self.wake()
            return
        self._look_flip = random.random() < 0.5
        self.play(random.choice(list(ACTIONS.keys())))

    def _menu(self, gp):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #D7E5F5;border-radius:10px;padding:6px;}"
            "QMenu::item{padding:6px 18px;border-radius:6px;color:#2C4258;font-size:13px;}"
            "QMenu::item:selected{background:#EFF6FD;}"
            "QMenu::separator{height:1px;background:#E6EFF9;margin:4px 8px;}")
        m.addAction("喂一条小鱼干（%d）" % self.fish, self.feed)
        m.addAction("动一下", self.do_random_action)
        m.addAction("睡 / 醒", lambda: self.wake() if self.sleeping else self.sleep())
        m.addSeparator()
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
            self.sleeping = False
            self.play("hop")
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
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.NoDropShadowWindowHint)
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
    tm.addAction("喂小鱼干", pet.feed)
    tm.addAction("动一下", pet.do_random_action)
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

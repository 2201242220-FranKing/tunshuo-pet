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

import studio_sync as ss
import action_engine as ae
import skin_rig as rig

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QPoint, QRectF,
                            QSize, Qt, QThread, QTimer, QVariantAnimation,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap, QRegion, QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(APP_DIR, "assets")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATE_PATH = os.path.join(APP_DIR, "state.json")

# 只放「配置」：会随源码入库，用户手动编辑，程序启动时只读一次。
DEFAULT_CONFIG = {
    "api_url": "",
    "auto_poll": False,          # 定时拉取，默认关闭；仅 api_url 非空时才会启动
    "poll_interval_minutes": 3,
    "notify_system": True,
    "pet_width": 60,
    "idle_sleep_seconds": 180,   # 无操作多久后自己睡着（0 = 永不）
    "studio_url": "http://127.0.0.1:8770",  # 形象工作台地址；留空 = 不联网同步
    "studio_sync_seconds": 20,              # 拉取间隔（秒），最小 5
}

# 只放「运行时状态」：每次互动都会写，不入库。
DEFAULT_STATE = {"fish": 0}

# 待机随机动作的间隔区间（秒）
IDLE_INTERVAL_RANGE = (4.5, 11.0)
IDLE_ACTIONS = ["sway", "sway", "look", "look", "stretch", "hop", "nod"]
# 工作台默认的待机候选（其余 4 个动作只在互动时触发，不会自己播）
IDLE_POOL = ["sway", "look", "stretch", "hop", "nod"]

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
# 动作数据（数据驱动，见 action_engine.py / actions.json）
#   · 默认动作从 actions.json 载入：每个动作是「关键帧数组 + cosine 缓动」
#   · 工作台编辑后，已发布配置里的 actions.defs 会覆盖这里的默认值
#   · 桌宠与网页共用同一份解释器，改动作不用再改两份代码
#   · 想加动作：在 actions.json 的 actions 里加一项，或在工作台时间轴里新建
# ======================================================================
DEFAULT_ACTION_DEFS = ae.load_file(os.path.join(APP_DIR, "actions.json"))
ACTIONS = ae.to_map(DEFAULT_ACTION_DEFS)      # 默认快照（离线 / 未接工作台时用）


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
        if not isinstance(posts, list):
            raise ValueError("接口返回的 posts 不是数组")
        out = []
        for i, p in enumerate(posts[:100]):        # 一次最多渲染 100 条
            if not isinstance(p, dict):
                continue
            try:
                heat = int(float(p.get("heat", 0) or 0))
            except (TypeError, ValueError):
                heat = 0                          # 脏数据不该让整批帖子作废
            link = p.get("url")
            # 只放行 http(s)：避免接口返回 javascript:/file: 之类的链接被双击打开
            if not (isinstance(link, str) and link.startswith(("http://", "https://"))):
                link = None
            out.append({
                "id": str(p.get("id", p.get("title", i))),
                "title": str(p.get("title") or "(无标题)")[:120],
                "author": str(p.get("author") or "豚友")[:60],
                "tag": str(p.get("tag") or "")[:30],
                "heat": heat,
                "time": str(p.get("time") or "")[:30],
                "url": link,
            })
        return out

    def _mock(self):
        self.n += 1
        # 固定 id 池：8 条常驻帖每次刷新内容会变，但 id 不变，不会被误判成新帖；
        # 只有每两次出现的 "new-N" 才代表真的来了一条新动态。
        posts = [{
            "id": "mock-%d" % i,
            "title": random.choice(MOCK_POOL),
            "author": random.choice(MOCK_AUTHORS),
            "tag": random.choice(MOCK_TAGS),
            "heat": random.randint(30, 680),
            "time": "%d分钟前" % random.randint(2, 90),
            "url": None,
        } for i in range(8)]
        if self.n % 2 == 0:
            posts.insert(0, {
                "id": "new-%d" % self.n,
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


class StudioFetcher(QThread):
    """拉形象配置 + 下载配饰图片，全部放在线程里，绝不阻塞动画。"""
    ok = Signal(dict)
    fail = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.ok.emit(ss.fetch(self.url))
        except Exception as ex:
            self.fail.emit(str(ex)[:80])


# ----------------------------------------------------------------------
class PetWindow(QWidget):
    """单窗口桌宠：精灵 + 内部气泡，永不新建窗口抢焦点。"""

    PAD = 8

    def __init__(self, cfg, source, state=None):
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
        self.state = state if state is not None else load_state(cfg)
        self.source = source
        self.posts = []
        self.seen = set()
        self.paused = False
        self.first_load = True
        self.fish = int(self.state.get("fish", 0) or 0)

        # 形象工作台：先用上一次的本地缓存启动（断网也能保持形象），
        # 稍后再联网拉「已发布」配置。没接工作台时 studio 就是内置默认值。
        self.studio = ss.load_cache()
        # 动作定义：优先用工作台已发布的版本，离线时回落到 actions.json
        cached_defs = ae.normalize_defs(self.studio.get("actions", {}).get("defs"))
        if cached_defs:
            # 兼容旧缓存：保留用户发布过的动作，补齐出厂新增的关节动作
            have = {d["key"] for d in cached_defs}
            cached_defs = cached_defs + [d for d in DEFAULT_ACTION_DEFS if d["key"] not in have]
        self.action_defs = cached_defs or list(DEFAULT_ACTION_DEFS)
        self.action_map = ae.to_map(self.action_defs)
        if int(self.studio.get("revision", 0)) > 0 and not cached_defs:
            # 缓存是旧版桌宠写的（没有动作定义），版本号又相同不会触发更新：
            # 标记一次强制同步，让首次拉取把工作台的动作数据补进缓存。
            self._studio_force = True
        if int(self.studio.get("revision", 0)) == 0:
            # 从未同步过工作台：沿用 config.json 的老配置，保证升级后行为不变
            self.studio["settings"]["notify"] = bool(cfg.get("notify_system", True))
            try:
                self.studio["settings"]["auto_sleep_seconds"] = int(cfg.get("idle_sleep_seconds", 180) or 0)
            except (TypeError, ValueError):
                pass
        self.studio_acc = []
        # 关节皮肤（rig 模式）：None 时完全走原来的整图绘制路径，零回归
        self.rig = None
        self.rig_pixmaps = {}
        self.rig_frames = {}
        self.rig_root = ""
        self._part_tf = {}          # 当前帧各部件的局部变换
        self._part_anim = None      # 独立于 root 的部件动画（拖动挣扎 / 摸头）
        self._last_drag_parts = 0.0
        self._press_local = None
        self.studio_url = str(cfg.get("studio_url") or "").strip()
        self._studio_worker = None

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
        self._last_tick_t = 0.0     # 上一次 _tick 的时间；呼吸按真实秒数累加
        self._act = None            # (名字, 起始时间, 时长, 动作定义 dict)
        self._act_active = False
        self._tf = (0.0, 0.0, 0.0, 1.0, 1.0, False)
        self._look_flip = False
        self._act_flip = False      # flip_random 动作本次播放是否翻转

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

        # 自动轮询：默认关闭；接了真实接口后把 auto_poll 打开即可按分钟拉新帖。
        # 演示数据模式下不启动，避免每几分钟用假数据弹一次提醒。
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh)
        if cfg.get("auto_poll") and str(cfg.get("api_url") or "").strip():
            try:
                minutes = max(1, int(cfg.get("poll_interval_minutes") or 3))
            except (TypeError, ValueError):
                minutes = 3
            self.poll_timer.start(minutes * 60 * 1000)

        # 形象同步：独立于热帖轮询，默认 20 秒拉一次；工作台没开就静默用缓存
        self.studio_timer = QTimer(self)
        self.studio_timer.timeout.connect(self._studio_refresh)
        self._apply_studio()
        if self.studio_url:
            try:
                secs = max(5, int(cfg.get("studio_sync_seconds", 20)))
            except (TypeError, ValueError):
                secs = 20
            self.studio_timer.start(secs * 1000)
            QTimer.singleShot(900, self._studio_refresh)

        QTimer.singleShot(1200, lambda: self.say(
            self.studio["settings"]["greeting"], 4200))

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
        """变换期间的扩展遮罩：按「角色 + 所有配饰」的实际包围盒动态计算。

        固定余量（左右 24px / 上 70px / 下 22px）只够覆盖原本 60x80 的角色
        旋转 30°；配饰可以被工作台拖到角色外侧、整体还能放大 1.4 倍，
        所以这里以角色中心为圆心求一个最小覆盖半径 R，旋转不会改变半径，
        再并上基础矩形，配饰拖到任何位置都不会被窗口形状裁掉。
        """
        base = QRectF(max(0, self._pet_offset.x() - 24),
                      max(0, self._pet_offset.y() - 70),
                      self.pet_w + 48,
                      self.pet_h + 92)
        scale = getattr(self, "studio_scale", 1.0)
        R = math.hypot(self.pet_w / 2.0, self.pet_h / 2.0) * scale
        for a in getattr(self, "studio_acc", []):
            hx = abs(a["x"] * self.pet_w) + a["lw"] / 2.0
            hy = abs(a["y"] * self.pet_h) + a["lh"] / 2.0
            R = max(R, math.hypot(hx, hy) * scale)
        if getattr(self, "rig", None):
            # 部件转动/挥手会伸到角色轮廓外；按父子变换后的保守包围半径扩遮罩，
            # 否则手尖会被窗口形状裁掉（与之前拖动残缺是同一个坑）
            R = max(R, rig.bounding_radius(self.rig["parts"], self._part_tf,
                                           self.pet_w, self.pet_h) * scale)
        cx = self._pet_offset.x() + self.pet_w / 2.0
        cy = self._pet_offset.y() + self.pet_h / 2.0
        # hop 动作会让整体上移约 58px，向上多留 64px
        extra = QRectF(cx - R, cy - R - 64, 2 * R, 2 * R + 64)
        return base.united(extra).toRect()

    def _applying_transform(self):
        """是否处于会改变角色轮廓的状态（动作 / 拖动倾斜 / 缩放 / 戴了配饰）。

        配饰与整体缩放都会让角色超出正立轮廓，必须用大矩形遮罩兜住，
        否则帽子、围巾的边角会被窗口形状裁掉（之前拖动残缺是同一个原因）。
        """
        return bool(getattr(self, "_act_active", False)
                    or getattr(self, "_dragging", False)
                    or getattr(self, "_part_anim", None)
                    or abs(getattr(self, "_drag_lean", 0.0)) > 0.5
                    or abs(getattr(self, "studio_scale", 1.0) - 1.0) > 0.001
                    or bool(getattr(self, "studio_acc", []))
                    or bool(getattr(self, "rig", None)))

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
        # 用宠物当前所在的屏幕，而不是永远用主屏（双屏时会跑错显示器）
        scr = (QApplication.screenAt(self.frameGeometry().center())
               or QApplication.primaryScreen()).availableGeometry()
        self.move(scr.right() - self.win_w - 40, scr.bottom() - self.win_h - 10)

    # ---------- 动作调度 ----------
    def play(self, name):
        if name not in self.action_map or self.sleeping:
            return
        act_cfg = self.studio["actions"]
        if act_cfg["enabled"].get(name, True) is False:   # 工作台里关掉的动作不播
            return
        d = self.action_map[name]
        dur = float(d["duration"]) / max(0.1, float(act_cfg["speed"]))  # 速度倍率：>1 变快
        self._act_flip = random.random() < 0.5 if d.get("flip_random") else False
        self._act = (name, time.monotonic(), dur, d)
        self._act_active = True
        self._apply_mask()
        self.touch()
        self.timer.setInterval(60)    # 立刻提帧，别等下一拍才动起来

    def on_event(self, name, parts_only=False):
        """事件状态机：按 trigger 找动作播放；找不到返回 False 让调用方走旧逻辑。

        parts_only=True 时只驱动部件层，不动 root —— 拖动中播挣扎动画仍要保留倾斜。
        """
        if self.sleeping or not self.rig:
            return False
        cfg = self.studio["actions"]
        enabled = cfg.get("enabled", {})
        speed = max(0.1, float(cfg["speed"]))
        for d in self.action_defs:
            if d.get("trigger") != name or enabled.get(d["key"], True) is False:
                continue
            if parts_only:
                self._part_anim = (d, time.monotonic(), float(d["duration"]) / speed)
                self.timer.setInterval(60)
                self._apply_mask()
            else:
                self.play(d["key"])
            return True
        return False

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
        parts = {}
        if not self._act:
            self._tf = (0.0, 0.0, self._drag_lean, 1.0, 1.0, False)
        else:
            name, t0, dur, action_def = self._act
            t = (time.monotonic() - t0) / dur
            if t >= 1.0:
                self._act = None
                self._act_active = False
                self._tf = (0.0, 0.0, 0.0, 1.0, 1.0, False)
                self._apply_mask()
            else:
                self._tf = ae.evaluate(action_def, max(0.0, t), self._act_flip)
                parts.update(ae.evaluate_parts(action_def, max(0.0, t)))
        # 部件动画独立于 root：拖动时也能挣扎，不会把倾斜角覆盖掉
        if self._part_anim:
            d, t0, dur = self._part_anim
            t = (time.monotonic() - t0) / dur
            if t >= 1.0:
                self._part_anim = None
                self._apply_mask()
            else:
                parts.update(ae.evaluate_parts(d, max(0.0, t)))
        self._part_tf = parts

    def _idle_pick(self):
        if not (self._act or self.sleeping or self.panel.isVisible() or self._dragging):
            # 待机候选由动作数据的 idle_weight 决定；工作台的权重滑块可覆盖它，
            # 因此新增/删除动作都能立刻影响待机，不用再改这里的名单。
            act_cfg = self.studio["actions"]
            weights = act_cfg.get("weights", {})
            merged = [dict(d, idle_weight=int(weights.get(d["key"], d["idle_weight"])))
                      for d in self.action_defs]
            pool = ae.idle_pool(merged, act_cfg["enabled"])
            if pool:
                self.play(random.choice(pool))
        ac = self.studio["actions"]
        self.idle_timer.start(int(random.uniform(ac["idle_min"], ac["idle_max"]) * 1000))

    def _tick(self):
        now = time.monotonic()
        dt = min(0.25, now - self._last_tick_t) if self._last_tick_t else 0.06
        self._last_tick_t = now
        # 呼吸按真实秒数累加（原来按 60ms 步进），降帧后节奏不会跟着变慢
        self._breath += dt * (1.25 if not self.sleeping else 0.583)
        amp = 2.4 if not self.sleeping else 1.2
        self._bob = math.sin(self._breath) * amp
        self._update_lean()
        self._update_action()

        # 自动睡觉时间由工作台发布（config.json 的 idle_sleep_seconds 作为初始值）
        sleep_after = int(self.studio["settings"]["auto_sleep_seconds"])
        if (sleep_after and not self.sleeping and not self._act
                and not self._dragging and not self.panel.isVisible()
                and now - self.last_interact > sleep_after):
            self.sleep()
        self.update()
        self._sync_frame_rate()

    def _sync_frame_rate(self):
        """按状态调帧：动作/拖动 16.7fps，静止 6.7fps，睡觉 3.3fps。

        常驻 60ms 会让一个十来小时的后台进程一直做无意义的整窗重绘；
        呼吸、倾斜、动作全都按真实时间计算，降帧不会改变动画速度。
        """
        anim = getattr(self, "bubble_alpha_anim", None)
        fading = anim is not None and anim.state() != QAbstractAnimation.Stopped
        busy = (self._act or self._part_anim or self._dragging
                or abs(self._drag_lean) > 0.15 or self.blinking or fading)
        if busy:
            interval = 60
        elif self.sleeping and not self.bubble_text:
            interval = 300
        elif self.bubble_text:
            interval = 120
        else:
            interval = 150
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)

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
        self.timer.setInterval(60)    # 气泡淡入期间保持流畅
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
        scale = getattr(self, "studio_scale", 1.0)
        accs = getattr(self, "studio_acc", [])

        # 以「角色中心」为锚点做变换：旋转/挤压都在窗口内部完成，不会被裁切
        cx = self._pet_offset.x() + self.pet_w / 2.0 + dx
        cy = self._pet_offset.y() + self.pet_h / 2.0 + dy + self._bob

        def layer(items):
            # 挂到部件上的配饰由 _paint_rig_layers 在该部件局部坐标系里画；
            # 这里只处理挂在 root 的（旧数据 attach 缺省 root，行为完全不变）
            return [a for a in accs if a["follow"] and a["layer"] == items
                    and a.get("attach", "root") == "root"]

        # 不跟随变形的配饰只跟着平移，单独一层画，避免被旋转带歪
        loose_back = [a for a in accs if not a["follow"] and a["layer"] == "back"]
        loose_front = [a for a in accs if not a["follow"] and a["layer"] == "front"]
        if loose_back:
            p.save(); p.translate(cx, cy)
            self._draw_accessories(p, loose_back)
            p.restore()

        p.save()
        p.translate(cx, cy)
        if rot:
            p.rotate(rot)
        if flip:
            p.scale(-1.0, 1.0)
        p.scale(sx * scale, sy * scale)
        # 配饰画在同一个变换里，跳起/倾斜/缩放时自然跟着角色走
        self._draw_accessories(p, layer("back"))
        if self.rig:
            self._paint_rig_layers(p, accs)
        else:
            p.drawPixmap(int(-self.pet_w / 2), int(-self.pet_h / 2), pm)
        self._draw_accessories(p, layer("front"))
        p.restore()

        if loose_front:
            p.save(); p.translate(cx, cy)
            self._draw_accessories(p, loose_front)
            p.restore()

        if self.sleeping:
            self._paint_zzz(p)

    def _current_head_frame(self):
        """rig 模式的表情帧只换 head 层，body / 手 / 呆毛不动，避免眨眼时手跟着跳。"""
        key = "idle"
        if self.sleeping:
            key = "sleep"
        elif self._act and self._act[0] in ("dance", "hop"):
            key = "happy"
        elif self.blinking:
            key = "blink"
        elif self.bubble_text:
            key = "speak"          # 播报时张嘴
        return self.rig_frames.get(key) or self.rig_frames.get("idle")

    def _draw_attached(self, p, accs, name, layer):
        items = [a for a in accs if a.get("attach", "root") == name
                 and a.get("layer") == layer and a.get("follow", True)]
        if items:
            self._draw_accessories(p, items)

    def _paint_rig_layers(self, p, accs):
        """按 z 序逐层绘制；每层的世界变换沿 parent 链累乘，部件动画作用在自己枢轴上。

        变换继承与绘制顺序是两件事：先算好世界矩阵，再按 z 序画，这样
        tail 挂在 head 下、但 z 比 head 小也能正确画在头后面。
        """
        parts = rig.z_order(self.rig["parts"])
        by_name = {x["name"]: x for x in parts}
        cache = {}

        def world(name):
            if name in cache:
                return cache[name]
            part = by_name[name]
            dx, dy, rot2, sx2, sy2 = self._part_tf.get(name, rig.PART_ZERO)
            px = part["pivot"]["x"] * self.pet_w
            py = part["pivot"]["y"] * self.pet_h
            t = QTransform()
            t.translate(px + dx, py + dy)
            if rot2:
                t.rotate(rot2)
            if sx2 != 1.0 or sy2 != 1.0:
                t.scale(sx2, sy2)
            t.translate(-px, -py)
            parent = part["parent"]
            # QTransform 是行向量约定，t * world(parent) 才等价于列向量下的
            # world(parent) ∘ local：子部件先绕自己的枢轴转，再跟父层一起动。
            # 顺序写反会让「头转 + 手挥」时手臂在世界坐标里旋转，网页预览也会对不上。
            w = (t * world(parent)) if parent else t
            cache[name] = w
            return w

        w, h = self.pet_w, self.pet_h
        for part in parts:
            name = part["name"]
            pm = self.rig_pixmaps.get(name)
            if name == "head":
                pm = self._current_head_frame() or pm
            if not pm or pm.isNull():
                continue
            p.save()
            p.setTransform(world(name), True)
            self._draw_attached(p, accs, name, "back")
            p.drawPixmap(QRectF(-w / 2.0, -h / 2.0, w, h), pm, QRectF(pm.rect()))
            self._draw_attached(p, accs, name, "front")
            p.restore()

    def _draw_accessories(self, p, items):
        for a in items:
            # 坐标以角色中心为原点，x/y 是相对角色宽高的归一化偏移
            x = a["x"] * self.pet_w - a["lw"] / 2.0
            y = a["y"] * self.pet_h - a["lh"] / 2.0
            p.drawPixmap(int(x), int(y), a["pm"])

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
            self._press_local = e.position().toPoint()
            self._drag_pos = self._press_at - self.frameGeometry().topLeft()
            self._drag_moved = 0
            self._dragging = False
            self._lean_v = 0.0
            self._last_gp = self._press_at
            self._last_move_t = time.monotonic()
            self._last_drag_parts = 0.0
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
                self.timer.setInterval(60)   # 拖动期间保持 16.7fps
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
            # 拖动中周期性挣扎：只驱动部件层，root 的倾斜角仍由 _update_lean 控制
            if self._dragging and self.rig and now - self._last_drag_parts > 0.85:
                self._last_drag_parts = now
                self.on_event("dragmove", parts_only=True)

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

        # 点上半身（头）= 摸头歪头；点身体 / 整图模式仍走原来的抖动
        pat = False
        if self.rig and self._press_local is not None:
            lx = self._press_local.x() - self._pet_offset.x()
            ly = self._press_local.y() - self._pet_offset.y()
            if 0 <= lx <= self.pet_w and 0 <= ly <= self.pet_h * 0.45:
                pat = self.on_event("pat")
        if not pat:
            self.play("shake")
        if self.posts and random.random() < 0.55:
            top = max(self.posts, key=lambda x: x["heat"])
            self.say("现在最火的是：\n「%s」\n热度 %d" % (top["title"][:18], top["heat"]))
        else:
            self.say(random.choice(self.studio["settings"]["phrases"]))

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
        # 只写 state.json（已被 .gitignore 忽略），喂鱼不会再弄脏仓库
        self.state["fish"] = self.fish
        try:
            _write_json(STATE_PATH, self.state)
        except Exception:
            pass

    def do_random_action(self):
        if self.sleeping:
            self.wake()
            return
        if self.action_map:
            self.play(random.choice(list(self.action_map)))

    def _menu(self, gp):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #D7E5F5;border-radius:10px;padding:6px;}"
            "QMenu::item{padding:6px 18px;border-radius:6px;color:#2C4258;font-size:13px;}"
            "QMenu::item:selected{background:#EFF6FD;}"
            "QMenu::separator{height:1px;background:#E6EFF9;margin:4px 8px;}")
        m.addAction("喂一条小鱼干（%d）" % self.fish, self.feed)
        m.addAction("动一下", self.do_random_action)
        m.addAction("打个招呼", lambda: self.on_event("greet") or self.play("wave"))
        m.addAction("睡 / 醒", lambda: self.wake() if self.sleeping else self.sleep())
        m.addSeparator()
        m.addAction("查看热帖榜", self.toggle_panel)
        m.addAction("立即刷新", self.refresh)
        a = QAction("暂停新帖提醒", m, checkable=True)
        a.setChecked(self.paused)
        a.toggled.connect(self._toggle_pause)
        m.addAction(a)
        m.addSeparator()
        m.addAction("打开形象工作台", self.open_studio)
        m.addAction("重新同步形象", self.force_studio_sync)
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

    # ---------- 形象工作台同步 ----------
    def _studio_refresh(self, force=False):
        """定时/手动拉取已发布形象。工作台没开或断网时静默回退到缓存。"""
        if not self.studio_url:
            return
        w = getattr(self, "_studio_worker", None)
        if w is not None and w.isRunning():
            return
        self._studio_force = bool(force)
        w = StudioFetcher(self.studio_url)
        w.ok.connect(self._on_studio)
        w.fail.connect(self._on_studio_fail)
        w.finished.connect(lambda w=w: self._studio_done(w))
        self._studio_worker = w
        w.start()

    def _studio_done(self, w):
        w.deleteLater()
        if self._studio_worker is w:
            self._studio_worker = None

    def _on_studio_fail(self, _msg):
        pass    # 静默：本地站本来就不一定一直开着

    def _on_studio(self, data):
        same = int(data.get("revision", 0)) == int(self.studio.get("revision", 0))
        force = getattr(self, "_studio_force", False)
        self._studio_force = False
        if same and not force:
            return
        self.studio = data
        ss.write_cache(data)
        self._apply_studio()
        if not same:
            self.sleeping = False
            self.play("hop")
            self.say("换了身新装扮～\n%s · v%d" % (data["name"], data["revision"]), 4600)

    def _load_rig(self):
        """在工作台切到关节皮肤时加载全部部件层；素材不齐/损坏就退回整图模式。"""
        def flat():
            self.rig = None
            self.rig_pixmaps = {}
            self.rig_frames = {}
            self.rig_root = ""
            self._part_tf = {}

        m = ss.load_skin(self.studio.get("skin"))
        if not m:
            flat()
            return
        root = os.path.join(ss.SKIN_DIR, m["id"])
        if any(not os.path.isfile(os.path.join(root, f)) for f in ss.skin_files(m)):
            flat()               # 断网 / 下载中断时绝不画半个角色
            return
        pms = {}
        for part in m["parts"]:
            pm = QPixmap(os.path.join(root, part["file"]))
            if pm.isNull():
                flat()
                return
            pms[part["name"]] = pm
        frames = {}
        for key, fname in m["frames"].items():
            pm = QPixmap(os.path.join(root, fname))
            if not pm.isNull():
                frames[key] = pm
        if not frames.get("idle"):
            flat()
            return
        self.rig = m
        self.rig_pixmaps = pms
        self.rig_frames = frames
        self.rig_root = root
        self._apply_mask()

    def _apply_studio(self):
        """把配置落成绘制状态（主线程里构建 QPixmap）。"""
        # 工作台发布的动作定义覆盖本地默认值；下发为空/脏数据时保持默认，不让小豚瘫掉
        synced = ae.normalize_defs(self.studio.get("actions", {}).get("defs"))
        if synced:
            have = {d["key"] for d in synced}
            synced = synced + [d for d in DEFAULT_ACTION_DEFS if d["key"] not in have]
        self.action_defs = synced or list(DEFAULT_ACTION_DEFS)
        self.action_map = ae.to_map(self.action_defs)
        self.studio_acc = ss.build_pixmaps(self.studio, self.pet_w)
        self.studio_scale = float(self.studio["appearance"]["scale"])
        self._load_rig()
        self._apply_mask()
        self.update()

    def force_studio_sync(self):
        self.say("正在同步形象…", 2200)
        self._studio_refresh(True)

    def open_studio(self):
        if self.studio_url:
            import webbrowser
            webbrowser.open(self.studio_url)
        else:
            self.say("还没配置形象工作台地址～")

    # ---------- 数据 ----------
    def refresh(self):
        self._workers = [w for w in getattr(self, "_workers", []) if w.isRunning()]
        if self._workers:            # 已有请求在跑：忽略重复点击，避免多次弹提醒
            return
        w = Fetcher(self.source)
        w.ok.connect(self._on_posts)
        w.fail.connect(lambda m: self.say("拉取失败：%s" % m))
        w.finished.connect(lambda w=w: self._worker_done(w))
        self._workers.append(w)
        w.start()

    def _worker_done(self, w):
        if w in getattr(self, "_workers", []):
            self._workers.remove(w)
        w.deleteLater()

    def _on_posts(self, posts):
        self.posts = posts
        new = [p for p in posts if p["id"] not in self.seen]
        for p in posts:
            self.seen.add(p["id"])
        # 只保留最近 200 个 id：长期轮询时 seen 不能无限增长
        if len(self.seen) > 200:
            self.seen = set(list(self.seen)[-200:])

        if self.first_load:
            # 首次加载只建立"已见过"基线，不弹气泡也不发系统通知，
            # 否则 seen 为空时所有帖子都会被当成新帖。
            self.first_load = False
            if self.panel.isVisible():
                self.panel.set_posts(posts)
            return

        if new and not self.paused:
            top = max(new, key=lambda x: x["heat"])
            self.sleeping = False
            # 关节皮肤下改成「抬手播报」，整图模式仍走原来的蹦一下
            if not self.on_event("newpost"):
                self.play("hop")
            self.say("有新帖！\n「%s」\n%s · 热度 %d"
                     % (top["title"][:18], top["author"], top["heat"]), 6800)
            self._notify("豚说小豚", "新帖：%s（热度 %d）" % (top["title"][:22], top["heat"]))
        if self.panel.isVisible():
            self.panel.set_posts(posts)

    def _notify(self, title, msg):
        # 工作台「新帖系统通知」开关优先（启动时已用 config.json 初始化过）
        if not self.studio["settings"]["notify"] or sys.platform != "darwin":
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
        # 双保险：即使数据来自别处，也只允许 http(s) 链接交给系统浏览器
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(url)
        else:
            self.pet.say("这条没有可打开的链接～")

    def show_near_pet(self):
        # 面板跟宠物所在的同一块屏幕对齐
        scr = (QApplication.screenAt(self.pet.frameGeometry().center())
               or QApplication.primaryScreen()).availableGeometry()
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
def _write_json(path, data):
    """原子写：先写临时文件再替换，避免写到一半被中断留下坏 JSON。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            cfg.update(raw)
    except FileNotFoundError:
        try:
            _write_json(CONFIG_PATH, cfg)   # 首次运行才创建
        except Exception:
            pass
    except Exception:
        # 配置写坏了时用默认值跑，但不覆盖用户文件
        pass
    return cfg


def load_state(cfg=None):
    """读取运行时状态；旧版把 fish 存在 config.json 里，这里做一次性迁移。"""
    state = dict(DEFAULT_STATE)
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                state.update(raw)
        except Exception:
            pass
        return state

    if cfg and "fish" in cfg:
        try:
            state["fish"] = int(cfg.get("fish") or 0)
        except (TypeError, ValueError):
            pass
    try:
        _write_json(STATE_PATH, state)
    except Exception:
        pass
    if cfg and "fish" in cfg:
        cfg.pop("fish", None)               # 迁移后配置里不再留这个字段
        try:
            _write_json(CONFIG_PATH, cfg)
        except Exception:
            pass
    return state


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    state = load_state(cfg)
    pet = PetWindow(cfg, DataSource(cfg), state)
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
    tm.addAction("打个招呼", lambda: pet.on_event("greet") or pet.play("wave"))
    tm.addAction("回到右下角", lambda: (pet.show_pet(), pet._place_bottom_right()))
    tm.addAction("查看热帖榜", pet.toggle_panel)
    tm.addAction("立即刷新", pet.refresh)
    tm.addSeparator()
    tm.addAction("打开形象工作台", pet.open_studio)
    tm.addAction("重新同步形象", pet.force_studio_sync)
    tm.addSeparator()
    tm.addAction("退出", pet._quit)
    tray.setContextMenu(tm)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

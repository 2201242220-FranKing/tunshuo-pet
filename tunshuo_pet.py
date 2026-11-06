#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豚说小豚 · 桌面宠物 Demo（macOS / tkinter，无第三方依赖）
=========================================================
功能：
  1. 桌面上有一只可拖动的小豚宠物，会眨眼、晃动、吐气泡
  2. 定时拉取论坛最新动态 / 热帖（有新帖时气泡 + macOS 系统通知提醒）
  3. 右键菜单：查看热帖 / 立即刷新 / 暂停提醒 / 退出
  4. 支持接入真实论坛 API（在 config.json 里填 api_url）

运行：python3 tunshuo_pet.py
接口约定：GET api_url 返回 JSON，形如
  {"posts": [{"title": "...", "author": "...", "heat": 123, "time": "...", "url": "https://..."}]}
或直接返回 posts 数组也可以。字段缺失会自动兜底。
"""

import json
import os
import queue
import random
import subprocess
import threading
import time
import urllib.request
import webbrowser

import tkinter as tk
from tkinter import ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_url": "",                 # 论坛接口地址；留空则使用内置演示数据
    "poll_interval_minutes": 3,    # 轮询间隔（分钟）
    "notify_system": True,         # 是否使用 macOS 系统通知
    "window_alpha": 0.95           # 窗口整体透明度（macOS 支持）
}


# ----------------------------------------------------------------------
# 演示数据：模拟论坛帖子池
# ----------------------------------------------------------------------
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
    "英语四六级准考证打印通道已开放",
    "隔壁新开的奶茶店第二杯半价，测评来了",
]

MOCK_AUTHORS = ["阿豚不吃香菜", "图书馆钉子户", "4点睡的秃头人", "食堂评论家",
                "打工豚", "酸奶盖收藏家", "早八幸存者", "小肚腩战士"]

MOCK_TAGS = ["闲置", "活动", "学习", "优惠", "拼车", "求助", "表白", "失物"]


def make_mock_post(idx):
    return {
        "id": "mock-%d-%d" % (idx, random.randint(1000, 9999)),
        "title": random.choice(MOCK_POOL),
        "author": random.choice(MOCK_AUTHORS),
        "tag": random.choice(MOCK_TAGS),
        "heat": random.randint(30, 600),
        "time": "刚刚",
        "url": None,
    }


class DataSource:
    """数据源：api_url 非空走真实接口，否则用演示数据。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mock_count = 0
        self._lock = threading.Lock()

    def fetch(self):
        url = (self.cfg.get("api_url") or "").strip()
        if url:
            return self._fetch_api(url)
        return self._fetch_mock()

    def _fetch_api(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "TunshuoPet/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
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

    def _fetch_mock(self):
        with self._lock:
            self.mock_count += 1
            posts = [make_mock_post(i) for i in range(8)]
            # 模拟"有新帖产生"：每隔几次拉取，出现一条新动态，方便演示提醒效果
            if self.mock_count % 2 == 0:
                posts.insert(0, make_mock_post(9000 + self.mock_count))
            for p in posts:
                p["time"] = "刚刚" if p["heat"] > 500 else "%d分钟前" % random.randint(3, 90)
            return posts


# ----------------------------------------------------------------------
# 桌面宠物应用
# ----------------------------------------------------------------------
class PetApp:
    PET_W, PET_H = 260, 300

    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = self._load_config()
        self.source = DataSource(self.cfg)
        self.msg_q = queue.Queue()
        self.seen_ids = set()
        self.posts = []
        self.notify_paused = False
        self._blink_open = True
        self._drag_start = None
        self._drag_moved = 0

        self._setup_window()
        self._setup_ui()
        self._setup_menu()
        self._start_worker()
        self._animate()

        self.root.after(300, self._drain_queue)

    # ---------------- 配置 ----------------
    def _load_config(self):
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

    # ---------------- 窗口 ----------------
    def _setup_window(self):
        r = self.root
        r.title("豚说小豚")
        r.overrideredirect(True)               # 无边框
        r.attributes("-topmost", True)         # 永远置顶
        try:
            r.attributes("-alpha", float(self.cfg.get("window_alpha", 0.95)))
        except Exception:
            pass
        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        r.geometry("%dx%d+%d+%d" % (self.PET_W, self.PET_H, sw - self.PET_W - 40, sh - self.PET_H - 90))
        r.configure(bg="#FFF3E9")

    def _setup_ui(self):
        # 气泡区
        self.bubble = tk.Label(
            self.root, text="喂！我是豚说小豚～\n右键点我有菜单哦",
            font=("PingFang SC", 12), bg="#FFFFFF", fg="#8A4B60",
            wraplength=230, justify="left", anchor="w",
            padx=10, pady=8, relief="flat", highlightthickness=1,
            highlightbackground="#F2C7D5"
        )
        self.bubble.pack(fill="x", padx=8, pady=(8, 0))
        self.bubble.bind("<Button-1>", lambda e: self._bubble_say_idle())

        # 宠物画布
        self.cv = tk.Canvas(self.root, width=self.PET_W, height=240,
                            bg="#FFF3E9", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self._draw_pet()
        self._bind_pet_events()

        # 底部状态栏
        self.status = tk.Label(self.root, text="演示模式 · 未接论坛接口",
                               font=("PingFang SC", 9), bg="#FFF3E9", fg="#B98A99")
        self.status.pack(fill="x", pady=(0, 4))

    # ---------------- 小豚绘制 ----------------
    def _draw_pet(self):
        cv, cx, cy = self.cv, 130, 150
        # 影子
        cv.create_oval(cx - 60, cy + 62, cx + 60, cy + 80, fill="#F6DCD2", outline="")
        # 耳朵
        cv.create_polygon(cx - 52, cy - 48, cx - 30, cy - 78, cx - 14, cy - 46,
                          fill="#F7A8C4", outline="#D97FA5", width=2)
        cv.create_polygon(cx + 52, cy - 48, cx + 30, cy - 78, cx + 14, cy - 46,
                          fill="#F7A8C4", outline="#D97FA5", width=2)
        # 身体
        cv.create_oval(cx - 68, cy - 55, cx + 68, cy + 70,
                          fill="#F9B7CF", outline="#D97FA5", width=2)
        # 鼻子
        cv.create_oval(cx - 30, cy - 12, cx + 30, cy + 28,
                          fill="#F472A0", outline="#C9557E", width=2)
        cv.create_oval(cx - 16, cy + 2, cx - 6, cy + 16, fill="#A93666", outline="")
        cv.create_oval(cx + 6, cy + 2, cx + 16, cy + 16, fill="#A93666", outline="")
        # 眼睛（记录 id，方便眨眼）
        self.eye_l = cv.create_oval(cx - 44, cy - 38, cx - 26, cy - 16,
                                       fill="#4A2333", outline="")
        self.eye_r = cv.create_oval(cx + 26, cy - 38, cx + 44, cy - 16,
                                       fill="#4A2333", outline="")
        # 腮红
        cv.create_oval(cx - 62, cy - 6, cx - 42, cy + 8, fill="#F9D5E3", outline="")
        cv.create_oval(cx + 42, cy - 6, cx + 62, cy + 8, fill="#F9D5E3", outline="")
        # 嘴
        cv.create_arc(cx - 14, cy + 4, cx + 14, cy + 26, start=200, extent=140,
                      style=tk.ARC, outline="#A93666", width=2)
        self.pet_cy = cy

    def _blink(self):
        cv = self.cv
        if self._blink_open:
            for item in (self.eye_l, self.eye_r):
                cv.itemconfigure(item, state="hidden")
            cx, cy = 130, self.pet_cy
            cv.create_line(cx - 46, cy - 26, cx - 24, cy - 26, fill="#4A2333", width=3, tags="blink")
            cv.create_line(cx + 24, cy - 26, cx + 46, cy - 26, fill="#4A2333", width=3, tags="blink")
            self._blink_open = False
        else:
            for item in (self.eye_l, self.eye_r):
                cv.itemconfigure(item, state="normal")
            cv.delete("blink")
            self._blink_open = True

    def _animate(self):
        # 眨眼
        if random.random() < 0.25:
            self._blink()
        else:
            if not self._blink_open:
                self._blink()
        # 轻微浮动
        dy = random.choice([-2, 2, 0, 0])
        self.cv.move("all", 0, dy)
        self.root.after(700, self._animate)

    # ---------------- 事件绑定 ----------------
    def _bind_pet_events(self):
        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Button-3>", self._show_menu)
        # macOS 触控板/某些鼠标中键当右键
        self.cv.bind("<Button-2>", self._show_menu)

    def _on_press(self, e):
        self._drag_start = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self._drag_moved = 0

    def _on_drag(self, e):
        if not self._drag_start:
            return
        x0, y0, wx, wy = self._drag_start
        dx, dy = e.x_root - x0, e.y_root - y0
        self._drag_moved = max(self._drag_moved, abs(dx) + abs(dy))
        self.root.geometry("+%d+%d" % (wx + dx, wy + dy))

    def _on_release(self, e):
        if self._drag_moved < 6:
            self.toggle_hot_panel()
        self._drag_start = None

    # ---------------- 菜单 ----------------
    def _setup_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="查看热帖 / 最新动态", command=self.toggle_hot_panel)
        m.add_command(label="立即刷新", command=self.request_refresh)
        self.pause_var = tk.BooleanVar(value=False)
        m.add_checkbutton(label="暂停新帖提醒", variable=self.pause_var,
                          command=self._toggle_pause)
        m.add_separator()
        m.add_command(label="退出小豚", command=self.root.destroy)
        self.menu = m

    def _show_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _toggle_pause(self):
        self.notify_paused = self.pause_var.get()
        self._bubble_say("好的，%s" % ("我先不打扰你了" if self.notify_paused else "有新帖我会马上喊你！"))

    # ---------------- 气泡 ----------------
    def _bubble_say(self, text):
        self.bubble.config(text=text)

    def _bubble_say_idle(self):
        idle = ["今天也要好好逛论坛哦～", "有热帖我盯着呢，放心！",
                "点我可以看热帖，右键有菜单～", "论坛又热闹起来了！"]
        self._bubble_say(random.choice(idle))

    # ---------------- 热帖面板 ----------------
    def toggle_hot_panel(self):
        if hasattr(self, "panel") and self.panel.winfo_exists():
            self.panel.destroy()
            return
        panel = tk.Toplevel(self.root)
        panel.title("豚说 · 热帖与最新动态")
        panel.geometry("460x380")
        panel.attributes("-topmost", True)
        panel.configure(bg="#FFF3E9")
        self.panel = panel

        head = tk.Label(panel, text="热帖榜（按热度排序）", font=("PingFang SC", 12, "bold"),
                        bg="#FFF3E9", fg="#8A4B60")
        head.pack(pady=(8, 2))

        cols = ("title", "author", "heat", "time")
        tree = ttk.Treeview(panel, columns=cols, show="headings", height=12)
        tree.heading("title", text="标题")
        tree.heading("author", text="作者")
        tree.heading("heat", text="热度")
        tree.heading("time", text="时间")
        tree.column("title", width=240)
        tree.column("author", width=90, anchor="center")
        tree.column("heat", width=50, anchor="center")
        tree.column("time", width=70, anchor="center")
        tree.pack(fill="both", expand=True, padx=8, pady=4)

        tip = tk.Label(panel, text="双击打开帖子链接（演示数据无链接）",
                       font=("PingFang SC", 9), bg="#FFF3E9", fg="#B98A99")
        tip.pack(pady=(0, 6))

        for p in self._sorted_posts():
            tree.insert("", "end", iid=p["id"], values=(p["title"], p["author"], p["heat"], p["time"]))

        def on_open(_e):
            sel = tree.selection()
            if not sel:
                return
            post = next((x for x in self.posts if x["id"] == sel[0]), None)
            if post and post.get("url"):
                webbrowser.open(post["url"])
            else:
                self._bubble_say("这条是演示数据，还没有链接～")
        tree.bind("<Double-1>", on_open)

    def _sorted_posts(self):
        return sorted(self.posts, key=lambda x: -x["heat"])[:50]

    # ---------------- 后台轮询 ----------------
    def _start_worker(self):
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def _poll_loop(self):
        interval = max(1, int(self.cfg.get("poll_interval_minutes", 3))) * 60
        while True:
            try:
                posts = self.source.fetch()
                self.msg_q.put(("posts", posts))
            except Exception as ex:
                self.msg_q.put(("error", str(ex)))
            time.sleep(interval)

    def request_refresh(self):
        self._bubble_say("正在刷新论坛动态…")

        def work():
            try:
                posts = self.source.fetch()
                self.msg_q.put(("posts", posts))
            except Exception as ex:
                self.msg_q.put(("error", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.msg_q.get_nowait()
                if kind == "posts":
                    self._on_posts(payload)
                elif kind == "error":
                    self._bubble_say("拉取失败：%s" % payload[:60])
        except queue.Empty:
            pass
        self.root.after(300, self._drain_queue)

    def _on_posts(self, posts):
        first = not self.posts
        self.posts = posts
        new_ones = [p for p in posts if p["id"] not in self.seen_ids]
        for p in posts:
            self.seen_ids.add(p["id"])
        if first:
            self._bubble_say("拿到最新动态啦！\n点我查看热帖，右键有菜单～")
            self._set_status()
            return
        if new_ones and not self.notify_paused:
            top = sorted(new_ones, key=lambda x: -x["heat"])[0]
            self._bubble_say("有新帖啦！🔥\n「%s」\n—— %s（热度 %d）"
                             % (top["title"][:18], top["author"], top["heat"]))
            self._system_notify("豚说小豚", "新帖：「%s」热度 %d" % (top["title"][:20], top["heat"]))
        self._set_status()
        if hasattr(self, "panel") and self.panel.winfo_exists():
            self.toggle_hot_panel()   # 关闭旧面板
            self.toggle_hot_panel()   # 用新数据重建

    def _set_status(self):
        if self.cfg.get("api_url"):
            self.status.config(text="已接入论坛接口 · 每 %d 分钟刷新" % max(1, int(self.cfg.get("poll_interval_minutes", 3))))
        else:
            self.status.config(text="演示模式 · 在 config.json 填 api_url 接入真实论坛")

    # ---------------- 系统通知 ----------------
    def _system_notify(self, title, msg):
        if not self.cfg.get("notify_system", True):
            return
        if sys.platform != "darwin":
            return
        msg = msg.replace('"', "'")
        title = title.replace('"', "'")
        script = 'display notification "%s" with title "%s" subtitle "论坛动态"' % (msg, title)
        try:
            subprocess.Popen(["osascript", "-e", script],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def main():
    root = tk.Tk()
    PetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

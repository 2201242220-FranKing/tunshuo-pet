#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说论坛 REST 接口适配层（按 2026-11-10 真实响应校准，默认不启用）。

线上地址：https://alumni.qiyuanheshan.com

技术提供的接口：

  GET /app/dynamic/page        最新帖子   circleId / pageNum / pageSize / type / tagId
  GET /app/dynamic/new/num     新帖提醒数 circleId / time / type / tagId
  GET /app/dynamic/ten/page    十大热帖   circleId
  GET /app/dynamic/detail      帖子详情   id
  GET /app/dynamic/ten/page    ⚠️ 文档里「站内信未读」写成了同一个路径，待技术确认

真实外层结构（已实测）：

  {"code":200, "data":[ {...帖子...} ], "encrypt":false,
   "exception":null, "message":"请求成功", "recordsTotal":7614}

`data` 直接是**帖子数组**（不是 records/list 包裹），`recordsTotal` 在顶层。
`code=400` 是参数错误，`code=110 / message=请先登录` 是缺登录态。

实测鉴权差异（重要）：
  - `/app/dynamic/page`、`/app/dynamic/detail` 匿名即可读；
  - `/app/dynamic/ten/page`、`/app/dynamic/new/num` 返回 code=110「请先登录」。
  因此默认不依赖这两个接口：十大热帖拿不到时，自动改用最新帖按 `totalHeatNum`
  降序出榜（上层 HotPanel 本来就按 heat 排序），桌宠零令牌也能跑。
  若技术给了匿名榜单接口或愿意用环境变量临时提供 token，榜单会自动切回真实十大。

帖子真实字段 → 桌宠 7 字段：

  id          <- id（19 位字符串；dynamicNo 是短编号，仅兜底）
  title       <- content 正文摘要（真实数据没有 title 字段，取首 38 字）
  author      <- userName
  tag         <- tagList[0].name，兜底 circleTitle
  heat        <- totalHeatNum，兜底 heatNum / zanNum / commentsNum / browseNum
  time        <- createTime
  url         <- 接口未返回；等技术给 H5 规则后填 config 的 forum_detail_url

设计约束：
  1. **默认完全不启用**：`forum_base` 留空时 `make_source()` 原样返回旧 DataSource，
     演示数据、气泡、热帖榜表现零回归；自动轮询仍默认关闭。
  2. 所有字段名猜测集中在 `SCHEMA`，技术改字段时只改这个字典
     （或 config.json 的 `forum_schema`），不用动逻辑。
  3. 传输层可注入：离线自测 `python3 forum_api.py --selftest` 不发一个网络请求；
     联网自检 `python3 forum_api.py --live --circle-id <学校圈子ID>`。
  4. **不保存令牌**：token 只从环境变量 `TUNSHUO_FORUM_TOKEN` 读，
     绝不写进会入库的 config.json / studio_cache.json。
  5. 只依赖标准库，不引入新框架。

仍需技术确认：站内信未读的正确路径、原帖 H5 链接规则、学校 circleId 的实际值、
`new/num` 的 time 语义、tagId 枚举。
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

TOKEN_ENV = "TUNSHUO_FORUM_TOKEN"
KNOWN_BASE = "https://alumni.qiyuanheshan.com"   # 仅用于文档与 --live 自检，不是启用开关

P_LATEST = "/app/dynamic/page"
P_NEW_NUM = "/app/dynamic/new/num"
P_TOP_TEN = "/app/dynamic/ten/page"
P_DETAIL = "/app/dynamic/detail"
# 文档疑似笔误：站内信未读与十大热帖路径重复。确认后改这一行即可启用。
UNREAD_PATH = None

# 候选字段名按优先级尝试。真实接口字段已提到最前面。
SCHEMA = {
    "code": ("code", "status", "errCode", "errno", "resultCode"),
    "ok_codes": (0, 200, "0", "200", "SUCCESS", "success", "ok", True),
    "auth_codes": (110, 401, 403, "110", "401", "403"),
    "message": ("msg", "message", "errmsg", "errorMsg", "errorMessage"),
    "payload": ("data", "result", "body", "content"),
    "list": ("records", "list", "rows", "items", "data", "content", "result"),
    "number": ("num", "count", "newNum", "newCount", "unread", "unreadNum"),
    "total": ("recordsTotal", "total", "totalCount", "totalSize"),
    "encrypt": ("encrypt", "isEncrypt", "encrypted"),
    "title_max": 38,
    "post": {
        "id": ("id", "dynamicId", "postId", "dynamicNo", "编号"),
        "title": ("title", "dynamicTitle", "subject", "name"),
        "content": ("content", "dynamicContent", "text", "body"),
        "author": ("userName", "nickname", "author", "userNickname",
                   "authorName", "createBy", "publisher"),
        "tag": ("tagName", "tag", "tagTitle", "labelName", "categoryName",
                "typeName", "circleTitle"),
        "tag_list": ("tagList", "tags", "tagNames"),
        "tag_name": ("name", "tagName", "title", "labelName"),
        "time": ("createTime", "publishTime", "time", "createdAt", "createDate", "date"),
        "heat": ("totalHeatNum", "heatNum", "heat", "hot", "zanNum", "likeCount",
                 "likeNum", "commentCount", "commentsNum", "viewCount", "browseNum",
                 "browseCount", "readCount"),
        "url": ("url", "link", "h5Url", "shareUrl", "detailUrl"),
    },
}


class ForumError(Exception):
    """接口层错误，消息会直接显示在桌宠气泡里，所以保持简短可读。"""


class ForumAuthError(ForumError):
    """需要登录态（code=110 等）。调用方会停止重试该接口，避免反复无效请求。"""


def _pick(d, keys, default=None):
    """按候选键顺序取第一个非空值。"""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def _as_number(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_url(v):
    """与旧 DataSource 同一套白名单：只放行 http(s)，挡住 javascript:/file:。"""
    return v if isinstance(v, str) and v.startswith(("http://", "https://")) else None


def _summarize(text, limit=38):
    """真实帖子没有标题字段，用正文首句做气泡标题：去链接、并空白、话题转方括号。"""
    s = re.sub(r"https?://\S+", "", str(text or ""))
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^#([^#]{1,20})#\s*", r"[\1] ", s)
    limit = max(8, min(120, _as_number(limit, 38)))
    if len(s) > limit:
        s = s[:limit - 1] + "…"
    return s or "(无标题动态)"


def _tag_of(p, f):
    """真实接口把标签放在 tagList[0].name，圈子名 circleTitle 只作兜底。"""
    lst = _pick(p, f["tag_list"])
    if isinstance(lst, list):
        for it in lst:
            if isinstance(it, str) and it.strip():
                return it.strip()[:30]
            if isinstance(it, dict):
                n = _pick(it, f["tag_name"])
                if n:
                    return str(n)[:30]
    return str(_pick(p, f["tag"], ""))[:30]


def _unwrap(raw, schema):
    """剥掉外层包裹，返回列表 / 数字 / 原始 dict。

    兼容真实 `{code,data:[...],recordsTotal}`、裸数组、
    `{code,data:{records,total}}`、`{code,data:[...]}`、`{code,data:8}`、详情对象。
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        raise ForumError("接口返回格式不认识")

    code = _pick(raw, schema["code"])
    if code is not None and code not in schema["ok_codes"]:
        msg = str(_pick(raw, schema["message"], "接口返回失败码 %s" % code))[:60]
        if code in schema["auth_codes"]:
            raise ForumAuthError(msg)
        raise ForumError(msg)
    if _pick(raw, schema["encrypt"]):
        raise ForumError("论坛响应已加密，需技术提供解密方式")

    payload = _pick(raw, schema["payload"], default=raw)
    if isinstance(payload, (list, int, float, str, bool)):
        return payload
    if isinstance(payload, dict):
        lst = _pick(payload, schema["list"])
        if isinstance(lst, list):
            return lst
        num = _pick(payload, schema["number"])
        if num is not None:
            return num
        return payload                      # 详情接口：直接返回原始对象
    raise ForumError("接口数据结构不认识")


def _normalize_posts(items, schema, detail_url_tpl=""):
    """映射成桌宠现有 7 字段：id/title/author/tag/heat/time/url。"""
    f = schema["post"]
    limit = schema.get("title_max", 38)
    out = []
    for i, p in enumerate(items[:100]):
        if not isinstance(p, dict):
            continue
        pid = _pick(p, f["id"])
        raw_title = _pick(p, f["title"])
        if raw_title not in (None, ""):
            title = str(raw_title)[:120]
        else:
            title = _summarize(_pick(p, f["content"]), limit)
        pid = str(pid) if pid not in (None, "") else title or str(i)
        link = _safe_url(_pick(p, f["url"]))
        if not link and detail_url_tpl:
            try:
                link = _safe_url(detail_url_tpl.format(id=pid))
            except (KeyError, IndexError, ValueError):
                link = None
        out.append({
            "id": pid,
            "title": title,
            "author": str(_pick(p, f["author"], "豚友"))[:60],
            "tag": _tag_of(p, f),
            "heat": _as_number(_pick(p, f["heat"], 0)),
            "time": str(_pick(p, f["time"], ""))[:30],
            "url": link,
        })
    return out


def _default_transport(url, headers, timeout=10):
    """默认 HTTP GET。返回原始文本，交给 _get 解析。"""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ForumError("接口 HTTP %s" % e.code)
    except urllib.error.URLError as e:
        raise ForumError("连不上论坛：%s" % str(e.reason)[:40])
    except Exception as e:
        raise ForumError("请求失败：%s" % str(e)[:40])


class ForumClient:
    """只负责「发请求 + 解析」，不带任何状态，方便单独自测。"""

    def __init__(self, base, circle_id="", token="", token_header="Authorization",
                 transport=None, schema=None, detail_url_tpl="", timeout=10,
                 unread_path=None, allow_all=False):
        base = str(base or "").strip().rstrip("/")
        if not re.match(r"^https?://", base):
            raise ForumError("forum_base 必须是 http(s):// 开头的完整地址")
        self.base = base
        self.circle_id = str(circle_id or "").strip()
        self.allow_all = bool(allow_all)
        self.token = token or ""                # 只从环境变量来，不读配置文件
        self.token_header = token_header or "Authorization"
        self.transport = transport or _default_transport
        self.schema = schema or SCHEMA
        self.detail_url_tpl = detail_url_tpl or ""
        self.timeout = timeout
        self.unread_path = unread_path if unread_path is not None else UNREAD_PATH
        self.calls = []                          # 自测用：记录请求过的 URL
        self.last_total = None                   # 顶层 recordsTotal，供以后做分页

    @classmethod
    def from_config(cls, cfg, **kw):
        """从 config.json 构造。token 特意只认环境变量。"""
        schema = dict(SCHEMA)
        override = cfg.get("forum_schema")
        if isinstance(override, dict):
            for k, v in override.items():
                if k == "post" and isinstance(v, dict):
                    schema["post"] = dict(schema["post"], **v)
                else:
                    schema[k] = v
        return cls(
            base=cfg.get("forum_base"),
            circle_id=cfg.get("forum_circle_id"),
            token=os.environ.get(TOKEN_ENV, ""),
            token_header=cfg.get("forum_token_header") or "Authorization",
            schema=schema,
            detail_url_tpl=cfg.get("forum_detail_url") or "",
            allow_all=bool(cfg.get("forum_allow_all", False)),
            timeout=10,
            **kw)

    def _get(self, path, params=None):
        q = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        url = self.base + path
        if q:
            url += "?" + urllib.parse.urlencode(q)
        self.calls.append(url)
        headers = {"User-Agent": "TunshuoPet/4.0", "Accept": "application/json"}
        if self.token:
            headers[self.token_header] = self.token
        raw = self.transport(url, headers)
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raise ForumError("接口返回的不是 JSON")
        if isinstance(raw, dict):
            self.last_total = _as_number(_pick(raw, self.schema["total"]), None)
        return _unwrap(raw, self.schema)

    def _circle(self):
        if self.circle_id:
            return self.circle_id
        if self.allow_all:
            return ""            # 不传 circleId：接口会返回全站（不按学校筛选）
        raise ForumError("请配置 forum_circle_id（学校圈子 ID）")

    # ---- 五个接口 ----
    def latest(self, page_num=1, page_size=10, post_type="dynamic", tag_id=None):
        raw = self._get(P_LATEST, {
            "circleId": self._circle(), "pageNum": page_num, "pageSize": page_size,
            "type": post_type, "tagId": tag_id,
        })
        return _normalize_posts(raw if isinstance(raw, list) else [], self.schema,
                                self.detail_url_tpl)

    def new_count(self, since, post_type="dynamic", tag_id=None):
        raw = self._get(P_NEW_NUM, {
            "circleId": self._circle(), "time": since,
            "type": post_type, "tagId": tag_id,
        })
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, dict):
            return _as_number(_pick(raw, self.schema["number"]))
        return _as_number(raw)

    def top_ten(self):
        raw = self._get(P_TOP_TEN, {"circleId": self._circle()})
        posts = _normalize_posts(raw if isinstance(raw, list) else [], self.schema,
                                 self.detail_url_tpl)
        # 榜单接口可能已排好序但不返回热度值：按返回顺序补一个递减分，
        # 保证 HotPanel 按 heat 降序渲染时不至于全 0 乱序。
        if posts and all(p["heat"] == 0 for p in posts):
            for i, p in enumerate(posts):
                p["heat"] = 1000 - i * 10
        return posts

    def unread(self):
        if not self.unread_path:
            raise ForumError("站内信未读接口路径待技术确认（文档与十大热帖重复）")
        raw = self._get(self.unread_path, {"circleId": self._circle()})
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, dict):
            return _as_number(_pick(raw, self.schema["number"]))
        return _as_number(raw)

    def detail(self, post_id):
        """返回接口原始对象；以后做「面板内看详情」时再解析，现在不消费。"""
        return self._get(P_DETAIL, {"id": post_id})


class ForumAdapter:
    """给 Fetcher 用的数据源：fetch() 返回完整的 7 字段帖子列表。

    上层 `_on_posts()` 自己用 seen 比对 id 判新帖，所以这里必须返回**完整榜单**，
    不能只回新增条目，否则热帖榜会被清空。
    """

    def __init__(self, cfg, fallback=None, client=None):
        self.client = client or ForumClient.from_config(cfg)
        self.fallback = fallback
        self.probe = bool(cfg.get("forum_probe", False))   # time 语义确认前默认关闭
        self.page_size = max(1, min(50, _as_number(cfg.get("forum_page_size"), 10)))
        self.fallback_size = max(self.page_size,
                                 min(50, _as_number(cfg.get("forum_top_fallback_size"), 20)))
        self._last = []
        self._last_sync = None
        self._top_disabled = False           # 十大热帖要求登录时不再反复请求
        self.last_warning = ""

    def fetch(self):
        # 可选省流量策略：new/num 探活，返回 0 且已有缓存时直接复用上一轮结果。
        # 依赖「time 上次刷新时间」的确切语义，确认后才把 forum_probe 打开。
        if self.probe and self._last and self._last_sync:
            since = self._last_sync.strftime("%Y-%m-%d %H:%M:%S")
            try:
                if self.client.new_count(since) <= 0:
                    return list(self._last)
            except ForumAuthError:
                self.probe = False           # 需要登录的接口别再反复打
            except ForumError:
                pass                         # 探活失败不影响正常拉取

        errors, posts = [], []
        size = self.page_size
        if self._top_disabled:
            size = self.fallback_size
        else:
            try:
                posts.extend(self.client.top_ten())
            except ForumAuthError as e:
                # 线上 ten/page 返回 code=110「请先登录」：降级为「最新帖按热度排序」，
                # 并记住本次会话不再请求，避免每次刷新都白打一次。
                self._top_disabled = True
                self.last_warning = "十大热帖需登录（%s），已改用最新帖按热度出榜" % e
                size = self.fallback_size
            except ForumError as e:
                self.last_warning = "十大热帖不可用（%s），已改用最新帖按热度出榜" % e
                size = self.fallback_size

        try:
            posts.extend(self.client.latest(page_size=size))
        except ForumError as e:
            errors.append("最新帖子：%s" % e)
        if not posts:
            # 两个接口都失败：有旧数据就沿用，避免热帖榜被清空；否则才报错。
            if self._last:
                return list(self._last)
            raise ForumError("；".join(errors)[:80] or "没有取到帖子")

        merged = {}
        for p in posts:                      # 十大热帖先入，保证榜单优先级
            merged.setdefault(p["id"], p)
        out = list(merged.values())
        self._last, self._last_sync = out, datetime.now()
        return out


def make_source(cfg, fallback):
    """唯一的启用开关：没填 forum_base 就完全不启用，原样返回旧数据源。"""
    if not str(cfg.get("forum_base") or "").strip():
        return fallback
    return ForumAdapter(cfg, fallback=fallback)


# ----------------------------------------------------------------------
# 离线自测：不联网、不读配置、不碰桌宠进程
#   python3 forum_api.py --selftest
# ----------------------------------------------------------------------
def _selftest():
    ok = 0

    def check(name, cond, extra=""):
        nonlocal ok
        assert cond, "FAIL %s %s" % (name, extra)
        ok += 1
        print("  OK  %s" % name)

    def client(handler, **kw):
        return ForumClient("https://forum.example.com", circle_id="CIRCLE_1",
                           transport=lambda u, h: handler(u, h), **kw)

    # 真实接口的一条帖子（字段照抄实测结构，值已虚构）
    real_post = {
        "id": "2120019718319501314", "dynamicNo": "261110AB48RD",
        "content": "   #校园趣事#   今天食堂的豚豚饭买一送一 https://example.com/x "
                   "详情看图，欢迎大家来拼单，人数够了就一起下单，晚上九点截止报名啦  ",
        "userName": "图书馆钉子户", "createTime": "2026-11-10 13:04:24",
        "tagList": [{"name": "宣传推广", "type": "dynamic"}],
        "circleTitle": "某大学", "circleId": "1844924022131912706",
        "heatNum": 50, "totalHeatNum": 96, "zanNum": 2,
        "commentsNum": 5, "browseNum": 34, "pics": "a.jpg,b.jpg",
        "type": "dynamic",
    }
    real = {"code": 200, "data": [real_post], "encrypt": False,
            "exception": None, "message": "请求成功", "recordsTotal": 7614}

    print("1) 真实响应结构与字段映射")
    c = client(lambda u, h: real)
    posts = c.latest()
    p = posts[0]
    check("data 是数组时解析出 1 条", len(posts) == 1)
    check("7 字段齐全", set(p) == {"id", "title", "author", "tag", "heat", "time", "url"})
    check("id 用长 id 而非短编号", p["id"] == "2120019718319501314")
    check("正文生成短标题（不是整段 97 字）", len(p["title"]) <= 38
          and "https" not in p["title"], p["title"])
    check("话题转为方括号前缀", p["title"].startswith("[校园趣事]"), p["title"])
    check("作者 userName 映射", p["author"] == "图书馆钉子户")
    check("标签取 tagList[0].name", p["tag"] == "宣传推广")
    check("热度取 totalHeatNum", p["heat"] == 96)
    check("时间取 createTime", p["time"] == "2026-11-10 13:04:24")
    check("接口无 url 时留空（双击不跳转）", p["url"] is None)
    check("顶层 recordsTotal 被记录", c.last_total == 7614)
    check("拼接参数正确", "circleId=CIRCLE_1" in c.calls[0]
          and "pageNum=1" in c.calls[0] and "type=dynamic" in c.calls[0])

    print("2) 旧约定 / 多种外层包裹继续兼容")
    ruoyi = {"code": 200, "msg": "ok", "data": {"records": [
        {"id": "1024", "title": "周三操场音乐会", "nickname": "甲",
         "tagName": "活动", "likeCount": 328, "createTime": "2026-11-10 12:00:00",
         "url": "https://forum.example.com/t/1024"},
        {"id": "1025", "title": "出一台 iPad", "nickname": "乙",
         "tagName": "闲置", "likeCount": "88", "createTime": "2026-11-10 12:05:00"},
    ], "total": 2}}
    old = client(lambda u, h: ruoyi).latest()
    check("若依 records 解析出 2 条", len(old) == 2)
    check("显式 title 字段不被摘要覆盖", old[0]["title"] == "周三操场音乐会")
    check("旧作者/标签/热度映射", old[0]["author"] == "甲"
          and old[0]["tag"] == "活动" and old[0]["heat"] == 328)
    check("热度数字字符串降级", old[1]["heat"] == 88)
    general = {"code": 0, "data": {"list": [
        {"dynamicId": "A1", "dynamicTitle": "热帖一", "userName": "甲"},
        {"dynamicId": "A2", "dynamicTitle": "热帖二", "userName": "乙"}]}}
    hot = client(lambda u, h: general).top_ten()
    check("通用 data.list + 动态字段名", len(hot) == 2 and hot[0]["id"] == "A1")
    check("无热度字段时按榜单顺序补分且递减",
          hot[0]["heat"] == 1000 and hot[1]["heat"] == 990)
    check("裸数组兼容", len(client(lambda u, h: [{"id": "z", "title": "裸数组"}]).top_ten()) == 1)

    print("3) 失败码 / 鉴权 / 加密 / 脏数据 / 链接白名单")
    try:
        client(lambda u, h: {"code": 500, "msg": "服务异常"}).top_ten()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("失败码带出服务端消息", "服务异常" in str(e))
    try:
        client(lambda u, h: {"code": 110, "message": "请先登录", "data": None}).top_ten()
        raise AssertionError("应抛 ForumAuthError")
    except ForumAuthError as e:
        check("code=110 识别为需登录", "请先登录" in str(e))
    try:
        client(lambda u, h: {"code": 200, "encrypt": True, "data": []}).top_ten()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("加密响应给出明确提示", "加密" in str(e))
    dirty = [{"id": "d1", "title": "脏数据", "heat": "abc",
              "url": "javascript:alert(1)", "nickname": None}]
    p2 = client(lambda u, h: dirty).latest()[0]
    check("脏热度降级为 0", p2["heat"] == 0)
    check("作者缺失回落", p2["author"] == "豚友")
    check("javascript 链接被挡", p2["url"] is None)
    tpl = client(lambda u, h: dirty, detail_url_tpl="https://forum.example.com/d/{id}")
    check("H5 模板拼出的链接放行", tpl.latest()[0]["url"] ==
          "https://forum.example.com/d/d1")
    check("空正文回落标题", client(lambda u, h: [{"id": "e1"}]).latest()[0]["title"]
          == "(无标题动态)")

    print("4) 新帖数 / 详情 / 站内信 / 圈子配置")
    c4 = client(lambda u, h: {"code": 0, "data": {"num": 3}})
    check("对象形态返回 3", c4.new_count("2026-11-10 12:00:00") == 3)
    check("time 参数格式", "time=2026-11-10+12%3A00%3A00" in c4.calls[0])
    check("纯数字形态", client(lambda u, h: {"code": 0, "data": 7})
          .new_count("2026-11-10 12:00:00") == 7)
    d = client(lambda u, h: {"code": 0, "data": {"id": "1024", "content": "详情"}})
    check("详情返回原始对象", d.detail("1024")["content"] == "详情")
    check("详情 id 参数", "id=1024" in d.calls[0])
    try:
        client(lambda u, h: {"code": 0, "data": 0}).unread()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("站内信路径未确认时明确报错", "待技术确认" in str(e))
    no_circle = ForumClient("https://forum.example.com",
                            transport=lambda u, h: {"code": 200, "data": []})
    try:
        no_circle.latest()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("未配 circleId 时给出明确引导", "forum_circle_id" in str(e))
    all_circle = ForumClient("https://forum.example.com", allow_all=True,
                             transport=lambda u, h: {"code": 200, "data": []})
    all_circle.latest()
    check("allow_all 时不带 circleId 参数", "circleId=" not in all_circle.calls[0])

    print("5) 聚合、降级与默认不启用")
    calls = []

    def mixed(u, h):
        calls.append(u)
        if "ten/page" in u:
            return {"code": 200, "data": [
                {"id": "A1", "content": "热帖一", "totalHeatNum": 50}]}
        return {"code": 200, "data": [
            {"id": "A1", "content": "热帖一（重复）", "totalHeatNum": 50},
            {"id": "B2", "content": "刚发的新帖", "totalHeatNum": 5}]}

    a = ForumAdapter({"forum_page_size": 10}, client=client(mixed))
    out = a.fetch()
    check("热帖 + 最新合并去重", len(out) == 2, str([x["id"] for x in out]))
    check("重复 id 保留热帖版本", out[0]["title"] == "热帖一")
    check("未开启探活时不请求 new/num", not any("new/num" in u for u in calls))

    auth_calls = []

    def needs_login(u, h):
        auth_calls.append(u)
        if "ten/page" in u:
            return {"code": 110, "message": "请先登录", "data": None}
        return {"code": 200, "data": [
            {"id": "L1", "content": "最新帖", "totalHeatNum": 42,
             "userName": "甲", "createTime": "2026-11-10 20:00:00"}]}

    a3 = ForumAdapter({"forum_page_size": 10}, client=client(needs_login))
    first = a3.fetch()
    check("十大热帖需登录时仍能出榜", len(first) == 1 and first[0]["heat"] == 42)
    check("降级提示可读", "需登录" in a3.last_warning)
    check("降级时扩大取样到 20", "pageSize=20" in auth_calls[1])
    ten_before = sum("ten/page" in u for u in auth_calls)
    a3.fetch()
    check("本会话不再反复请求需登录接口",
          sum("ten/page" in u for u in auth_calls) == ten_before)

    class Fallback:
        def fetch(self):
            return ["MOCK"]

    cfg_empty = dict(DEFAULT_LIKE_CONFIG)
    check("forum_base 为空时返回旧数据源",
          isinstance(make_source(cfg_empty, Fallback()), Fallback))
    cfg_on = dict(DEFAULT_LIKE_CONFIG, forum_base=KNOWN_BASE)
    check("填了 forum_base 才启用适配层",
          isinstance(make_source(cfg_on, Fallback()), ForumAdapter))
    check("默认不开启探活", ForumAdapter(cfg_on, client=client(mixed)).probe is False)

    print("6) 令牌与降级")
    seen_headers = {}

    def with_token(u, h):
        seen_headers.update(h)
        return {"code": 0, "data": 0}

    old_env = os.environ.pop(TOKEN_ENV, None)
    try:
        os.environ[TOKEN_ENV] = "TEST_ONLY_TOKEN"
        fc = ForumClient.from_config({"forum_base": "https://forum.example.com",
                                      "forum_circle_id": "CIRCLE_1"},
                                     transport=with_token)
        fc.new_count("2026-11-10 12:00:00")
        check("token 从环境变量进 Header", seen_headers.get("Authorization") ==
              "TEST_ONLY_TOKEN")
        check("令牌不写进配置字典", "token" not in cfg_empty)
    finally:
        os.environ.pop(TOKEN_ENV, None)
        if old_env is not None:
            os.environ[TOKEN_ENV] = old_env

    fail_client = client(lambda u, h: (_ for _ in ()).throw(ForumError("连不上")))
    a2 = ForumAdapter({}, client=fail_client, fallback=Fallback())
    a2._last = [{"id": "old", "title": "缓存"}]
    check("接口全挂时沿用上一轮结果", a2.fetch()[0]["id"] == "old")

    print("\nSELFTEST_OK %d 项通过" % ok)


# ----------------------------------------------------------------------
# 联网自检：只读，不写任何配置
#   python3 forum_api.py --live --circle-id <学校圈子ID>
#   python3 forum_api.py --live --all              # 不带圈子 ID，会拉全站
# ----------------------------------------------------------------------
def _arg(argv, name, default=""):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _mask(s):
    s = str(s or "")
    return (s[0] + "*" * (len(s) - 1)) if s else "-"


def _live_check(argv):
    base = _arg(argv, "--base", KNOWN_BASE)
    circle = _arg(argv, "--circle-id", "")
    allow_all = "--all" in argv or not circle
    cfg = {"forum_base": base, "forum_circle_id": circle,
           "forum_allow_all": allow_all, "forum_page_size": 5,
           "forum_top_fallback_size": 20, "forum_probe": False}
    print("联网自检（只读）：base=%s circle=%s 全站=%s"
          % (base, circle or "(未指定)", allow_all))
    c = ForumClient.from_config(cfg)
    for name, fn in (("最新帖子 page", lambda: c.latest()),
                     ("十大热帖 ten/page", lambda: c.top_ten()),
                     ("新帖数 new/num", lambda: c.new_count("2026-11-01 00:00:00"))):
        try:
            r = fn()
            desc = ("%d 条" % len(r)) if isinstance(r, list) else str(r)
            suffix = ("（recordsTotal=%s）" % c.last_total
                      if name == "最新帖子 page" else "")
            print("  OK   %s -> %s %s" % (name, desc, suffix))
        except ForumError as e:
            print("  WARN %s -> %s" % (name, e))
    try:
        first = c.latest(page_size=1)
        if first:
            detail = c.detail(first[0]["id"])
            print("  OK   详情 detail -> %d 个字段" % len(detail)
                  if isinstance(detail, dict) else "  WARN 详情返回非对象")
    except ForumError as e:
        print("  WARN 详情 detail ->", e)
    try:
        a = ForumAdapter(cfg, client=c)
        posts = a.fetch()
        print("\n聚合结果 %d 条（作者已打码）：" % len(posts))
        for p in posts[:5]:
            print("  [%s] %s | %s | %s | 热度 %d | %s | url=%s"
                  % (p["id"], p["title"], _mask(p["author"]), p["tag"] or "动态",
                     p["heat"], p["time"], "有" if p["url"] else "无（待 H5 规则）"))
        if a.last_warning:
            print("  降级提示：", a.last_warning)
    except ForumError as e:
        print("  ERROR 聚合失败：", e)


# 只在自测里模拟 config.json 的默认值，避免模块导入时依赖主程序
DEFAULT_LIKE_CONFIG = {
    "forum_base": "", "forum_circle_id": "", "forum_probe": False,
    "forum_page_size": 10, "forum_allow_all": False,
    "forum_top_fallback_size": 20,
}

if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    elif "--live" in sys.argv:
        _live_check(sys.argv)
    else:
        print(__doc__)

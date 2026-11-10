#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""豚说论坛 REST 接口适配层（骨架，默认不启用）。

技术提供的接口（2026-11-10）：

  GET /app/dynamic/page        最新帖子   circleId / pageNum / pageSize / type / tagId
  GET /app/dynamic/new/num     新帖提醒数 circleId / time / type / tagId
  GET /app/dynamic/ten/page    十大热帖   circleId
  GET /app/dynamic/ten/page    ⚠️ 文档里「站内信未读」写成了同一个路径，待技术确认
  GET /app/dynamic/detail      帖子详情   id

为什么单独一层：桌宠原来只有一个 `api_url`，约定返回一个帖子数组。技术给的是
一组 REST 接口，但上层 `_on_posts()` 去重播报、`HotPanel` 排序渲染、双击打开链接
都只认 7 个字段。适配层把多接口聚合成同样的 7 字段列表，上层零改动。

设计约束：
  1. **默认完全不启用**：`forum_base` 留空时 `make_source()` 原样返回旧 DataSource，
     演示数据、气泡、热帖榜表现零回归；自动轮询仍默认关闭。
  2. **返回结构未定也能跑**：所有字段名猜测集中在 `SCHEMA` 的候选键里，
     技术给了真实响应后只改这个字典（或 config.json 的 `forum_schema`），不用改逻辑。
  3. **传输层可注入**：离线用假响应自测 `python3 forum_api.py --selftest`。
  4. **不保存令牌**：token 只从环境变量 `TUNSHUO_FORUM_TOKEN` 读，
     绝不写进会入库的 config.json / studio_cache.json。
  5. 只依赖标准库，不引入新框架。

待技术确认后要动的只有三处：base URL、`SCHEMA` 字段映射、`UNREAD_PATH`。
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

TOKEN_ENV = "TUNSHUO_FORUM_TOKEN"

P_LATEST = "/app/dynamic/page"
P_NEW_NUM = "/app/dynamic/new/num"
P_TOP_TEN = "/app/dynamic/ten/page"
P_DETAIL = "/app/dynamic/detail"
# 文档疑似笔误：站内信未读与十大热帖路径重复。确认后改这一行即可启用。
UNREAD_PATH = None

# 候选字段名按优先级尝试。技术给真实响应示例后，把实际字段提到最前面即可。
# 结构参考了常见的分页封装（records/total 是若依系，list/data 是通用系）。
SCHEMA = {
    "code": ("code", "status", "errCode", "errno", "resultCode"),
    "ok_codes": (0, 200, "0", "200", "SUCCESS", "success", "ok", True),
    "message": ("msg", "message", "errmsg", "errorMsg", "errorMessage"),
    "payload": ("data", "result", "body", "content"),
    "list": ("records", "list", "rows", "items", "data", "content", "result"),
    "number": ("num", "count", "newNum", "newCount", "total", "unread", "unreadNum"),
    "post": {
        "id": ("id", "dynamicId", "postId", "dynamic_id", "dynamicNo", "编号"),
        "title": ("title", "dynamicTitle", "subject", "name", "content", "text"),
        "author": ("nickname", "author", "userName", "userNickname",
                   "authorName", "createBy", "publisher"),
        "tag": ("tagName", "tag", "tagTitle", "labelName", "categoryName", "typeName"),
        "time": ("createTime", "publishTime", "time", "createdAt", "createDate", "date"),
        "heat": ("heat", "hot", "likeCount", "likes", "commentCount",
                 "viewCount", "browseCount", "readCount"),
        "url": ("url", "link", "h5Url", "shareUrl", "detailUrl"),
    },
}


class ForumError(Exception):
    """接口层错误，消息会直接显示在桌宠气泡里，所以保持简短可读。"""


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


def _unwrap(raw, schema):
    """剥掉外层包裹，返回列表 / 数字 / 原始 dict。

    兼容：裸数组、`{code,data:{records,total}}`、`{code,data:[...]}`、
    `{code,data:8}`、`{code,data:{...}}`（详情）。
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        raise ForumError("接口返回格式不认识")

    code = _pick(raw, schema["code"])
    if code is not None and code not in schema["ok_codes"]:
        msg = _pick(raw, schema["message"], "接口返回失败码 %s" % code)
        raise ForumError(str(msg)[:60])

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
    out = []
    for i, p in enumerate(items[:100]):
        if not isinstance(p, dict):
            continue
        pid = _pick(p, f["id"])
        title = str(_pick(p, f["title"], "(无标题)"))[:120]
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
            "tag": str(_pick(p, f["tag"], ""))[:30],
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
                 unread_path=None):
        base = str(base or "").strip().rstrip("/")
        if not re.match(r"^https?://", base):
            raise ForumError("forum_base 必须是 http(s):// 开头的完整地址")
        self.base = base
        self.circle_id = str(circle_id or "").strip()
        self.token = token or ""                # 只从环境变量来，不读配置文件
        self.token_header = token_header or "Authorization"
        self.transport = transport or _default_transport
        self.schema = schema or SCHEMA
        self.detail_url_tpl = detail_url_tpl or ""
        self.timeout = timeout
        self.unread_path = unread_path if unread_path is not None else UNREAD_PATH
        self.calls = []                          # 自测用：记录请求过的 URL

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
        return _unwrap(raw, self.schema)

    def _circle(self):
        if not self.circle_id:
            raise ForumError("请先在 config.json 配置 forum_circle_id")
        return self.circle_id

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
        self.page_size = max(1, min(50, int(cfg.get("forum_page_size") or 10)))
        self._last = []
        self._last_sync = None

    def fetch(self):
        # 可选省流量策略：new/num 探活，返回 0 且已有缓存时直接复用上一轮结果。
        # 依赖「time 上次刷新时间」的确切语义，确认后才把 forum_probe 打开。
        if self.probe and self._last and self._last_sync:
            since = self._last_sync.strftime("%Y-%m-%d %H:%M:%S")
            try:
                if self.client.new_count(since) <= 0:
                    return list(self._last)
            except ForumError:
                pass                       # 探活失败不影响正常拉取

        errors, posts = [], []
        for name, call in (("热帖榜", lambda: self.client.top_ten()),
                           ("最新帖子", lambda: self.client.latest(
                               page_size=self.page_size))):
            try:
                posts.extend(call())
            except ForumError as e:
                errors.append("%s：%s" % (name, e))
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

    ruoyi = {"code": 200, "msg": "ok", "data": {"records": [
        {"id": "1024", "title": "周三操场音乐会", "nickname": "图书馆钉子户",
         "tagName": "活动", "likeCount": 328, "createTime": "2026-11-10 12:00:00",
         "url": "https://forum.example.com/t/1024"},
        {"id": "1025", "title": "出一台 iPad", "nickname": "打工豚",
         "tagName": "闲置", "likeCount": "88", "createTime": "2026-11-10 12:05:00"},
    ], "total": 2}}

    print("1) 分页接口与字段映射")
    c = client(lambda u, h: ruoyi)
    posts = c.latest()
    check("若依风格 records 解析出 2 条", len(posts) == 2)
    check("7 字段齐全", set(posts[0]) ==
          {"id", "title", "author", "tag", "heat", "time", "url"})
    check("作者/标签/热度映射", posts[0]["author"] == "图书馆钉子户"
          and posts[0]["tag"] == "活动" and posts[0]["heat"] == 328)
    check("热度数字字符串降级", posts[1]["heat"] == 88)
    check("拼接参数正确", "circleId=CIRCLE_1" in c.calls[0]
          and "pageNum=1" in c.calls[0] and "type=dynamic" in c.calls[0])

    print("2) 多种外层包裹兼容")
    general = {"code": 0, "data": {"list": [
        {"dynamicId": "A1", "dynamicTitle": "热帖一", "userName": "甲"},
        {"dynamicId": "A2", "dynamicTitle": "热帖二", "userName": "乙"}]}}
    c2 = client(lambda u, h: general)
    hot = c2.top_ten()
    check("通用 data.list + 动态字段名", len(hot) == 2 and hot[0]["id"] == "A1")
    check("无热度字段时按榜单顺序补分且递减",
          hot[0]["heat"] == 1000 and hot[1]["heat"] == 990)
    c3 = client(lambda u, h: [{"id": "z", "title": "裸数组"}])
    check("裸数组兼容", len(c3.top_ten()) == 1)

    print("3) 失败码 / 脏数据 / 链接白名单")
    try:
        client(lambda u, h: {"code": 500, "msg": "服务异常"}).top_ten()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("失败码带出服务端消息", "服务异常" in str(e))
    dirty = [{"id": "d1", "title": "脏数据", "heat": "abc",
              "url": "javascript:alert(1)", "nickname": None}]
    p = client(lambda u, h: dirty).latest()[0]
    check("脏热度降级为 0", p["heat"] == 0)
    check("作者缺失回落", p["author"] == "豚友")
    check("javascript 链接被挡", p["url"] is None)
    tpl = client(lambda u, h: dirty, detail_url_tpl="https://forum.example.com/d/{id}")
    check("H5 模板拼出的链接放行", tpl.latest()[0]["url"] ==
          "https://forum.example.com/d/d1")

    print("4) 新帖数 / 详情 / 站内信")
    c4 = client(lambda u, h: {"code": 0, "data": {"num": 3}})
    n = c4.new_count("2026-11-10 12:00:00")
    check("对象形态返回 3", n == 3)
    check("time 参数格式", "time=2026-11-10+12%3A00%3A00" in c4.calls[0])
    check("纯数字形态", client(lambda u, h: {"code": 0, "data": 7})
          .new_count("2026-11-10 12:00:00") == 7)
    d = client(lambda u, h: {"code": 0, "data": {"id": "1024", "title": "详情"}})
    check("详情返回原始对象", d.detail("1024")["title"] == "详情")
    check("详情 id 参数", "id=1024" in d.calls[0])
    try:
        client(lambda u, h: {"code": 0, "data": 0}).unread()
        raise AssertionError("应抛 ForumError")
    except ForumError as e:
        check("站内信路径未确认时明确报错", "待技术确认" in str(e))

    print("5) 聚合与默认不启用")
    calls = []

    def mixed(u, h):
        calls.append(u)
        if "ten/page" in u:
            return {"code": 0, "data": {"records": [
                {"id": "A1", "title": "热帖一", "likeCount": 50}]}}
        return {"code": 0, "data": {"records": [
            {"id": "A1", "title": "热帖一（重复）", "likeCount": 50},
            {"id": "B2", "title": "刚发的新帖", "likeCount": 5}]}}

    a = ForumAdapter({"forum_page_size": 10}, client=client(mixed))
    out = a.fetch()
    check("热帖 + 最新合并去重", len(out) == 2, str([p["id"] for p in out]))
    check("重复 id 保留热帖版本", out[0]["title"] == "热帖一")
    check("未开启探活时不请求 new/num", not any("new/num" in u for u in calls))

    class Fallback:
        def fetch(self):
            return ["MOCK"]

    cfg_empty = dict(DEFAULT_LIKE_CONFIG)
    check("forum_base 为空时返回旧数据源",
          isinstance(make_source(cfg_empty, Fallback()), Fallback))
    cfg_on = dict(DEFAULT_LIKE_CONFIG, forum_base="https://forum.example.com")
    check("填了 forum_base 才启用适配层",
          isinstance(make_source(cfg_on, Fallback()), ForumAdapter))
    check("默认不开启探活", ForumAdapter(cfg_on, client=client(mixed)).probe is False)

    print("6) 令牌与降级")
    seen_headers = {}

    def with_token(u, h):
        seen_headers.update(h)
        return {"code": 0, "data": 0}

    old = os.environ.pop(TOKEN_ENV, None)
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
        if old is not None:
            os.environ[TOKEN_ENV] = old

    fail_client = client(lambda u, h: (_ for _ in ()).throw(ForumError("连不上")))
    a2 = ForumAdapter({}, client=fail_client, fallback=Fallback())
    a2._last = [{"id": "old", "title": "缓存"}]
    check("接口全挂时沿用上一轮结果", a2.fetch()[0]["id"] == "old")

    print("\nSELFTEST_OK %d 项通过" % ok)


# 只在自测里模拟 config.json 的默认值，避免模块导入时依赖主程序
DEFAULT_LIKE_CONFIG = {
    "forum_base": "", "forum_circle_id": "", "forum_probe": False,
    "forum_page_size": 10,
}

if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)

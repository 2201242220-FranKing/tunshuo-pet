# HANDOFF.md · 给接手开发的 AI Agent（维护者模式）

> **这份文件和 `AGENTS.md` 不一样，别搞混**：
> `AGENTS.md` 面向**使用者 agent**，目标是「在这台电脑装好并启动桌宠」；
> 本文件面向**维护者 agent**，目标是「继续开发、改代码、跑回归」。
> 搭环境时按 `AGENTS.md`，动代码时按本文件。
>
> 本文件是项目约定，不是某次聊天记录：换电脑、换会话、换模型都以它为准。
> 所有约束只在仓库里这一处维护，不要在聊天里临时另编一套。

---

## 一、项目主人只需说这一句（可直接转发给 Codex 等 agent）

```
请读取仓库 https://github.com/2201242220-FranKing/tunshuo-pet 里的 HANDOFF.md，
进入维护者模式继续开发：先读材料、复述现状，等我确认后再动代码。用中文回复。
```

仓库已 clone 到本地时换成：

```
请读取本仓库的 HANDOFF.md 进入维护者模式，先复述现状再等我确认，不要直接改代码。
```

后续每次续聊一句即可：「继续豚说小豚项目，先 `git status` 确认工作区干净，需要同步就 `git pull --ff-only`，再按 HANDOFF.md 继续。」

---

## 二、开工顺序（严格按顺序，先读后做）

### 0. 确认代码是最新的

```bash
git status --short
git log --oneline -5
python3 check_update.py
```

`UPDATE_AVAILABLE` 时按 `check_update.py` 的 `UPDATE_PROMPT` 原样转述，但**不要擅自 pull**：
只有工作区干净、且项目主人明确同意，才执行 `git pull --ff-only`。
本地有改动（`dirty=true`）先告知，不许 pull / `reset --hard` / `checkout --` 覆盖。

### 1. 先读材料，一行代码都别改

- `HANDOFF.md`（本文件）、`AGENTS.md`（安装与排障规则、边界）
- `README.md`：环境要求、接口约定、配置字段、已知限制、版本记录、目录结构
- `VERSION`、`requirements.txt`、`config.json`、`论坛接口待确认清单.txt`
- `git log --oneline -10`：看最近几次提交改了什么、为什么改

### 2. 复述现状，等确认

给项目主人 3~5 行：当前版本、模块分工、本次目标、你打算动哪些文件、预计影响面。
**得到确认后才动手**。重大改动先给方案，不要一次性大重构。

### 3. 搭一次可运行环境

```bash
python3 bootstrap.py --check       # 只读体检：依赖 + 证书链 + HTTPS 探活
python3 bootstrap.py --setup       # 只装依赖、生成启动图标，不启动进程
```

`CERT_MISSING` / `ENV_CERT_MISSING` 时按 `AGENTS.md` 跑 `python3 bootstrap.py --fix-certs`，不要问用户。
Windows 用 `py -3`；建过 `.venv` 后手动跑脚本优先用 `.venv/bin/python`
（Windows 是 `.venv\Scripts\python.exe`），否则系统 Python 可能没装 PySide6。

---

## 三、项目现状快照（2026-11-12，一律以仓库实际为准）

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/2201242220-FranKing/tunshuo-pet`（**对外发 HTTPS**；维护者本机远端是 SSH `git@github.com:...`） |
| 版本 / 分支 | `VERSION` = `4.2.4`；`main`，快照提交 `8a4d606` |
| 平台 | macOS / Windows 10·11 正式支持，Linux 桌面实验性；**三平台共用一份主程序** |
| 依赖 | `PySide6-Essentials==6.9.2`、`Pillow>=10.0`，其余全标准库；无云服务、无账号体系 |
| 主程序 | `tunshuo_pet_pro.py`（绘制 / 动作 / 交互 / 数据源 / 托盘） |
| 数据层 | `forum_api.py` 聚合论坛 REST → **固定 7 字段列表** |
| 配置 | `config.json` 已登记 4 所学校圈子（浙外 / 浙工大 / 浙科 / 长征），`auto_poll=false`，令牌零落盘 |
| 更新提醒 | `VERSION` 是唯一版本戳；`check_update.py` 只读 `git fetch / rev-list / show`，绝不自动 pull |

**模块速查**（完整说明见 README「目录结构」）：

| 文件 | 职责 |
|---|---|
| `tunshuo_pet_pro.py` | 主窗口、HotPanel 榜单、播报、托盘、更新提醒 |
| `forum_api.py` | 论坛适配层、字段映射、代理失败直连重试 |
| `action_engine.py` / `skin_rig.py` / `actions.json` | 动作关键帧、关节皮肤 |
| `studio_sync.py` | 形象工作台只读同步与缓存 |
| `bootstrap.py` / `make_shortcut.py` / `make_app.py` | 安装、启动图标、macOS `.app` |
| `diagnose.py` / `enable_forum.py` / `check_update.py` | 诊断、圈子配置、更新检查 |
| `selftest_panel.py` / `forum_api.py --selftest` / `diagnose.py --selftest` | 三层离线自测 |

**不可动摇的两个口径**：

1. **7 字段数据契约**：`id / title / author / tag / heat / time / url`。`forum_api.ForumAdapter.fetch()`
   聚合最新帖与降级十大热帖，上层 `_on_posts()` 的 seen 去重、双击打开链接都依赖它，不要改契约。
2. **播报取「发布时间最新的一条」**：榜单「最新」模式、来新帖时的「新帖播报」、单击桌宠的
   「单击播报」三处共用 `post_time_key()`，**不是热度最高**。文案分别是「豚说 · 最新动态」、
   「最新的一条是」。相对时间（「刚刚」「5分钟前」）解析不了时沉底并保持拉取顺序。

---

## 四、开发红线（绝对不要做）

- 不改 7 字段契约、不改上面第 2 条播报口径、不改业务文案口径；纯 UI 改动不发新请求、不触发刷新。
- 不改 `config.json` 的默认值；**不写入任何 token / 密钥 / 账号密码到任何会入库的文件**。
  令牌只从环境变量临时读取。论坛 `page` / `detail` 当前匿名可读、**零令牌即可跑**，
  不要自作主张加登录流程；`ten/page` / `new/num` 需登录（`code=110`），已自动降级。
- 不引入 `requirements.txt` 之外的依赖，不换 pip 源，不装 PyInstaller 等新工具；
  **不用 `verify=False` 关证书校验、不加 `certifi`**。证书问题一律走 `--fix-certs`。
- 不删除仓库文件；不 `git pull` 覆盖本地改动、不 `reset --hard`、不 `checkout --`、不强推。
- 不调用除 **PyPI、仓库自身 git 远端**、`config.json` 里已配置的论坛地址
  `https://alumni.qiyuanheshan.com`、本地工作台 `127.0.0.1:8770` 之外的服务；
  不做论坛写操作（发帖 / 回复 / 点赞）。
- 不打包 `.exe`，不把别人做好的 `.app` / `.exe` 拷来用：启动器绑定本机 Python 路径与源码目录，
  换机器必须由 `bootstrap.py` → `make_shortcut.py` 在本机重新生成。
- 本地 commit 用中文简述；**push 前必须先问项目主人**，不要擅自推送。

---

## 五、每次改完必须跑（不许跳过、不许降低标准）

```bash
python3 forum_api.py --selftest      # 接口层 73 项，离线
python3 selftest_panel.py            # 面板 / 播报 45 项，离屏不弹窗
python3 diagnose.py --selftest       # 错误分类与证书链 16 项，离线
python3 -m py_compile *.py
QT_QPA_PLATFORM=offscreen python3 -c "import tunshuo_pet_pro"   # 离屏导入冒烟，不弹窗
```

以上全过再向项目主人汇报：改了哪些文件、为什么、有没有影响榜单 / 播报 / 更新提醒 / 三平台差异分支。
改过源码或 `VERSION` 后，**必须重启桌宠**才加载新代码。
拉取失败时跑 `python3 diagnose.py`（只读联网），按输出的分类处理；气泡只有 96px 会截断英文异常，
完整原因在 `logs/pet.log`（`.app` 启动看 `~/Library/Logs/tunshuo-pet.log`），别截图气泡。

---

## 六、发版流程（只有项目主人明确说「发版」才做）

1. 改仓库根 `VERSION`。
2. 在 `README.md`「版本记录」补一行改了什么。
3. `git push origin main`。

`check_update.py` 只读比对版本，桌宠每次启动约 7 秒后自检、只在有新版时冒一次气泡；
统一话术唯一定义在 `check_update.py` 的 `UPDATE_PROMPT`，要改文案只改这一处，别在别处复制一份。

---

## 七、待办清单（背景信息，不要自行开工）

| 事项 | 状态 | 阻塞点 / 说明 |
|---|---|---|
| 双击榜单条目看正文（范围 B） | **未做** | 当初明确划在范围 A 之外，先问项目主人是否开启。接口不返回 `url`；可考虑用已有的匿名 `/app/dynamic/detail` 做面板内详情，但要先确认方案 |
| 登录功能 | **不做** | `page` / `detail` 匿名可读，技术未提供登录接口规范；保持零令牌，不要主动加 |
| 论坛技术待确认 | 等待外部回复 | 完整 `circleId` 对照表、长征圈子返回 0 条、十大热帖/新帖数需登录、原帖 H5 URL 规则、`new/num` 的 `time` 语义与 `tagId` 枚举、站内信未读路径、限频 → 直接转发 `论坛接口待确认清单.txt`（已标注哪些实测通过、不用重复问） |
| 站内信角标 UI | 未做 | 正确接口路径还没确认；`ForumClient.unread()` 已保留但默认抛明确错误 |
| Windows 真机验证 | **未验证** | 目前只有离线桩 / 本机模拟，无 Windows 真机结论、无 `.exe` |
| Linux 托盘 | 实验性 | 无托盘的轻量 WM 下图标可能不显示 |

改动前先确认这些项的优先级，不要一次开多条线。

---

## 八、多机 / 多人并行

- **同一时间只让一台机器改代码并 push**；其他机器开工前先按第 0 节确认并同步。
- 不要自行合并、不要强推、不要覆盖别人的提交；发现分叉或冲突**先停下来问项目主人**。
- 别把本机 `.venv/`、`logs/`、`state.json`、`studio_cache.json` 或生成的 `.app` 提交进仓库
  （都已在 `.gitignore`）。写权限由每台电脑自己配 SSH key 解决，**不要把 token 贴进聊天或文件**。

---

## 九、常见误区

- 「读完 `AGENTS.md` 装好并启动」≠「交接完成」：那是使用者模式，维护者要看本文件。
- clone 用 **HTTPS**；`git@github.com:...` 是维护者本机的 SSH 地址，别人没配 key 会失败。
- 「拉取失败」不等于 VPN 问题：先跑 `diagnose.py` 看分类。证书类走 `--fix-certs`（与 VPN 无关），
  代理类先确认桌宠是否真的仍拉不到（已内置代理失败自动直连重试）。
- 更新检查返回 `UNKNOWN` / `NO_GIT` 是设计内静默降级，不是错误。
- `config.json` 只在文件不存在时自动生成，之后启动只读不写；改配置用 `enable_forum.py --apply`。

# 豚说小豚 · 桌面宠物

豚说校园论坛的桌面宠物：一只蓝色小鲸鱼常驻桌面右下角，会播报最新帖、随机做待机动作，也能被拖拽、投喂。**macOS / Windows 10·11 共用同一份源码**，Linux 桌面为实验性支持。当前版本先在本地跑通体验，后续再迁移到小程序端。

仓库：https://github.com/2201242220-FranKing/tunshuo-pet
当前版本：见仓库根 `VERSION`（v4.2.3）

## 分享给别人：一句话就够

把下面这句发给对方（或直接发给对方的 AI agent），它会自动识别系统、补齐依赖、启动桌宠，全程不需要用户再补充任何信息：

```
请读取仓库 https://github.com/2201242220-FranKing/tunshuo-pet 并按其中的 AGENTS.md
自动安装并运行小豚桌宠，缺什么依赖你自己补齐，不用问我。
```

完整规则（系统识别、依赖自愈、自检、更新提醒、红线）见 **[AGENTS.md](AGENTS.md)**。
分享时发 **HTTPS** 地址（`git@github.com:...` 是维护者用的 SSH 地址），并确认仓库已公开或已给对方权限。

## 特性

- **单窗口绘制**：角色、气泡都在同一个透明窗口里用 `QPainter` 画，不新建顶层窗口，不会抢走你正在操作的界面焦点。
- **动作数据驱动**：`actions.json` 里 14 个出厂动作都是关键帧数组 `[t, dx, dy, 旋转°, 横缩放, 纵缩放, 翻转]`，`action_engine.py` 用 cosine 缓动插值；不再有硬编码动作函数。工作台可增删动作、编辑关键帧，发布后覆盖本地默认值；断网时回落到 `actions.json`。
- **关节皮肤（分层部件）**：默认整图模式行为完全不变；工作台启用 `rig` 皮肤后，角色按 manifest 拆成 身体/头/左右手/尾鳍/嘴 逐层绘制，每层有自己的枢轴与父子变换。关键帧第 8 位可选的部件字典能单独驱动头、手、嘴，做出转头、招手、张嘴；老数据没有第 8 位就等同原来的整体变换。`skin_rig.py` 负责 manifest 校验、父子链、z 序与包围盒，窗口遮罩按所有部件旋转后的范围计算，挥手不会被裁掉。
- **事件状态机**：来新帖 → 抬手播报（`announce`）、被拖动 → 手脚挣扎（`struggle`）、点击摸头 → 歪头（`nuzzle`）、待机 → 呼吸（`breathe`）；找不到对应触发动作时自动回落到原有逻辑。
- **待机随机动作**：每隔 4.5~11 秒随机播一个动作，另有随机眨眼、呼吸浮动。
- **拖动倾斜**：按最近 100ms 的平均速度计算倾斜角，慢拖也有明显反应，甩到 1200px/s 吃满 30°；松手有边缘吸附和回弹余震。
- **热帖播报**：可同时监控多个学校圈子（按 `circleId` 逐个拉取后合并出榜，条目带学校简称）；当前已接浙外 / 浙工大 / 浙科 / 长征 4 所学校的真实数据。也可回退到内置演示数据。榜单支持「最新 / 最热」切换，来新帖时播报发布时间最新的那一条。首次刷新只建立基线、不误报新帖；自动轮询默认关闭，手动「立即刷新」才拉。
- **状态**：连点 5 次跳舞、右键喂小鱼干、180 秒无操作自动睡觉（zzz），点击唤醒。
- **按需调帧**：动作/拖动 16.7fps、静止 6.7fps、睡觉 3.3fps；呼吸、倾斜、动作都按真实时间计算，降帧不会让动画变慢，长时间常驻更省电。
- **形象工作台**：配套网站 `tunshuo-pet-studio/` 可以可视化改外观、动作、台词、配饰，上传并切换整套皮肤包；发布后桌宠自动同步，皮肤素材下载到 `assets/skins/`。配饰画在角色的同一个变换里，跳起/倾斜时不会飘掉；`attach` 字段还能把帽子挂到头部、围巾挂到身体。断网时沿用上一次的形象。

## 环境要求与依赖

### 电脑配置

| 项 | macOS | Windows 10 / 11 | Linux 桌面（实验性） |
|---|---|---|---|
| 系统版本 | macOS 11 Big Sur 及以上（Intel / Apple Silicon 均可） | Windows 10 1809 及以上、Windows 11 | 带桌面环境与系统托盘的 X11 / Wayland |
| Python | **3.9 ~ 3.13，64 位** | 同左（安装时勾选 *Add Python to PATH*） | 同左（Debian/Ubuntu 另需 `python3-venv`） |
| 内存 | ≥ 4 GB（桌宠常驻约 120~200 MB） | 同左 | 同左 |
| 磁盘 | 首次约 **300 MB**（PySide6 轮子 133 MB + Pillow + venv） | 同左 | 同左 |
| 图形 | 支持透明窗口与系统托盘 | 同左（DWM 窗口合成默认开启，勿关闭） | 无托盘的轻量 WM 下托盘图标可能不显示 |
| 网络 | 首次安装需访问 **PyPI**；运行时需访问 `https://alumni.qiyuanheshan.com`（匿名只读） | 同左 | 同左 |
| Git | 可选，仅用于「检查更新」；ZIP 下载也能跑，只是没有自动更新提醒 | 同左 | 同左 |
| 权限 | 只需能写**仓库目录**（`.venv/`、`logs/`、`state.json`），**不需要管理员 / sudo** | 同左 | 同左 |

**不支持**：32 位 Python、Python 3.8 及以下 / 3.14 及以上、Windows 7/8、无图形界面的服务器、手机端。
首次 `pip install` 会下载约 133 MB 的 PySide6 轮子，网速慢时可能要十几分钟，属正常现象。

### 依赖包（`requirements.txt`）

| 包 | 版本 | 用途 | 运行必需 |
|---|---|---|---|
| `PySide6-Essentials` | `==6.9.2` | Qt 窗口 / 绘制 / 托盘 / 系统通知 | **必需** |
| `Pillow` | `>=10.0` | 仅重新生成 `assets/pet*.png` 时用到 | 否（随 requirements 一起装） |
| `shiboken6` | 由 PySide6 自动带入 | PySide6 的 Python 绑定层 | 自动 |

其余全部是标准库（`json` / `urllib` / `datetime` / `subprocess` / `plistlib` / `ctypes`）。
**没有引入任何第三方框架、云服务、账号体系或令牌**：论坛 `page` / `detail` 匿名可读，`ten/page` / `new/num` 需登录的接口已自动降级，用户不需要提供任何凭据，也没有登录入口。

### 平台差异（一处源码，四处分支）

| 差异点 | macOS | Windows / Linux |
|---|---|---|
| 系统通知 | `osascript display notification` | Qt 托盘 `showMessage()`（气泡 / Toast） |
| 窗口属性 | 额外设 `WA_MacAlwaysShowToolWindow` | 跳过（该属性仅 macOS 有效） |
| 界面字体 | PingFang SC | Microsoft YaHei UI / Noto Sans CJK SC |
| 打包 / 启动 | `make_shortcut.py` 自动生成 `.app` + 桌面图标、`start_macos.command` | 桌面快捷方式 / `.desktop`、`start_windows.bat`、通用 `bootstrap.py` |
| 日志 | `.app` 启动器写 `~/Library/Logs/tunshuo-pet.log`；bootstrap 写 `logs/pet.log` | `logs/pet.log` |

> PySide6 6.9.2 在 macOS 12.6.1 / Intel 上验证过；Windows / Linux 用的是同一 Qt 版本，透明窗口遮罩行为基本一致，极高 DPI 与多屏缩放可能有细微差异。

## 快速开始

### 最省事：交给 `bootstrap.py`（三个平台通用，推荐）

```bash
git clone https://github.com/2201242220-FranKing/tunshuo-pet.git
cd tunshuo-pet
python3 bootstrap.py              # Windows PowerShell / CMD 用：py -3 bootstrap.py
```

它自动建 `.venv`、补齐缺失依赖、**生成桌面 / 应用里的启动图标**、后台启动桌宠，命令立即返回，
日志在 `logs/pet.log`。只装环境不启动用 `python3 bootstrap.py --setup`（图标同样会生成）；
只读体检用 `python3 bootstrap.py --check`（不写盘）。

图标由 `make_shortcut.py` 生成，**只用标准库和系统自带能力**，在本机创建、绑定本机 Python 与源码目录：
macOS 得 `~/Applications/豚说小豚.app` + 桌面同名符号链接；Windows 得桌面「豚说小豚.lnk」
（指向 `pythonw.exe` + `bootstrap.py`）；Linux 得桌面 / 应用菜单两个 `.desktop`。
幂等：已存在就跳过，不覆盖、不删除；生成失败只打印提示，不影响桌宠运行。
手动重跑 `python3 make_shortcut.py`，`--check` 可只读预览将要创建什么。

### 手动分步（想自己控制进程时）

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 tunshuo_pet_pro.py
```

Windows（PowerShell）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tunshuo_pet_pro.py
```

> 若 PowerShell 提示「禁止运行脚本」，直接改用 `.\.venv\Scripts\python.exe tunshuo_pet_pro.py` 即可。

### 双击运行（免终端）

安装时已自动在桌面 / 应用里生成启动图标，之后直接双击即可，不用再开终端。

| 平台 | 自动生成的图标 | 备用启动方式 |
|---|---|---|
| macOS | `~/Applications/豚说小豚.app` + 桌面同名图标 | 双击 `start_macos.command` |
| Windows | 桌面「豚说小豚.lnk」 | 双击 `start_windows.bat` |
| Linux | 桌面 / 应用菜单「豚说小豚.desktop」 | `python3 bootstrap.py` |

启动后系统托盘出现小豚图标（macOS 在菜单栏、Windows 在任务栏通知区，小豚不占 Dock / 任务栏按钮）。
**改过源码或 `VERSION` 后必须重启桌宠**才加载新代码。

## 手动重建 macOS .app（免终端，仅 macOS）

> **正常安装不用看这一节**：`bootstrap.py` 已自动调用 `make_shortcut.py` 完成 `.app` 与桌面图标。
> 下面命令只在换了 Python 解释器、改了图标、或图标被误删时需要手动重跑。
> Windows 用户不用看这一节：双击 `start_windows.bat` 即可，它会走 `bootstrap.py` 自动装依赖并后台启动。

```bash
python3 make_app.py
```

会生成并安装到 `~/Applications/豚说小豚.app`，之后双击即可启动，不依赖终端。可用环境变量调整：

| 变量 | 作用 | 生效时机 |
|---|---|---|
| `TUNSHUO_INSTALL_DIR` | 自定义 `.app` 安装位置 | 打包时 |
| `TUNSHUO_PET_DIR` | 覆盖启动器里的源码目录 | 运行时 |
| `PET_PYTHON` | 指定 Python 解释器 | 运行时 |

启动器优先使用打包时记录的解释器；换机器或 Python 升级导致该路径失效时，会依次探测项目 `.venv`、`PET_PYTHON`、PATH 里的 `python3`。**换机器请重新跑一次 `make_app.py`**，因为 `.app` 里的启动器与源码目录绑定。

## 配置

`config.json`：

| 字段 | 默认 | 说明 |
|---|---|---|
| `api_url` | `""` | 留空用内置演示数据；填了就走真实接口 |
| `notify_system` | `true` | 有新帖时是否发系统通知（macOS 通知中心 / Windows 托盘气泡）。**工作台发布过形象后由工作台的「新帖系统通知」接管** |
| `pet_width` | `60` | 角色逻辑宽度（px）；素材 240px 通过 DPR=4 显示 |
| `idle_sleep_seconds` | `180` | 无操作多久自动睡着，`0` 表示永不。**工作台发布过形象后由工作台的「自动睡觉」接管** |
| `auto_poll` | `false` | 是否定时拉新帖。**仅在 `api_url` 或 `forum_base` 配好时生效**；演示数据模式下不会启动，避免假数据反复弹提醒 |
| `poll_interval_minutes` | `3` | 轮询间隔（分钟，最小 1）。已有请求未结束时会自动跳过这一轮 |
| `studio_url` | `http://127.0.0.1:8770` | 形象工作台地址；**留空 = 完全不联网同步**，只用本地缓存 |
| `studio_sync_seconds` | `20` | 拉取形象配置的间隔（秒，最小 5）。与热帖轮询互相独立 |

`config.json` 只在文件不存在时自动生成，之后启动只读不写，手改不会被覆盖。

形象的运行时缓存单独放在 `studio_cache.json`，下载的配饰放在 `assets/accessories/`（都已加入 `.gitignore`）。工作台没开或断网时静默沿用缓存，不弹错。形象同步只做只读 GET，本地程序里不需要任何密钥；上线后把 `studio_url` 改成公网域名即可。

运行时状态单独放在 `state.json`（首次启动自动生成，已加入 `.gitignore`）：目前只存 `fish`（已投喂的小鱼干数量）。旧版本把 `fish` 写在 `config.json` 里，程序会在首次启动时自动迁移，计数不会丢；因此喂鱼不会再让 git 显示仓库有改动。

### 接口约定

`api_url` 返回 JSON 数组，或 `{"posts": [...]}`：

```json
{
  "posts": [
    {
      "id": "post-1024",
      "title": "周三晚操场音乐会，有人组队吗",
      "author": "图书馆钉子户",
      "tag": "活动",
      "heat": 328,
      "time": "5分钟前",
      "url": "https://example.com/t/1024"
    }
  ]
}
```

`id` 缺省时用 `title` 去重；`heat` 允许数字或数字字符串，脏数据会降级为 0；`url` 只放行 `http://` / `https://`；一次最多取 100 条。

### 论坛 REST 接口适配层（已按真实响应校准；当前启用 4 所学校圈子）

线上地址 `https://alumni.qiyuanheshan.com`。技术提供的接口：`/app/dynamic/page` 最新帖子、`/app/dynamic/new/num` 新帖提醒数、`/app/dynamic/ten/page` 十大热帖、`/app/dynamic/detail` 帖子详情。**上面的 `api_url` 是旧的单接口约定，继续有效**；新接口走 `forum_api.py`，聚合成同样的 7 字段列表，因此 `_on_posts()` 的 seen 去重、双击打开链接零改动。榜单排序与播报口径见下方「榜单最新 / 最热切换」小节。

真实外层结构（已实测）：

```json
{"code": 200, "data": [ {"id": "...", "content": "...", "userName": "...",
                         "tagList": [{"name": "宣传推广"}], "createTime": "...",
                         "totalHeatNum": 96} ],
 "encrypt": false, "message": "请求成功", "recordsTotal": 7614}
```

`data` **直接是帖子数组**（不是 `records`/`list` 包裹），`recordsTotal` 在顶层；`code=400` 参数错误，`code=110 / message=请先登录` 缺登录态。

| 桌宠字段 | 取自 | 说明 |
|---|---|---|
| `id` | `id` | 19 位字符串；`dynamicNo` 短编号只作兜底 |
| `title` | `content` | 真实帖子没有标题字段，取正文首 24 字做摘要（去链接、并空白、`#话题#` 转方括号）。上限由 `forum_api.SCHEMA["title_max"]` 控制，也可用 `forum_schema` 覆盖；定在 24 字是因为 38 字会让热帖榜每条高达 110px 以上 |
| `author` | `userName` | |
| `tag` | `tagList[0].name` | 兜底 `circleTitle` 圈子名 |
| `heat` | `totalHeatNum` | 兜底 `heatNum` / `zanNum` / `commentsNum` / `browseNum` |
| `time` | `createTime` | |
| `url` | 接口未返回 | 等技术给 H5 规则后填 `forum_detail_url`；在此之前双击条目不会跳转 |

**实测鉴权差异（重要）**：`page` 与 `detail` 匿名即可读；`ten/page` 与 `new/num` 返回 `code=110 请先登录`。因此默认不依赖这两个接口：十大热帖拿不到时自动改用最新帖按 `totalHeatNum` 出榜（上层本来就按 heat 排序），并把取样从 10 扩到 20，本次会话不再反复请求需登录的接口。**零令牌也能跑**；若技术提供匿名榜单或用环境变量临时给 token，榜单会自动切回真实十大。

| config.json 字段 | 默认 | 说明 |
|---|---|---|
| `forum_base` | `""` | **唯一启用开关**。留空 → `make_source()` 原样返回旧 `DataSource`，继续用演示数据，零回归；启用填 `https://alumni.qiyuanheshan.com` |
| `forum_circle_id` | `""` | 单个学校圈子 circleId（旧写法，继续兼容）。**不传时接口不按学校筛选**，所以未配置会明确报错 |
| `forum_circles` | `[]` | **多学校列表**：`[{"id":"圈子ID","name":"学校简称"}, ...]`，最多 20 个。非空时优先于 `forum_circle_id` |
| `forum_tag_circle` | `true` | 多学校时在条目标签前加学校简称（如「浙外·宣传推广」），单学校不加 |
| `forum_allow_all` | `false` | 设为 `true` 才允许不传 circleId 拉全站 |
| `forum_token_header` | `Authorization` | 令牌字段名；**令牌值只从环境变量 `TUNSHUO_FORUM_TOKEN` 读，绝不写进会入库的 config.json** |
| `forum_detail_url` | `""` | 原帖 H5 链接模板，用 `{id}` 占位；拼出的链接仍只放行 http(s) |
| `forum_probe` | `false` | `new/num` 探活；需登录且 `time` 语义未定，保持关闭 |
| `forum_page_size` | `10` | 每次拉最新帖子的条数（1~50） |
| `forum_top_fallback_size` | `20` | 十大热帖不可用时扩大到的取样条数 |
| `forum_schema` | `null` | 可选：覆盖 `forum_api.SCHEMA` 的字段映射，技术改字段时只改这里 |
| `forum_timeout` | `15` | 单次请求超时秒数（3~30）。部分空圈子实测响应 5~6 秒，10 秒容易误判超时，故默认 15 |

这些默认值只在 `DEFAULT_CONFIG` 里，**不会写回现有 config.json**（程序只在文件不存在时才创建它）。

**自检命令**（都不写任何配置）：

```bash
python3 forum_api.py --selftest                          # 73 项离线自测，不发网络请求
python3 selftest_panel.py                                # 45 项离屏 UI 自测，检查榜单切换与播报口径
python3 diagnose.py --selftest                           # 错误分类自测，不联网
python3 diagnose.py                                      # 拉取失败时的一键网络诊断（只读、联网）
python3 forum_api.py --live --circle-id <学校圈子ID>     # 真实只读联调，作者自动打码
python3 forum_api.py --live --all                        # 不带圈子 ID，拉全站（仅验证用）
```

**多学校监控**：`forum_circles` 里每加一个学校，桌宠下次刷新就会多拉一个圈子，合并去重成一张榜单（默认按热度排，面板可切「最新」按发布时间排）；条目标签会带学校简称。某个学校接口失败只影响它自己，其他学校照常出榜；全部失败时沿用上一轮结果，不会清空榜单。帖子若带 `circleId` 但与请求的圈子不符会被丢弃，防止 ID 填错或服务端回落全站时串进别校数据。上限 20 个学校，`seen` 去重上限已从 200 提到 1000，避免多学校时旧帖被误判成新帖。旧的 `forum_circle_id` 单值写法继续有效。

**启用 / 增删学校（用 `enable_forum.py`，默认只预览不写盘）**：

```bash
python3 enable_forum.py --list                                # 看当前监控了哪些学校
python3 enable_forum.py --check                               # 逐校只读体检：ID 是否有效、有无帖子
python3 enable_forum.py --add <圈子ID> --name <简称>           # 预览 + 只读联调
python3 enable_forum.py --add <圈子ID> --name <简称> --apply   # 正式加入（重复 ID 只更新名称）
python3 enable_forum.py --remove <圈子ID> --apply             # 移除一个学校；移空则回退演示数据
python3 enable_forum.py --off --apply                        # 一键清空回退
python3 enable_forum.py --circle-id <圈子ID> --apply         # 旧写法：只监控一个学校
```

脚本只改 `forum_base` / `forum_circles` / `forum_circle_id` / `forum_allow_all` 四个键，其余配置原样保留，**令牌永远不写盘**；也不会替你重启桌宠。写入后退出并重启 `.app` → 右键「立即刷新」，首次刷新只建立基线不误报新帖。若要定时播报，再单独把 `auto_poll` 设为 `true`（轮询条件已兼容 `api_url` 或 `forum_base` 任一配好）；当前按用户要求保持关闭。

**当前现场状态（2026-11-11）**：`config.json` 已登记 4 所学校，`forum_circles` 优先于旧的 `forum_circle_id`（仍保留浙外的值做兼容）。全部经过只读联调，服务端回读的 `circleTitle` 与学校名一致，防串校过滤生效：

| 简称 | circleId | recordsTotal | 联调结果 |
|---|---|---|---|
| 浙外 | `1844924022131912706` | 7637 | 正常，圈子名「浙外校友圈」 |
| 浙工大 | `1849752540716011521` | 7295 | 正常，圈子名「浙工大校友圈」 |
| 浙科 | `1846842931990769666` | 12152 | 正常，圈子名「浙科校友圈」 |
| 长征 | `1860950189561458688` | 0 | ⚠ 匿名读取返回 `code=200` 但 `data=[]`；可能圈子还没人发帖，也可能 ID 不对，需找技术核对 |

一次「立即刷新」实测：4 校合并 60 条（每校 20 条），标签形如「浙工大·日常求助」，去重通过、无失败学校；耗时约 6 秒（长征空圈子响应偏慢）。长征当前不贡献帖子，但留在列表里，之后有新帖会自动出现，不会影响其他三校出榜。自动轮询仍按约定关闭。

**仍需技术确认**：完整的学校 `circleId` 对照表、长征圈子为何为空（ID 是否正确）、十大热帖/新帖数需登录（返回 `code=110 请先登录`）、原帖 H5 链接规则、`new/num` 的 `time` 语义与 `tagId` 枚举、站内信未读的正确路径。可直接转发 `论坛接口待确认清单.txt`（已标注哪些项实测通过、不用重复给）。技术文档里「十大热帖」和「站内信 提醒未读消息」写成了同一个 `GET /app/dynamic/ten/page?circleId=`，疑似笔误；`ForumClient.unread()` 已保留但默认抛明确错误，路径确认后改 `UNREAD_PATH` 即可，站内信角标属于新 UI，尚未实现。

## 交互一览

| 操作 | 效果 |
|---|---|
| 悬停 | 随机张望 |
| 单击 | 抖一下，播报当前最新一条帖子或随机一句 |
| 双击 | 打开 / 关闭帖子榜（面板内可切「最新 / 最热」，双击条目打开原帖） |
| 连点 5 次 | 跳舞彩蛋 |
| 按住左右拖 | 移动 + 按速度倾斜 + 关节皮肤下手脚挣扎 + 松手边缘吸附与余震 |
| 来新帖 / 摸头 | 关节皮肤下抬手播报 / 歪头眯眼（整图模式仍是原来的蹦一下/抖动） |
| 右键 | 喂小鱼干、随机动作、睡/醒、热帖榜、立即刷新、检查更新、暂停提醒、打开形象工作台、重新同步形象、退出 |
| 系统托盘 | 隐藏/显示、喂鱼、动一下、回到右下角、热帖榜、立即刷新、检查更新、打开形象工作台、重新同步形象、退出 |

### 榜单「最新 / 最热」切换（2026-11-11）

双击打开榜单后，标题下方有一组「最新 / 最热」分段按钮，**默认最热**，与旧版表现完全一致。

| 模式 | 排序依据 | 条目第二行 |
|---|---|---|
| 最热 | `heat` 降序 | 标签 · 作者 · 热度 N |
| 最新 | `createTime` 降序 | 标签 · 作者 · 时间（如 `11-11 17:30`） |

- **纯 UI 层改动**：`forum_api.py`、7 字段契约、`config.json`、`enable_forum.py` 全部没动。切换只是把同一批 `posts` 换个排序键重绘，**不发新请求、不触发刷新**，也不写配置或令牌；显示的仍是上次「立即刷新」拉到的那批数据。
- 多学校是按圈子分组拼起来的，所以「最新」会真的按发布时间全局重排，不是沿用列表顺序。时间解析集中在 `post_time_key()`：能解析成绝对时间的规整成定长字符串比较；演示数据的「5分钟前」「刚刚」这类相对串解析不了，统一排到最后并保持拉取顺序，不会乱跳。
- 十大热帖接口恢复匿名可用后，老热帖会自然沉到「最新」榜底部；`top_ten()` 给无热度榜单补的假分不参与时间排序。
- **播报口径已统一为发布时间最新的一条**：来新帖时取新帖里时间最新的（原来是热度最高），气泡与系统通知显示时间；单击桌宠也由「现在最火的是」改为「最新的一条是」，同样显示时间与作者。榜单「最新」、新帖播报、单击播报三处现在共用同一个 `post_time_key()`。
- 两个模式都不显示对方模式的排序值，避免 336px 面板里第二行被挤断。接口仍不返回 `url`，双击条目依旧打不开原帖（待技术给 H5 规则，或改用已有的匿名 `detail` 接口做面板内详情）。

回归自测：`python3 forum_api.py --selftest`（67 项，接口层）与 `python3 selftest_panel.py`（45 项，离屏检查榜单切换与三处播报口径）都不联网、不写配置、不弹窗。

## 目录结构

```
tunshuo-pet/
├── AGENTS.md              给对方 AI agent 的自动安装说明书（分享时只需发仓库）
├── VERSION                版本戳；更新检查与 .app 版本号都读它
├── bootstrap.py           全平台一键安装：建 venv / 补齐依赖 / 生成图标 / 后台启动
├── make_shortcut.py       自动生成桌面 / 应用启动图标（三平台，幂等，bootstrap 自动调用）
├── check_update.py        只读更新检查（git fetch / rev-list / show，绝不自动 pull）
├── start_windows.bat      Windows 双击启动器
├── start_macos.command    macOS 双击启动器
├── tunshuo_pet_pro.py     主程序（绘制 / 动作 / 交互 / 数据源 / 托盘），三平台共用
├── studio_sync.py         形象工作台同步：拉取、归一化、缓存、配饰 QPixmap
├── actions.json           14 个出厂动作关键帧（桌宠离线默认，工作台发布可覆盖）
├── action_engine.py       动作解释器：数据校验 / 缓动插值 / 部件通道
├── skin_rig.py            皮肤 manifest 校验、父子变换链、z 序、包围盒
├── forum_api.py           论坛 REST 适配层（真实字段已校准，默认不启用，可离线/联网自检）
├── enable_forum.py        论坛接口启用/回退/增删学校/逐校体检（默认只预览，--apply 才写配置）
├── selftest_panel.py      榜单切换与播报口径的离屏自测（45 项，不联网不写盘）
├── diagnose.py            拉取失败一键诊断（只读、联网，输出 DIAGNOSIS_OK / FAIL）
├── 论坛接口待确认清单.txt   可直接转发技术的追问清单（含已实测通过的项）
├── make_app.py            macOS .app 打包脚本（仅 macOS）
├── config.json            用户配置（入库）
├── state.json             运行时状态（自动生成，不入库）
├── studio_cache.json      上次同步的官方形象（自动生成，不入库）
├── .venv/                 一键安装生成的虚拟环境（不入库）
├── logs/                  运行日志（不入库）
├── requirements.txt       依赖声明
├── LICENSE                MIT
└── assets/
    ├── pet.png            常态帧（240px）
    ├── pet_blink.png      眨眼帧
    ├── accessories/       工作台下发的配饰 PNG（自动下载，不入库）
    ├── skins/             工作台下发的皮肤包（自动下载；含一份离线占位包）
    ├── process_sprite.py  素材处理：去白底 + alpha bleed
    └── Keep_this_exact_*  两张原始源图，供重新生成帧使用
```

需要重新生成角色帧时：

```bash
pip install Pillow
python3 assets/process_sprite.py
```

> 素材处理里的 **alpha bleed** 不能省：RGBA 图片缩小显示时，透明区的黑色会被插值混进轮廓，形成一圈黑边。脚本先把角色颜色渗进透明区，主程序也不做运行期缩放，而是用 `devicePixelRatio` 交给系统合成。

## 已知限制

- macOS 与 Windows 10/11 为正式支持；Linux 为实验性，需要桌面环境提供系统托盘。`make_app.py` 只在 macOS 可用（在别的平台运行会明确报错并指向 `bootstrap.py`）。没有打包好的 `.exe`：`make_app.py` 生成的启动器绑定本机 Python 路径，换机器必须本机重跑；要真·单文件 exe 得另走 PyInstaller（约 200MB，本项目未引入）。
- 已启用 4 所学校真实数据（浙外 / 浙工大 / 浙科 / 长征），自动轮询按用户要求保持关闭（只有右键「立即刷新」才拉一次）。十大热帖与新帖数接口需登录，当前数据层自动降级为「最新帖按热度出榜」（这是取数降级，与榜单的「最新 / 最热」切换无关）；接口不返回 url，双击打开原帖待技术给 H5 链接规则。长征圈子目前返回 0 条，待技术核对 ID；其余学校仍待补完整对照表。可用 `--off --apply` 随时回退到演示数据。
- 形象同步依赖 `tunshuo-pet-studio/` 的服务；工作台没运行时桌宠用本地缓存继续跑，不会报错，但新发布的形象要等服务起来（或手动「重新同步形象」）才生效。不想联网就把 `studio_url` 留空。
- `assets/skins/placeholder/` 是**程序从现有 `pet.png` 切出来的技术验证包**，不是最终美术：小角度（头 ≤10°、手 ≤35°）没有破洞，角度再大会露出同色底补的月牙。正式皮肤请按 `tunshuo-pet-studio/JOINT_SPEC.md` 重画挖空底图与部件层，直接放进工作台替换即可，代码不用改。
- 无边框透明窗口必须关掉系统投影（`Qt.NoDropShadowWindowHint`），否则动作播放、遮罩变矩形时，macOS 会在角色背后投出一块灰黑方块。
- 若启动后没有反应：用 `bootstrap.py` 启动的看 `logs/pet.log`，用 macOS `.app` 启动的看 `~/Library/Logs/tunshuo-pet.log`；也可先跑 `python3 bootstrap.py --check` 确认依赖齐全。
- **网络与代理 / VPN**：桌宠用 Python 标准库 `urllib` 发请求，会自动继承 `HTTP_PROXY` / `HTTPS_PROXY`、macOS 系统代理、Windows 注册表代理（VPN 客户端改的就是这几处）。**已内置容错**：论坛请求走代理失败时，会绕过代理对同一 URL 直连重试一次——不改系统代理设置、不关证书校验、不写配置，所以开着 VPN 通常也能正常出榜；没走代理的失败不会重复请求，直连也失败则保留原始异常便于定位。
- **仍出现「拉取失败」**：跑 `python3 diagnose.py`（只读、联网），它会打印当前生效的代理，并在失败时做一次「绕过代理直连」对照，直连能通就给出 `DIAGNOSIS_FAIL 代理 / VPN 网络环境`。诊断如实反映网络环境，**报告代理不通不代表桌宠坏了**；只有桌宠确实拉不到时，才考虑退出 VPN / 换节点 / 把 `alumni.qiyuanheshan.com` 加入代理白名单或 `NO_PROXY` 后重启，其余再按证书、超时、DNS 的建议处理。气泡高度上限 96px，放不下英文异常，完整原因会写进日志：`bootstrap.py` 启动看 `logs/pet.log`，`.app` 启动看 `~/Library/Logs/tunshuo-pet.log`。贴诊断输出或日志末尾即可，不必截图气泡。

## 版本与更新提醒

分享出去之后，对方不需要记版本号，你也不需要群发通知。机制分三层：

**1. 谁来判断**：仓库根 `VERSION` 是唯一版本戳；`check_update.py` 只跑
`git fetch --quiet origin` + `git rev-list --count HEAD..@{u}` + `git show @{u}:VERSION`，
比较本地落后远端几个提交。只读，**不 pull、不改工作区、不写配置、不新增任何接口**。

**2. 什么时候提示、怎么提示**（三条触发路径，共用同一套话术）：

| 触发 | 行为 | 提示内容 |
|---|---|---|
| 对方 agent 跑 `python3 check_update.py` | 第一行输出 `UPDATE_AVAILABLE` / `UP_TO_DATE` / `UNKNOWN` / `NO_GIT` | 有新版时输出 `UPDATE_PROMPT` 固定话术，agent **原样转述**给用户，同一会话只提醒一次 |
| 桌宠每次启动约 7 秒后 | 后台自检一次 | **只在确实有新版时**冒一次气泡「小豚有新版本啦～让 agent 跑 git pull 就能更新」，并发一条托盘通知 |
| 右键 / 托盘「检查更新」 | 手动触发 | 无论有没有新版都回一句结果 |

**统一话术**（定义在 `check_update.py` 的 `UPDATE_PROMPT`，要改文案只改这一处，
`AGENTS.md` 与 README 都引用它，不会两处漂移）：

> 豚说小豚有新版本可用（本地 vX，线上 vY，落后 N 个提交）。
> 建议现在更新：让 agent 执行 `git pull --ff-only`，再运行 `python3 bootstrap.py --setup`，
> 最后从托盘退出并重新启动小豚即可生效。
> 若本地改过 config.json 等文件，agent 会先告知你，不会强行覆盖。

**3. 边界**：断网 → `UNKNOWN`，静默跳过不打扰；ZIP 分发 → `NO_GIT`，只是没有提醒，功能不受影响；
本地有未提交改动（`dirty=true`）→ 先告知用户，不许直接 pull 或 reset。
设环境变量 `TUNSHUO_SKIP_UPDATE_CHECK=1` 可关闭桌宠开机自检（不写 `config.json`）。

**发布新版本（维护者）**：改 `VERSION` → 在下方「版本记录」补一行 → `git push origin main`。
对方下次启动桌宠或让 agent 读仓库就会自动收到同一句提示，不需要额外通知。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| 4.2.3 | 2026-11-12 | 论坛请求在代理 / VPN 不通时自动直连重试一次（不关 VPN 也能出榜）；新增 `make_shortcut.py`，安装时自动在桌面 / 应用生成本机启动图标（macOS `.app`、Windows `.lnk`、Linux `.desktop`）；接口层自测 67 → 73 项 |
| 4.2.2 | 2026-11-12 | 新增 `diagnose.py` 一键网络诊断（含代理 / VPN 检测与直连对照）；拉取失败时完整异常写日志、气泡改人话；修复诊断分类遇到异常对象会崩溃的问题；把 VPN/代理列为排障首项 |
| 4.2.1 | 2026-11-11 | 修复更新检查在 detached HEAD / 无 upstream 时误报「已是最新」，改为 `UNKNOWN` 静默跳过 |
| 4.2.0 | 2026-11-11 | 新增 `AGENTS.md` 自动安装说明、`bootstrap.py` 一键补依赖、Windows 支持（托盘通知 / 字体 / `start_windows.bat`）、`VERSION` 版本戳与三层更新提醒 |
| 4.1.x 及更早 | 2026-11-11 前 | 榜单「最新 / 最热」切换、播报口径统一为时间最新、45 项面板离屏自测、四校圈子真实数据、关节皮肤与动作系统（历史提交见 `git log`） |

## License

MIT，见 [LICENSE](LICENSE)。

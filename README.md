# 豚说小豚 · 桌面宠物

豚说校园论坛的 macOS 桌面宠物原型：一只蓝色小鲸鱼常驻桌面右下角，会播报热帖、随机做待机动作，也能被拖拽、投喂。当前版本先在本地跑通体验，后续再迁移到小程序端。

仓库：https://github.com/2201242220-FranKing/tunshuo-pet

## 特性

- **单窗口绘制**：角色、气泡都在同一个透明窗口里用 `QPainter` 画，不新建顶层窗口，不会抢走你正在操作的界面焦点。
- **动作数据驱动**：`actions.json` 里 14 个出厂动作都是关键帧数组 `[t, dx, dy, 旋转°, 横缩放, 纵缩放, 翻转]`，`action_engine.py` 用 cosine 缓动插值；不再有硬编码动作函数。工作台可增删动作、编辑关键帧，发布后覆盖本地默认值；断网时回落到 `actions.json`。
- **关节皮肤（分层部件）**：默认整图模式行为完全不变；工作台启用 `rig` 皮肤后，角色按 manifest 拆成 身体/头/左右手/尾鳍/嘴 逐层绘制，每层有自己的枢轴与父子变换。关键帧第 8 位可选的部件字典能单独驱动头、手、嘴，做出转头、招手、张嘴；老数据没有第 8 位就等同原来的整体变换。`skin_rig.py` 负责 manifest 校验、父子链、z 序与包围盒，窗口遮罩按所有部件旋转后的范围计算，挥手不会被裁掉。
- **事件状态机**：来新帖 → 抬手播报（`announce`）、被拖动 → 手脚挣扎（`struggle`）、点击摸头 → 歪头（`nuzzle`）、待机 → 呼吸（`breathe`）；找不到对应触发动作时自动回落到原有逻辑。
- **待机随机动作**：每隔 4.5~11 秒随机播一个动作，另有随机眨眼、呼吸浮动。
- **拖动倾斜**：按最近 100ms 的平均速度计算倾斜角，慢拖也有明显反应，甩到 1200px/s 吃满 30°；松手有边缘吸附和回弹余震。
- **热帖播报**：可同时监控多个学校圈子（按 `circleId` 逐个拉取后合并出榜，条目带学校简称）；当前已接浙外真实数据。也可回退到内置演示数据。首次刷新只建立基线、不误报新帖；自动轮询默认关闭，手动「立即刷新」才拉。
- **状态**：连点 5 次跳舞、右键喂小鱼干、180 秒无操作自动睡觉（zzz），点击唤醒。
- **按需调帧**：动作/拖动 16.7fps、静止 6.7fps、睡觉 3.3fps；呼吸、倾斜、动作都按真实时间计算，降帧不会让动画变慢，长时间常驻更省电。
- **形象工作台**：配套网站 `tunshuo-pet-studio/` 可以可视化改外观、动作、台词、配饰，上传并切换整套皮肤包；发布后桌宠自动同步，皮肤素材下载到 `assets/skins/`。配饰画在角色的同一个变换里，跳起/倾斜时不会飘掉；`attach` 字段还能把帽子挂到头部、围巾挂到身体。断网时沿用上一次的形象。

## 环境要求

| 项 | 要求 |
|---|---|
| 系统 | macOS（用到了 `osascript`、`sips`、`iconutil`、`codesign` 与 Qt 的 macOS 专属属性） |
| Python | 3.9 ~ 3.13 |
| 依赖 | `PySide6-Essentials==6.9.2`；重新生成素材时另需 `Pillow` |

> PySide6 6.9.2 是在 macOS 12.6.1 / Intel 上验证过的版本。若你的环境装不上，可尝试同系列其它版本，但窗口遮罩与透明合成行为可能有差异。

## 快速开始

```bash
git clone https://github.com/2201242220-FranKing/tunshuo-pet.git
cd tunshuo-pet

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 tunshuo_pet_pro.py
```

启动后菜单栏会出现托盘图标（小豚不占 Dock）。日志写在 `~/Library/Logs/tunshuo-pet.log`。

## 打包成 .app（免终端）

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
| `notify_system` | `true` | 有新帖时是否发 macOS 系统通知。**工作台发布过形象后由工作台的「新帖系统通知」接管** |
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

### 论坛 REST 接口适配层（已按真实响应校准；当前启用浙外单校测试）

线上地址 `https://alumni.qiyuanheshan.com`。技术提供的接口：`/app/dynamic/page` 最新帖子、`/app/dynamic/new/num` 新帖提醒数、`/app/dynamic/ten/page` 十大热帖、`/app/dynamic/detail` 帖子详情。**上面的 `api_url` 是旧的单接口约定，继续有效**；新接口走 `forum_api.py`，聚合成同样的 7 字段列表，因此 `_on_posts()` 去重播报、`HotPanel` 排序渲染、双击打开链接全部零改动。

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

这些默认值只在 `DEFAULT_CONFIG` 里，**不会写回现有 config.json**（程序只在文件不存在时才创建它）。

**自检命令**（都不写任何配置）：

```bash
python3 forum_api.py --selftest                          # 67 项离线自测，不发网络请求
python3 forum_api.py --live --circle-id <学校圈子ID>     # 真实只读联调，作者自动打码
python3 forum_api.py --live --all                        # 不带圈子 ID，拉全站（仅验证用）
```

**多学校监控**：`forum_circles` 里每加一个学校，桌宠下次刷新就会多拉一个圈子，合并成一张按热度排序的榜单；条目标签会带学校简称。某个学校接口失败只影响它自己，其他学校照常出榜；全部失败时沿用上一轮结果，不会清空榜单。帖子若带 `circleId` 但与请求的圈子不符会被丢弃，防止 ID 填错或服务端回落全站时串进别校数据。上限 20 个学校，`seen` 去重上限已从 200 提到 1000，避免多学校时旧帖被误判成新帖。旧的 `forum_circle_id` 单值写法继续有效。

**启用 / 增删学校（用 `enable_forum.py`，默认只预览不写盘）**：

```bash
python3 enable_forum.py --list                                # 看当前监控了哪些学校
python3 enable_forum.py --add <圈子ID> --name <简称>           # 预览 + 只读联调
python3 enable_forum.py --add <圈子ID> --name <简称> --apply   # 正式加入（重复 ID 只更新名称）
python3 enable_forum.py --remove <圈子ID> --apply             # 移除一个学校；移空则回退演示数据
python3 enable_forum.py --off --apply                        # 一键清空回退
python3 enable_forum.py --circle-id <圈子ID> --apply         # 旧写法：只监控一个学校
```

脚本只改 `forum_base` / `forum_circles` / `forum_circle_id` / `forum_allow_all` 四个键，其余配置原样保留，**令牌永远不写盘**；也不会替你重启桌宠。写入后退出并重启 `.app` → 右键「立即刷新」，首次刷新只建立基线不误报新帖。若要定时播报，再单独把 `auto_poll` 设为 `true`（轮询条件已兼容 `api_url` 或 `forum_base` 任一配好）；当前按用户要求保持关闭。

**当前现场状态（2026-11-10）**：已启用浙外圈子 `1844924022131912706`（名称「浙外」）做测试，桌宠已重启加载真实数据；其余学校 ID 待用户提供后用 `--add` 追加。

**仍需技术确认**：学校 `circleId` 实际值、十大热帖/新帖数需登录（返回 `code=110 请先登录`）、原帖 H5 链接规则、`new/num` 的 `time` 语义与 `tagId` 枚举、站内信未读的正确路径。可直接转发 `论坛接口待确认清单.txt`（已标注哪些项实测通过、不用重复给）。技术文档里「十大热帖」和「站内信 提醒未读消息」写成了同一个 `GET /app/dynamic/ten/page?circleId=`，疑似笔误；`ForumClient.unread()` 已保留但默认抛明确错误，路径确认后改 `UNREAD_PATH` 即可，站内信角标属于新 UI，尚未实现。

## 交互一览

| 操作 | 效果 |
|---|---|
| 悬停 | 随机张望 |
| 单击 | 抖一下，播报当前最热帖或随机一句 |
| 双击 | 打开 / 关闭热帖榜（双击条目打开原帖） |
| 连点 5 次 | 跳舞彩蛋 |
| 按住左右拖 | 移动 + 按速度倾斜 + 关节皮肤下手脚挣扎 + 松手边缘吸附与余震 |
| 来新帖 / 摸头 | 关节皮肤下抬手播报 / 歪头眯眼（整图模式仍是原来的蹦一下/抖动） |
| 右键 | 喂小鱼干、随机动作、睡/醒、热帖榜、立即刷新、暂停提醒、打开形象工作台、重新同步形象、退出 |
| 菜单栏托盘 | 隐藏/显示、喂鱼、动一下、回到右下角、热帖榜、立即刷新、打开形象工作台、重新同步形象、退出 |

## 目录结构

```
tunshuo-pet/
├── tunshuo_pet_pro.py     主程序（绘制 / 动作 / 交互 / 数据源 / 托盘）
├── studio_sync.py         形象工作台同步：拉取、归一化、缓存、配饰 QPixmap
├── actions.json           14 个出厂动作关键帧（桌宠离线默认，工作台发布可覆盖）
├── action_engine.py       动作解释器：数据校验 / 缓动插值 / 部件通道
├── skin_rig.py            皮肤 manifest 校验、父子变换链、z 序、包围盒
├── forum_api.py           论坛 REST 适配层（真实字段已校准，默认不启用，可离线/联网自检）
├── enable_forum.py        论坛接口启用/回退/增删学校（默认只预览，--apply 才写配置）
├── 论坛接口待确认清单.txt   可直接转发技术的追问清单（含已实测通过的项）
├── make_app.py            macOS .app 打包脚本
├── config.json            用户配置（入库）
├── state.json             运行时状态（自动生成，不入库）
├── studio_cache.json      上次同步的官方形象（自动生成，不入库）
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

- 仅 macOS；Windows / Linux 上托盘通知、打包脚本与部分窗口属性不适用。
- 已启用浙外真实数据做测试，自动轮询按用户要求保持关闭（只有右键「立即刷新」才拉一次）。十大热帖与新帖数接口需登录，当前自动降级为「最新帖按热度出榜」；接口不返回 url，双击打开原帖待技术给 H5 链接规则。学校 ID 目前只有浙外一个，其余待补；可用 `--off --apply` 随时回退到演示数据。
- 形象同步依赖 `tunshuo-pet-studio/` 的服务；工作台没运行时桌宠用本地缓存继续跑，不会报错，但新发布的形象要等服务起来（或手动「重新同步形象」）才生效。不想联网就把 `studio_url` 留空。
- `assets/skins/placeholder/` 是**程序从现有 `pet.png` 切出来的技术验证包**，不是最终美术：小角度（头 ≤10°、手 ≤35°）没有破洞，角度再大会露出同色底补的月牙。正式皮肤请按 `tunshuo-pet-studio/JOINT_SPEC.md` 重画挖空底图与部件层，直接放进工作台替换即可，代码不用改。
- 无边框透明窗口必须关掉系统投影（`Qt.NoDropShadowWindowHint`），否则动作播放、遮罩变矩形时，macOS 会在角色背后投出一块灰黑方块。
- 若启动后没有反应，先看 `~/Library/Logs/tunshuo-pet.log`；启动器会在 PySide6 缺失时写明原因。

## License

MIT，见 [LICENSE](LICENSE)。

# 豚说小豚 · 桌面宠物

豚说校园论坛的 macOS 桌面宠物原型：一只蓝色小鲸鱼常驻桌面右下角，会播报热帖、随机做待机动作，也能被拖拽、投喂。当前版本先在本地跑通体验，后续再迁移到小程序端。

仓库：https://github.com/2201242220-FranKing/tunshuo-pet

## 特性

- **单窗口绘制**：角色、气泡都在同一个透明窗口里用 `QPainter` 画，不新建顶层窗口，不会抢走你正在操作的界面焦点。
- **动作数据驱动**：`actions.json` 里 9 个出厂动作都是关键帧数组 `[t, dx, dy, 旋转°, 横缩放, 纵缩放, 翻转]`，`action_engine.py` 用 cosine 缓动插值；不再有硬编码动作函数。工作台可增删动作、编辑关键帧，发布后覆盖本地默认值；断网时回落到 `actions.json`。
- **待机随机动作**：每隔 4.5~11 秒随机播一个动作，另有随机眨眼、呼吸浮动。
- **拖动倾斜**：按最近 100ms 的平均速度计算倾斜角，慢拖也有明显反应，甩到 1200px/s 吃满 30°；松手有边缘吸附和回弹余震。
- **热帖播报**：内置演示数据；填入 `api_url` 后可切到真实论坛接口。首次刷新只建立基线、不误报新帖；打开 `auto_poll` 后按分钟定时拉取。
- **状态**：连点 5 次跳舞、右键喂小鱼干、180 秒无操作自动睡觉（zzz），点击唤醒。
- **按需调帧**：动作/拖动 16.7fps、静止 6.7fps、睡觉 3.3fps；呼吸、倾斜、动作都按真实时间计算，降帧不会让动画变慢，长时间常驻更省电。
- **形象工作台**：配套网站 `tunshuo-pet-studio/` 可以可视化改外观、动作、台词和配饰；发布后桌宠自动同步。配饰画在角色的同一个变换里，跳起/倾斜时不会飘掉。断网时沿用上一次的形象。

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
| `auto_poll` | `false` | 是否定时拉新帖。**仅在 `api_url` 非空时生效**；演示数据模式下不会启动，避免假数据反复弹提醒 |
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

## 交互一览

| 操作 | 效果 |
|---|---|
| 悬停 | 随机张望 |
| 单击 | 抖一下，播报当前最热帖或随机一句 |
| 双击 | 打开 / 关闭热帖榜（双击条目打开原帖） |
| 连点 5 次 | 跳舞彩蛋 |
| 按住左右拖 | 移动 + 按速度倾斜 + 松手边缘吸附与余震 |
| 右键 | 喂小鱼干、随机动作、睡/醒、热帖榜、立即刷新、暂停提醒、打开形象工作台、重新同步形象、退出 |
| 菜单栏托盘 | 隐藏/显示、喂鱼、动一下、回到右下角、热帖榜、立即刷新、打开形象工作台、重新同步形象、退出 |

## 目录结构

```
tunshuo-pet/
├── tunshuo_pet_pro.py     主程序（绘制 / 动作 / 交互 / 数据源 / 托盘）
├── studio_sync.py         形象工作台同步：拉取、归一化、缓存、配饰 QPixmap
├── actions.json           出厂动作关键帧（桌宠离线默认，工作台发布可覆盖）
├── action_engine.py       动作解释器：数据校验 / 缓动插值 / 待机权重
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
- 默认使用演示数据，尚未接真实论坛接口；自动轮询默认关闭，接好接口后需在 `config.json` 里把 `auto_poll` 设为 `true`。
- 形象同步依赖 `tunshuo-pet-studio/` 的服务；工作台没运行时桌宠用本地缓存继续跑，不会报错，但新发布的形象要等服务起来（或手动「重新同步形象」）才生效。不想联网就把 `studio_url` 留空。
- 无边框透明窗口必须关掉系统投影（`Qt.NoDropShadowWindowHint`），否则动作播放、遮罩变矩形时，macOS 会在角色背后投出一块灰黑方块。
- 若启动后没有反应，先看 `~/Library/Logs/tunshuo-pet.log`；启动器会在 PySide6 缺失时写明原因。

## License

MIT，见 [LICENSE](LICENSE)。

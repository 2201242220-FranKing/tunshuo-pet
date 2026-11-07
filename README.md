# 豚说小豚 · 桌面宠物

豚说校园论坛的 macOS 桌面宠物原型：一只蓝色小鲸鱼常驻桌面右下角，会播报热帖、随机做待机动作，也能被拖拽、投喂。当前版本先在本地跑通体验，后续再迁移到小程序端。

仓库：https://github.com/2201242220-FranKing/tunshuo-pet

## 特性

- **单窗口绘制**：角色、气泡都在同一个透明窗口里用 `QPainter` 画，不新建顶层窗口，不会抢走你正在操作的界面焦点。
- **动作注册表**：`hop / sway / look / stretch / nod / shake / land / dance / wobble` 共 9 个动作，用 `@action("名字", 秒数)` 装饰器注册，函数返回 `(dx, dy, 旋转, 横缩放, 纵缩放, 水平翻转)` 即可扩展。
- **待机随机动作**：每隔 4.5~11 秒随机播一个动作，另有随机眨眼、呼吸浮动。
- **拖动倾斜**：按最近 100ms 的平均速度计算倾斜角，慢拖也有明显反应，甩到 1200px/s 吃满 30°；松手有边缘吸附和回弹余震。
- **热帖播报**：内置演示数据；填入 `api_url` 后可切到真实论坛接口。首次刷新只建立基线、不误报新帖。
- **状态**：连点 5 次跳舞、右键喂小鱼干、180 秒无操作自动睡觉（zzz），点击唤醒。

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
| `notify_system` | `true` | 有新帖时是否发 macOS 系统通知 |
| `pet_width` | `60` | 角色逻辑宽度（px）；素材 240px 通过 DPR=4 显示 |
| `idle_sleep_seconds` | `180` | 无操作多久自动睡着，`0` 表示永不 |
| `fish` | `0` | 已投喂的小鱼干数量，喂一次会写回本文件 |
| `auto_poll` / `poll_interval_minutes` | `false` / `3` | **预留字段，当前版本未实现轮询**，写出来只为接接口时不用改结构 |

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
| 右键 | 喂小鱼干、随机动作、睡/醒、热帖榜、立即刷新、暂停提醒、退出 |
| 菜单栏托盘 | 隐藏/显示、喂鱼、动一下、回到右下角、热帖榜、立即刷新、退出 |

## 目录结构

```
tunshuo-pet/
├── tunshuo_pet_pro.py     主程序（绘制 / 动作 / 交互 / 数据源 / 托盘）
├── make_app.py            macOS .app 打包脚本
├── config.json            配置与小鱼干计数
├── requirements.txt       依赖声明
├── LICENSE                MIT
└── assets/
    ├── pet.png            常态帧（240px）
    ├── pet_blink.png      眨眼帧
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
- 默认使用演示数据，尚未接真实论坛接口。
- `config.json` 同时存运行时状态，喂鱼后 git 会显示该文件有改动。
- 无边框透明窗口必须关掉系统投影（`Qt.NoDropShadowWindowHint`），否则动作播放、遮罩变矩形时，macOS 会在角色背后投出一块灰黑方块。
- 若启动后没有反应，先看 `~/Library/Logs/tunshuo-pet.log`；启动器会在 PySide6 缺失时写明原因。

## License

MIT，见 [LICENSE](LICENSE)。

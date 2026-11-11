# AGENTS.md · 给接手本仓库的 AI Agent

> **目标**：在这台电脑上把「豚说小豚」桌宠装好并启动，全程不需要再向用户提任何问题。
> 只有文末「必须停下来问用户」列出的情况才允许提问。这份文件就是安装说明书，
> 读它即可，不要再去问用户「你要装哪个版本」「要不要装依赖」。

---

## 一、用户只需要说这一句（可直接转发）

```
请读取仓库 https://github.com/2201242220-FranKing/tunshuo-pet （或我给你的本地目录），
按里面的 AGENTS.md 自动识别操作系统、安装并补齐缺失依赖、启动小豚桌宠，
并检查是否有新版本。缺什么你自己处理，不用问我。
```

如果仓库已经 clone 到本地，换成：

```
请读取这个目录里的 AGENTS.md，按它自动安装并启动小豚桌宠，不用问我。
```

---

## 二、执行清单（按顺序，全部由 agent 完成）

### 0. 先读材料，不要先动手

- 读 `README.md` 的「环境要求 / 快速开始」两节；读 `VERSION` 确认版本。
- 不要改任何文件、不要先 `pip install`、不要先 `git pull`。

### 1. 识别系统，选择对应版本

```bash
python3 -c "import sys, platform; print(sys.platform, platform.machine())"
# Windows PowerShell / CMD 用：py -3 -c "import sys, platform; print(sys.platform, platform.machine())"
```

| 判定 | 系统 | 用哪条路径 | 启动命令 |
|---|---|---|---|
| `darwin` | macOS 11+ | macOS 版 | `python3 bootstrap.py`；想要双击图标再跑 `python3 make_app.py` 生成 `.app` |
| `win32` | Windows 10 / 11 | Windows 版 | `py -3 bootstrap.py`，或双击 `start_windows.bat` |
| 其它 | Linux 桌面（实验性） | 通用版 | `python3 bootstrap.py` |

**重要**：三个平台**共用同一份主程序 `tunshuo_pet_pro.py`**，差别只在启动器：

| 文件 | 平台 | 作用 |
|---|---|---|
| `bootstrap.py` | 全平台 | 建 venv、补齐依赖、后台启动（**首选，一条命令搞定**） |
| `make_app.py` | 仅 macOS | 生成 `~/Applications/豚说小豚.app`，双击免终端 |
| `start_macos.command` | 仅 macOS | 双击运行（走 bootstrap） |
| `start_windows.bat` | 仅 Windows | 双击运行（走 bootstrap） |

仓库里**没有、也不需要**单独的「Windows 版 exe」或另一套源码。别去找、别去下载、
别自作主张用 PyInstaller 重打包。若 clone 下来的是 ZIP 而不是 git 仓库，只是少了自动
更新检查，安装运行不受影响。

### 2. 自动安装并补齐依赖

```bash
python3 bootstrap.py              # Windows：py -3 bootstrap.py
```

它会自动完成：校验 Python 3.9~3.13（64 位）→ 缺 `.venv` 就建 → 用 venv 解释器重跑自己
→ 缺 `PySide6-Essentials` / `Pillow` 就 `pip install -r requirements.txt` → 后台启动桌宠。
**命令会立即返回**，不会卡住你的会话；日志在 `logs/pet.log`。

若你希望自己管理进程（长会话推荐），改用两步：

```bash
python3 bootstrap.py --setup       # 只装依赖，不启动
python3 tunshuo_pet_pro.py         # 用后台任务方式启动，会话可继续
```

> `.venv` 建好后，手动启动请用 `.venv/bin/python`（Windows 是 `.venv\Scripts\python.exe`），
> 否则系统 Python 里可能没装 PySide6。

### 3. 自检（不用等用户确认，直接跑）

```bash
python3 bootstrap.py --check        # 环境体检：只读，输出 ENV_OK / ENV_MISSING
python3 forum_api.py --selftest     # 接口层 67 项离线自测
python3 selftest_panel.py           # 面板 / 播报 36 项离屏自测，不弹窗
```

三项全过才算装好；不通过就按报错修，不要跳过、不要降低标准。

### 4. 检查更新，并按固定话术提醒用户

```bash
python3 check_update.py
```

输出第一行是状态：`UPDATE_AVAILABLE` / `UP_TO_DATE` / `UNKNOWN` / `NO_GIT`。

- **`UPDATE_AVAILABLE`** → 把命令输出的提示话术**原样转述给用户**（话术唯一定义在
  `check_update.py` 的 `UPDATE_PROMPT`，不要自己另编一套）。同一会话只提醒一次。
- 用户同意后再更新：`git pull --ff-only` → `python3 bootstrap.py --setup` →
  从托盘退出并重启桌宠。**不要替用户擅自 pull。**
- 结果里 `dirty=true`（本地有未提交改动）→ **先告知用户**，不要直接 pull，
  更不要 `reset --hard` / `checkout --` 覆盖。
- `UP_TO_DATE` / `UNKNOWN` / `NO_GIT` → 静默跳过，不打扰用户，也不要当成错误。

桌宠本身也有两层提醒：每次启动约 7 秒后自检一次，**只在确实有新版时**冒一次气泡；
右键菜单和托盘菜单里都有「检查更新」可手动触发。设 `TUNSHUO_SKIP_UPDATE_CHECK=1`
可关闭开机自检（不写 config.json）。

### 5. 收尾告知用户

桌宠在屏幕右下角；双击看帖子榜（可切「最新 / 最热」），右键 / 系统托盘可刷新、隐藏、
退出。源码或 `VERSION` 变过之后，**必须重启桌宠**才加载新代码。

---

## 三、边界：绝对不要做

- 不改 `config.json` 的默认值、不写入任何 token / 密钥 / 账号密码。
- 不 `git pull` 覆盖本地改动、不 `reset --hard`、不 `checkout --`、不删除仓库文件。
- 不引入 `requirements.txt` 之外的依赖；不换 pip 源；不装 PyInstaller 等新工具。
- 不调用除 **PyPI、仓库自身 git 远端**、`config.json` 里已配置的论坛地址
  `https://alumni.qiyuanheshan.com` 与本地工作台 `127.0.0.1:8770` 之外的服务。
- 不把别人打包好的 `.app` / `.exe` 拷来用：`make_app.py` 生成的启动器绑定了本机
  Python 路径与源码目录，换机器必须在本机重新生成。
- 不替用户发帖、回复或做任何写操作；论坛接口只读，且 `page` / `detail` 匿名可读、
  **不需要登录、不需要用户 provide 任何东西**。

---

## 四、必须停下来问用户的 4 种情况

1. 找不到 Python，或版本不在 3.9~3.13 / 是 32 位 → 请用户装
   [Python 3.9~3.13 64 位](https://www.python.org/downloads/)（Windows 勾上 Add Python to PATH）。
2. `pip install` 失败（无网络、公司代理、磁盘不足）→ 把 `bootstrap.py --check` 的结果
   贴给用户再问，不要自行换源或降级依赖。
3. 仓库私有、clone 被拒绝 → 请仓库主人把 HTTPS 地址设为公开或给对方权限。
4. 系统托盘不可用（无头 Linux / 某些远程桌面）→ 问用户是否仍以无托盘模式运行。

除此之外，一律自己判断、自己执行、自己补齐。

---

## 五、给维护者：发布新版本时怎么让所有人收到提醒

1. 改仓库根的 `VERSION`（如 `4.2.0` → `4.2.1`）并提交。
2. 在 README「版本记录」补一行改了什么。
3. `git push origin main`。

对方什么都不用做：agent 下次跑 `check_update.py` 就会拿到 `UPDATE_AVAILABLE` 和统一话术，
桌宠每次启动也会自检并冒气泡。**不需要群发通知，也不需要对方记版本号**。
`check_update.py` 只做 `git fetch / rev-list / show`，不 pull、不改工作区、不新增接口。

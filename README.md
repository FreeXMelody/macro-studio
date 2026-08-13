# Macro Studio

```text
 __  __                         ____  _             _ _       
|  \/  | __ _  ___ _ __ ___    / ___|| |_ _   _  __| (_) ___  
| |\/| |/ _` |/ __| '__/ _ \   \___ \| __| | | |/ _` | |/ _ \ 
| |  | | (_| | (__| | | (_) |   ___) | |_| |_| | (_| | | (_) |
|_|  |_|\__,_|\___|_|  \___/   |____/ \__|\__,_|\__,_|_|\___/ 
```

一个面向 Windows 桌面应用的轻量自动操作工作台。

它最初来自“剧组歌单顺序播放”的需求：维护一组歌曲，自动搜索、点击、等待、播放。现在它已经扩展为更通用的桌面宏工具：你可以采集点位、编排动作、保存预设、绑定歌单变量，也可以用截图模板做视觉识别点击。

> 本项目用于个人自动化和辅助操作。使用时请遵守目标软件的用户协议、社区规则和当地法律法规。

## Highlights

- **点位分组**：为不同应用、不同流程维护独立坐标组。
- **热键采集**：选中点位后移动鼠标，按 `F8` 保存坐标。
- **动作序列**：新增、更新、复制、删除、拖拽排序、启用/禁用。
- **动作预设**：新建、保存、载入、复制、重命名、删除。
- **歌单变量**：每首歌执行同一套或指定动作预设，支持分组、全部视图、随机和循环。
- **急停热键**：运行中按 `F9` 强制停止。
- **图像目标**：模板图预览、剪贴板截图导入、拖拽选区。
- **视觉点击**：`image_click` 使用 OpenCV 模板匹配，命中后自动点击。

## Screens In Your Head

```text
+----------------+  +-------------------------+  +----------------+
| Point Groups   |  | Action Sequence         |  | Playlist       |
| - Search box   |  | 1. click 搜索框         |  | KPOP           |
| - Play button  |  | 2. paste {keyword}      |  | 优雅           |
| F8 capture     |  | 3. image_click 播放图标 |  | 可爱           |
+----------------+  +-------------------------+  +----------------+
```

## Requirements

- Windows
- Python 3.10+
- Tkinter，通常随 Python Windows 安装包自带

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the current Tkinter UI:

```powershell
python macro_studio.py
```

On the `refactor/tauri-vue3` branch, the local sidecar API can also run independently:

```powershell
python -m backend.main
```

It binds to a random `127.0.0.1` port and prints one `sidecar.ready` JSON object containing the temporary session token. The run center defaults to simulation mode and can explicitly switch to the Windows executor for real actions. Press F9 for an emergency stop.
Run the browser development stack without Rust. This starts Vue and the Python sidecar together, injects the temporary token, and stops both when the command exits:

```powershell
npm --prefix frontend install
npm run web:dev
```

Use `npm run frontend:dev` only when you intentionally want the UI without a sidecar; automation and target testing will stay disconnected in that mode.

Run the complete Tauri development app (Rust must be installed):

```powershell
npm install
npm run dev
```

The launcher automatically locates Cargo in the default rustup directory even when the current terminal has an outdated `PATH`. If the system drive has limited free space, save a machine-local Cargo build directory before starting Tauri:

```powershell
Set-Content .cargo-target 'D:\CargoTarget\macro-studio'
npm run dev
```

The `.cargo-target` file is ignored by Git and can contain a drive path specific to the current machine.

In development, Tauri starts `python -m backend.main` automatically and passes its one-time loopback connection to Vue over Tauri IPC. A packaged production build additionally needs the Python sidecar executable; that packaging step is tracked separately from the current development shell.

## Quick Start

1. 打开程序，确认“窗口关键词”能匹配目标应用窗口。
2. 在“点位”里新建点位，选中后把鼠标移到目标位置，按 `F8` 采集坐标。
3. 在“动作序列”里编排 `click`、`paste`、`wait` 等动作。
4. 在“歌单变量”里添加歌曲，并用 `{keyword}`、`{total}` 这类变量驱动动作。
5. 点击“播放歌单”。运行中可按 `F9` 急停。

## Image Click Workflow

`image_click` 适合处理坐标不稳定、按钮位置会变化、或者只想“看到某个图标就点”的场景。

1. 打开“图像目标”。
2. 用 `Win + Shift + S` 截图，然后点击“读取剪贴板”。
3. 用“模板预览”确认截图是否正确。
4. 点击“拖拽选区 Ctrl+R”，程序会暂时隐藏，拖出识别范围；留空表示全屏识别。
5. 在动作序列中新增 `image_click`，参数填写图像目标名称。

参数说明：

| 参数 | 说明 |
| --- | --- |
| 阈值 | 模板匹配最低相似度，常用 `0.80` 到 `0.95` |
| 边缘低阈值 | Canny 弱边缘阈值；越低保留的细节越多，同时更容易带入场景噪声 |
| 边缘高阈值 | Canny 强边缘阈值；越高轮廓越干净，同时可能漏掉较淡的图标边缘 |
| 偏移X/Y | 命中模板中心后再偏移点击的位置 |
| 重试秒 | 单轮持续识别时间；超时后会按动作序列恢复策略重试或回退 |

边缘低/高阈值只影响 `edge`、`masked_edge` 以及自动选择边缘算法的 `smart` 模式；`grayscale` 不使用这两个参数。


## Stage Search

歌单面板里的“剧组搜索”可以调用剧组站搜索接口，读取候选作品的 `property` 元数据，并自动从 `actionTime` / `speechTime` 填入作品时长。结果列表会显示分类、作者、时长、热度、收藏数、喜欢数和封面预览，默认只筛选单人作品。

`role_id` / `user_id` 是当前账号角色标识，通常同一角色下比较稳定；`skey` 是会话票据，可能会随登录或过期变化；`sort` / `page_size` / 分类过滤是搜索参数。打开剧组搜索窗口时，程序会通过 WinDivert 启动一次性只读监听；接受 UAC 后，在 90 秒内于游戏剧组站搜索一次作品，即可自动捕获并验证这些参数。剪贴板导入保留为备用入口。配置只保存在本地 `macro_config.json`，不要提交到仓库。

建议流程：打开剧组搜索，接受监听权限，在游戏内执行一次搜索；参数验证通过后，从候选列表选择作品，然后“填入表单”或“加入歌单”。

## Stage Diagnostics

“剧组搜索”窗口里的“诊断”按钮会只读扫描本机 WebView 缓存、关键 DLL 字符串和最近游戏日志，用来辅助判断剧组站是否存在可调用的 native bridge 或播放入口。

推荐流程：

1. 打开游戏并进入剧组站。
2. 搜索一个作品，最好再点一次“预览作品”。
3. 关闭游戏，让 WebView 缓存文件释放。
4. 打开 Macro Studio，进入“剧组搜索”，点击“诊断”。
5. 查看报告里的“结论 / 提示”“WebView 缓存命中”“游戏模块命中”和“最近播放/桥接日志”。

也可以命令行生成报告：

```powershell
python .\stage_diagnostics.py .\stage_diagnostics_report.txt
```

诊断报告可能包含本机路径、缓存 URL 和日志片段，默认不会提交到仓库。
## Action Types

| 类型 | 说明 |
| --- | --- |
| `click` | 点击指定点位，需填写点位名 |
| `image_click` | 按图像目标名称识别模板，命中后点击 |
| `paste` | 粘贴文本，支持变量，例如 `{keyword}` |
| `wait` | 等待秒数或 `mm:ss` |
| `key` | 单击指定按键，例如 `space`、`esc`、`f5`、`a` |
| `key_hold` | 长按指定按键，例如 `space@0.8` |
| `key_down` | 按下指定按键，直到后续 `key_up` 抬起 |
| `key_up` | 抬起指定按键 |
| `enter` | 按 Enter |
| `ctrl_a` | 按 Ctrl+A |
| `hotkey` | 单击组合键，例如 `ctrl+v`、`alt+f4`、`shift+tab` |
| `hotkey_hold` | 长按组合键，例如 `ctrl+space@0.5` |
| `open_uri` | 打开网页或 Windows 协议链接，例如剧组站深链 |
| `http_request` | 发送一次 HTTP 请求，例如 `GET http://127.0.0.1:端口/path` |
| `log` | 写一条日志，便于调试流程 |

除 `wait` 外，每个动作都可以填写“后等待”，表示动作执行完成后额外等待多久。`key`/`hotkey` 支持常见键名：字母、数字、`space`、`tab`、`esc`、方向键、`home`、`end`、`delete`、小键盘 `num0` 到 `num9`、`f1` 到 `f24`；也可以用 `vk:0x20` 这类 Windows 虚拟键码。动作面板里的“按键设置”按钮可以用表单生成单击、长按、按下、抬起、组合键和组合键长按参数。`open_uri` 和 `http_request` 主要用于探索剧组站入口：拿到真实深链或本地接口后填入参数即可测试。

## Playlist Variables

动作参数中可以使用：

| 变量 | 说明 |
| --- | --- |
| `{title}` | 作品名 |
| `{keyword}` | 搜索词 |
| `{duration}` | 歌曲时长，秒 |
| `{buffer}` | 额外等待，秒 |
| `{total}` | 歌曲时长 + 额外等待 |

常见用法：

- `paste` 动作填 `{keyword}`，执行时粘贴当前歌曲搜索词。
- `wait` 动作填 `{total}`，等待当前歌曲播放完成。

## Local Files And Privacy

程序运行时会使用这些本地文件：

- `macro_config.json`：窗口关键词、点位、动作序列、动作预设、图像目标
- `playlist.json`：歌单分组和歌曲变量
- `image_templates/`：从剪贴板读取的模板图片

这些文件默认被 `.gitignore` 忽略，因为它们通常包含个人坐标、歌单和截图。仓库只提供安全示例：

- `macro_config.example.json`
- `playlist.example.json`

可复制示例作为初始配置：

```powershell
Copy-Item macro_config.example.json macro_config.json
Copy-Item playlist.example.json playlist.json
```

## Development Check

```powershell
python -m py_compile .\macro_studio.py .\models.py .\storage.py .\utils.py .\automation.py .\vision.py .\stage_api.py .\stage_http_listener.py .\stage_transport.py .\stage_diagnostics.py
python -m compileall -q .\backend
python -m unittest discover -s .\tests -v
```

Vue 3 + TypeScript + Tauri 的渐进式迁移约束与验收阶段见 [`docs/TAURI_REFACTOR_STRATEGY.md`](docs/TAURI_REFACTOR_STRATEGY.md)。

## Roadmap Ideas

- 窗口相对坐标，减少窗口移动后的重新采集。
- 更完整的快捷键系统。
- OCR 或更高级的视觉判断。
- 条件动作、失败重试、分支流程。
- 更彻底的模块化和测试覆盖。

## License

MIT

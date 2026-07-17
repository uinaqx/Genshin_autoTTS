# Genshin_autoTTS

一个轻量、开源的 Windows 游戏自动配音伴侣。它只读取屏幕像素，通过 OCR 识别“说话角色”和“字幕”，为角色分配并持久化固定音色，然后自动生成、缓存和播放语音。

项目使用 Edge 中文神经网络音色，不需要下载大型语音包。它不会回退到传统 Windows SAPI 机器音；网络或神经语音服务不可用时会明确报错。生成的 MP3 按设定容量自动淘汰最久未使用的内容。

> “神经人声”表示高自然度合成语音，不等同于真人演员预录。世界任务本身没有官方真人录音；如验收标准严格要求真人演员录制，则必须另行取得逐句录音及授权，任何 TTS 都不能被描述为真人原录。

> 本项目是非官方辅助工具，与米哈游、HoYoverse 或《原神》无关联。它不注入游戏进程、不读取游戏内存、不修改游戏文件，也不包含或分发游戏文本、音频、模型及其他受版权保护的资源。使用者应自行遵守游戏服务条款和所在地区法律。

## 已实现流程

```mermaid
flowchart LR
    A[屏幕框选区域] --> B[定时截图]
    B --> C[RapidOCR 本地识别]
    C --> D[角色名与字幕规范化]
    D --> E[多帧稳定与重复过滤]
    E --> F[固定角色音色档案]
    F --> I[在线神经网络人声]
    I --> K[MP3 音频]
    K --> L[SQLite 索引的容量受限缓存]
    L --> M[自动播放]
```

- 分别框选角色名与字幕区域，适配不同分辨率和 UI 布局。
- OCR 完全在本机运行，不上传截图。
- 针对逐字出现的游戏字幕进行多帧稳定，避免朗读半句话。
- 相同角色永久复用同一音色；映射保存在本地 JSON 中。
- 仅使用高自然度中文神经网络音色，拒绝回退到传统 SAPI 机器音。
- 神经语音失败时明确提示，避免低质量音色被误认为成功。
- 语音按内容寻址，重复台词直接命中缓存。
- 缓存默认上限 256 MB，可在界面修改，并使用 LRU 自动清理。
- 提供无需打开游戏的演示命令，以及覆盖 OCR、TTS、播放和缓存的真实冒烟测试。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10、3.11 或 3.12（推荐 3.11）
- 可访问 Edge 神经语音服务的网络连接

## 安装

在 PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
```

开发与测试环境：

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

首次使用 RapidOCR 时会初始化随 Python 包安装的本地模型，可能需要等待数秒。

## 使用

启动桌面程序：

```powershell
.\.venv\Scripts\genshin-autotts-gui.exe
```

1. 将游戏设置为窗口化或无边框窗口模式。
2. 在一段无配音对话停留时，点击“框选角色名区域”，只框住角色名称可能出现的位置。
3. 点击“框选字幕区域”，只框住对话正文可能出现的位置。
4. 点击“全流程测试”，确认联网神经人声可以正常播放。
5. 点击“开始自动配音”。

为提高识别率，框选范围应尽量紧，不要包含头像、按钮和背景中的其他文字。游戏 UI 缩放或分辨率变化后需要重新框选。

### 命令行检查

直接生成一条语音，不截图：

```powershell
.\.venv\Scripts\genshin-autotts.exe demo --speaker 派蒙 --text "旅行者，我们出发吧！"
```

运行真实全链路冒烟测试（合成测试图片 → OCR → 稳定器 → 神经人声 → 二次缓存命中）：

```powershell
.\.venv\Scripts\genshin-autotts.exe smoke
```

启动可供人工框选的游戏字幕测试场景：

```powershell
.\.venv\Scripts\genshin-autotts.exe fixture
```

显示当前配置和数据目录：

```powershell
.\.venv\Scripts\genshin-autotts.exe config
```

## 轻量化策略

本项目不预装全量世界任务语音。角色档案只有少量 JSON 数据；语音仅在实际遇到台词时按需生成。

按约 48 kbps MP3 粗略计算，一分钟语音约 360 KB，256 MB 可保存约 12 小时音频。缓存达到上限后会自动删除最久未播放的条目。

运行数据默认位于：

```text
%LOCALAPPDATA%\GenshinAutoTTS\
├── config.json
├── speaker_profiles.json
└── cache\
    ├── cache.sqlite3
    └── objects\
```

测试或便携运行时可通过环境变量改位置：

```powershell
$env:GENSHIN_AUTOTTS_HOME = "D:\GenshinAutoTTSData"
```

`speaker_profiles.json` 可备份，以便重装后继续复用角色音色。删除某个角色的记录后，该角色会在下次出现时重新分配音色。

## 配置说明

首次启动会自动创建配置。完整示例见 [`config.example.json`](config.example.json)。主要参数：

| 参数 | 默认值 | 作用 |
| --- | ---: | --- |
| `ocr_interval_ms` | 300 | 截图识别间隔 |
| `stability_frames` | 3 | 连续稳定多少帧才朗读 |
| `minimum_stable_ms` | 600 | 字幕至少稳定多久 |
| `repeat_cooldown_seconds` | 8 | 相同角色与台词的防重复时间 |
| `tts_provider` | `edge` | 高自然度神经人声；旧版 `sapi` 配置会自动迁移 |
| `cache_max_mb` | 256 | 本地音频缓存上限 |

## 音色分配

程序会先读取内置的少量角色特征提示；未知角色则根据角色名哈希稳定分配性别、年龄感和语速风格。最终档案立即写入 `speaker_profiles.json`，所以同一角色后续始终使用同一音色。

程序使用多种中文神经网络音色，并按性别、年龄感和表达风格固定分配。当前版本不会克隆原角色声线，也不会训练或分发任何角色模型；音频是高自然度合成结果，而非原角色声优或其他真人演员的预录音。

## 已知限制

- OCR 对透明字幕、复杂背景、动态模糊和极小字号较敏感。
- 当前通过两个固定区域识别 UI；不自动判断不同游戏的对话框位置。
- 仅凭角色名无法可靠推断完整性格。未知角色采用可复现的风格分配，而非语义人格分析。
- 神经人声需要联网，服务不可用时不会用传统机器音顶替。
- 高自然度合成语音并不等于真人录音，不能用于冒充真人演员。
- 游戏更新、UI 变化或缩放设置改变可能需要重新框选。
- 外部伴侣方案能降低侵入性，但不能替用户判断任何游戏厂商的服务条款。

## 开发与验证

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m pytest --cov=genshin_autotts
.\scripts\smoke_test.ps1
```

项目结构：

```text
src/genshin_autotts/
├── capture.py   # 屏幕截图
├── ocr.py       # OCR 与观测源
├── text.py      # 文本规范化、稳定与去重
├── voice.py     # 固定角色音色档案
├── tts.py       # Edge 神经人声生成与失败重试
├── cache.py     # SQLite + LRU 音频缓存
├── pipeline.py  # 并发识别/播音流水线
└── ui.py        # Tkinter 桌面界面与区域框选
```

提交改动前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。安全问题请参考 [`SECURITY.md`](SECURITY.md)。

## 许可证

源代码使用 [MIT License](LICENSE)。许可证不授予任何第三方游戏内容、商标、角色、音频或模型的权利。

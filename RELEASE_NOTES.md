# Genshin_autoTTS v0.4.0

本版本将默认架构从“依赖真人录音包”升级为“本地识别与音色路由 + 云端开放平台合成 + 本地缓存播放”。

## 核心变化

- 新增火山引擎 HTTP TTS 提供商。
- 新增阿里云 NLS REST TTS 提供商。
- 默认不再要求导入真人录音包。
- 角色名和 OCR 均在本地处理；云端只接收稳定台词、音色 ID 与必要合成参数。
- 同一角色会复用持久化的固定音色，并支持 `speaker_voice_overrides` 手工覆盖。
- API 凭据通过 Windows DPAPI 为当前用户加密保存。
- 支持通过环境变量提供凭据，适合免落盘和自动化部署。
- 云端生成结果继续使用容量受限的本地缓存，减少延迟与重复计费。
- 保留严格真人录音包作为兼容模式。

## 云平台凭据

火山引擎需要：

- `App ID`
- `Access Token`

阿里云需要：

- `AppKey`
- `Access Token`

两者均可在桌面界面的“配置 API”窗口填写。也可使用：

- `GENSHIN_AUTOTTS_VOLCENGINE_APP_ID`
- `GENSHIN_AUTOTTS_VOLCENGINE_ACCESS_TOKEN`
- `GENSHIN_AUTOTTS_ALIYUN_APP_KEY`
- `GENSHIN_AUTOTTS_ALIYUN_ACCESS_TOKEN`

## 使用前请注意

- 云平台的开通、试用额度、计费、并发和音色授权由对应平台管理。
- 云端语音是合成语音，不是游戏官方原声，也不包含角色声音克隆。
- 阿里云 Access Token 可能过期，需要按平台要求更新。
- 当前安装包未使用商业代码签名证书，请只从本仓库 Release 下载并核对 SHA-256。
- 本项目仍是外部屏幕识别工具，不注入游戏进程、不读取游戏内存、不修改游戏文件。

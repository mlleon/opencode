---
name: transcribe-video
description: Extract transcript or subtitles from a local video file. Use this skill whenever the user asks to transcribe a video, extract speech-to-text, get subtitles, or wants a text version of what's said in a video. Also trigger on "提取字幕", "视频转文字", "语音转文字", "transcribe", "extract audio text", or when the user references getting a script/transcript from any video file (mp4, mkv, mov, avi, webm). This skill is for LOCAL video files — for YouTube or other online URLs, use the download-video skill first to get the file, then transcribe it.
---

# transcribe-video（字幕优先 + 转录 + Obsidian 笔记）

把本地视频/音频转成文本，并生成结构化 Obsidian 笔记。

## 推荐入口（从任意目录运行）

强烈建议使用 `skills/` 级共享 uv 工程固定依赖来源，以确保 `document-parser` 与 `transcribe-video` 复用同一个 Python runtime，并通过 dependency group 隔离各自依赖。

本 skill 使用：

- uv project：`$HOME/.config/opencode/skills`
- uv group：`transcribe-video`
- skill root：`$HOME/.config/opencode/skills/transcribe-video`
- Python 版本：`>=3.12`

```bash
# 一键：字幕优先（若存在）→ 否则 ASR → 输出 txt/json/md
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python "$HOME/.config/opencode/skills/transcribe-video/scripts/run.py" "<video_path>" zh-CN
```

### 仅转录（输出 txt/json，不生成 md）

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python "$HOME/.config/opencode/skills/transcribe-video/scripts/transcribe.py" "<video_path>" zh-CN
```

### 仅结构化（json → md）

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python "$HOME/.config/opencode/skills/transcribe-video/scripts/structure.py" "<name>/<name>.json"
```

## 行为说明（字幕优先策略）

优先策略：
1) **如果检测到内嵌字幕轨（subtitle stream）**，优先提取字幕（更快、更准）
2) 如果没有字幕轨或提取失败，再使用 NVIDIA NIM Whisper (whisper-large-v3) 做语音转文字（ASR）

默认语言：`zh-CN`。

### 手动查看字幕轨（可选排查）

```bash
ffprobe -v quiet -select_streams s -show_entries stream=index,codec_name:stream_tags=language,title -of json "<video_path>"
```

### 字幕轨选择（语言匹配）

当字幕轨有多个时，脚本会优先选择与 `language_code` 最匹配的字幕轨（常见写法映射）：

- `zh-CN`：优先 `zh / zho / chi / cmn`
- `en-US`：优先 `en / eng`

若语言信息缺失，会退化为选择最靠前的可导出文本字幕轨。

## 输出目录与产物

默认会在视频/音频同级目录下，以文件名（不含扩展名）创建一个文件夹，把输出文件放进去：

- `<name>/<name>.txt`
- `<name>/<name>.json`
- `<name>/<name>.md`
- `<name>/<name>.srt`（仅当检测到字幕轨且导出成功时）

## 环境准备（只需一次）

共享 runtime 已由 `skills/pyproject.toml` 管理，不再需要在 skill 目录单独维护 `pyproject.toml` 或 `uv.lock`。

首次运行如遇依赖解析问题，先检查 `skills/uv.lock` 是否最新，再重新执行对应 `uv run` 命令。

## API Key 配置

不要把真实 API Key 写进 skill 目录下的 `.env` 并分发/提交。

推荐放到 OpenCode keys 目录：`~/.config/opencode/keys/nvidia.key`：

```bash
nvapi-...
```

也支持写成：

```bash
NIM_API_KEY=nvapi-...
```

兼容：在家目录创建 `~/.transcribe_video.env`：

```bash
NIM_API_KEY=nvapi-...
```

## 常见语言码

`zh-CN`（中文）、`en-US`（英语）、`ja-JP`（日语）、`ko-KR`（韩语）、`fr-FR`（法语）、`de-DE`（德语）、`es-ES`（西语）。

## NIM Whisper limits（参考）

| Limit | Value |
|-------|-------|
| Audio file size (per request) | 25 MB |
| Default gRPC message size | 64 MB |
| Rate limit | 40 RPM (free tier) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gRPC error` | 检查 API key 是否有效；稍后重试 |
| Empty transcript | 尝试显式指定语言码（如 `zh-CN`） |
| Rate limit (429) | 稍等后重试；必要时降低频率 |

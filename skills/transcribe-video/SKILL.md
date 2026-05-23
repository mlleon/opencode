---
name: transcribe-video
description: Extract transcript or subtitles from a local video/audio file and archive it as traceable raw material in memory-source. Use this skill when the user asks to transcribe a local video, extract subtitles, convert speech to text, or prepare video/audio material for a knowledge base. This skill is for LOCAL media files only.
---

# transcribe-video（视频资料入库处理器）

把本地视频/音频转成可追溯、可校验、可领域化扩展的转录资料，并归档到项目级 `memory-source/raw/03-transcripts/`。

这个 skill 不是自动文章生成器。它的默认目标是：保留原文和时间戳，生成候选结构，进入 raw 资料层，后续再由人工或其他 workflow 做二次创作。

## Runtime 约定

- uv project：`$HOME/.config/opencode/skills`
- uv group：`transcribe-video`
- skill root：`$HOME/.config/opencode/skills/transcribe-video`
- Python 版本：`>=3.12`

## Agent 推荐入口

正常 `/transcribe-video` 调用时，Agent 应自动判断 `projectRoot`，不要要求用户手动进入 skill 目录。

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video run \
  --project-root "<project-root>" \
  --input "<video-or-audio-path>" \
  --language zh-CN \
  --structure-mode assisted \
  --taxonomy-review auto
```

如果没有可用 LLM，`assisted` 会自动降级为 `deterministic`，并在最终 Markdown frontmatter 中记录 `llm_used: false` 和错误原因。

## 标准流程

```text
dry-run
  ↓
transcribe       字幕优先；没有字幕则使用 NVIDIA NIM Whisper ASR
  ↓
normalize        生成规范化 transcript JSON/Markdown
  ↓
segment          切成可审查的时间块
  ↓
classify         基于 taxonomy 判断内容领域
  ↓
analyze          分析 secondaryHints / golden test 覆盖缺口，必要时生成 review 候选
  ↓
assist           可选：Kimi K2.6 生成 JSON 候选
  ↓
structure        脚本生成最终 Markdown
  ↓
postprocess      写入 memory-source
  ↓
validate         校验 raw/assets 终态
```

## memory-source 输出

最终 Markdown：

```text
memory-source/raw/03-transcripts/<finalStem>.md
```

支撑材料：

```text
memory-source/assets/raw/transcripts/<finalStem>/
├── transcript.txt
├── transcript.json
├── transcript.srt              # 如果存在字幕
├── transcript.normalized.json
├── segments.json
├── classification.json
├── analysis.json
└── assist.json
```

约束：

- `raw/03-transcripts/` 只放 Markdown
- JSON/TXT/SRT 等过程资料只进入 `assets/raw/transcripts/`
- 所有候选判断都必须带时间戳或原文证据
- 默认 `review_status: pending`

## 内容领域 taxonomy / harness

配置文件：

```text
skills/transcribe-video/config/content_taxonomy.json
```

当前采用 harness 化 taxonomy：一级分类稳定，二级标签由 `secondaryHints` 引导并允许在证据约束内开放生成。

一级分类：

- `culture_life_aesthetics`：东方文化与生活美学
- `general_reflection`：人生思考
- `ai_technology`：AI / IT / 技术
- `business_marketing`：商业 / 品牌 / 营销
- `data_analysis`：数据分析
- `knowledge_workflow`：知识管理 / 方法论 / 工作流
- `content_creation`：内容创作
- `generic`：通用素材

新增方向时优先补充 `secondaryHints` 和 golden test 候选，不要新增 Markdown 模板或 schema 字段。

当 `--taxonomy-review auto` 检测到高置信新二级方向时，会把候选写入：

```text
<projectRoot>/.cache/transcribe-video/<workId>/review/
├── analysis.json
├── taxonomy-candidates.json
├── golden-test-candidates.json
└── analysis-report.md
```

这些 review 产物不进入 `memory-source/raw/`。

## LLM 模型配置

配置文件：

```text
skills/transcribe-video/config/llm.json
```

当前质量优先配置：

- assisted：`nvidia / moonshotai/kimi-k2.6`
- premiumReview：`pqapi / gpt-5.5`（第一阶段不默认启用）
- fallback：`litellm / glm-5.1-xhigh`

LLM 只能输出通用 harness JSON 候选，不能直接写最终 Markdown。脚本会校验：

- primaryCategory 必须存在于 taxonomy
- secondaryCategories 必须符合格式约束
- evidence.text 必须来自原文
- start/end 时间戳必须合法
- blockId 必须存在
- reviewRequired 必须存在

## 常用命令

### dry-run

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video dry-run --project-root "<project-root>"
```

### 完整运行

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video run \
  --project-root "<project-root>" \
  --input "<video-or-audio-path>" \
  --language zh-CN \
  --structure-mode assisted \
  --taxonomy-review auto
```

### analyze 已有转录分块

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video analyze \
  --project-root "<project-root>" \
  --input-transcript "<segments.json>" \
  --output "<analysis.json>"
```

### validate

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video validate --project-root "<project-root>"
```

## 兼容旧入口

旧入口仍保留用于只转录到视频同级目录：

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python "$HOME/.config/opencode/skills/transcribe-video/scripts/run.py" "<video_path>" zh-CN
```

但进入 `memory-source` 的正式流程应使用 `python -m scripts.transcribe_video run`。

## API Key

NVIDIA NIM Whisper 和 Kimi K2.6 默认共用：

```text
~/.config/opencode/keys/nvidia.key
```

也支持环境变量：

```bash
NIM_API_KEY=nvapi-...
TRANSCRIBE_VIDEO_LLM_API_KEY=...
```

不要把真实 API Key 写进 skill 目录并提交。

## 常见语言码

`zh-CN`（中文）、`en-US`（英语）、`ja-JP`（日语）、`ko-KR`（韩语）、`fr-FR`（法语）、`de-DE`（德语）、`es-ES`（西语）。

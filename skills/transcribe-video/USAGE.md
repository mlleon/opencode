# transcribe-video 使用与维护文档

`transcribe-video` 是本地视频/音频资料入库处理器，用于把媒体文件转成可追溯、可校验、可长期维护的 transcript raw material，并写入项目级 `memory-source/raw/03-transcripts/`。

它不是自动文章生成器。它只负责：转录、标准化、分块、分类、受控结构化、生成最终 Markdown 和支撑材料。

---

## 1. 适用场景

适合使用 `transcribe-video` 的场景：

- 从本地视频/音频提取字幕或语音转文字
- 把转录结果归档到项目级 `memory-source/`
- 为视频资料生成可追溯的主题、观点、概念、摘录候选
- 处理东方文化、生活美学、AI、Agent、品牌营销、数据分析、IT 技术等多领域视频文稿
- 在后期资料越来越多时，通过 `analyze` 自动发现 taxonomy / golden test 覆盖缺口

不适合使用的场景：

- 直接生成公众号文章、品牌文案或文学化改写
- 对没有原文证据的观点做总结
- 让 LLM 直接写最终 Markdown
- 把过程 JSON/TXT/SRT 放入 `memory-source/raw/`
- 为每个新领域新增一套 Markdown 模板

---

## 2. 运行环境

统一使用 `skills/` 级共享 uv runtime：

```text
uv project：$HOME/.config/opencode/skills
uv group：transcribe-video
skill root：$HOME/.config/opencode/skills/transcribe-video
Python：>=3.12
```

正常命令格式：

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video <command> ...
```

---

## 3. 标准 pipeline

```text
dry-run
  ↓
transcribe       字幕优先；没有字幕时使用 NVIDIA NIM Whisper ASR
  ↓
normalize        生成规范化 transcript JSON/Markdown
  ↓
segment          切成稳定 blockId 的时间块
  ↓
classify         基于 taxonomy 做确定性一级分类初判
  ↓
analyze          检查 secondaryHints / golden test 覆盖缺口
  ↓
assist           可选：LLM 输出受控 harness JSON 候选
  ↓
structure        脚本渲染最终 Markdown
  ↓
postprocess      写入 memory-source 终态结构
  ↓
validate         校验 raw/assets 边界
```

原则：

- 脚本控制结构和落盘位置
- LLM 只理解内容并输出 JSON 候选
- 所有候选必须能追溯到原文 evidence
- 最终 Markdown 由 `structure.py` 渲染

---

## 4. 输出结构

最终 Markdown：

```text
memory-source/raw/03-transcripts/<finalStem>.md
```

支撑材料：

```text
memory-source/assets/raw/transcripts/<finalStem>/
├── transcript.txt
├── transcript.json
├── transcript.srt                  # 如果存在字幕
├── transcript.normalized.json
├── segments.json
├── classification.json
├── analysis.json
└── assist.json
```

项目级 staging：

```text
<projectRoot>/.cache/transcribe-video/<workId>/
├── raw/
├── normalized/
├── analysis/
├── structured/
└── review/                         # 只在需要人工/Agent review 时出现
```

`review/` 示例：

```text
review/
├── analysis.json
├── taxonomy-candidates.json
├── golden-test-candidates.json
└── analysis-report.md
```

`review/` 是流程候选产物，不进入 `memory-source/raw/`。

---

## 5. 命令总览

### 5.1 dry-run：检查项目结构

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video dry-run \
  --project-root "<project-root>"
```

检查：

- `memory-source/` 是否存在
- project root 是否有 `CLAUDE.md` 或 `AGENTS.md`
- `memory-source/` 是否有 `CLAUDE.md` 或 `AGENTS.md`
- `raw/` 和 `assets/` 是否存在
- transcript raw/assets 输出路径策略

### 5.2 run：完整转录入库

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video run \
  --project-root "<project-root>" \
  --input "<video-or-audio-path>" \
  --language zh-CN \
  --structure-mode assisted \
  --taxonomy-review auto
```

参数：

```text
--project-root      必填，目标项目根目录
--input             必填，本地视频/音频路径
--language          默认 zh-CN
--structure-mode    assisted 或 deterministic，默认 assisted
--taxonomy-review   off / auto / always，默认 auto
--final-stem        可选，覆盖最终 Markdown 文件名
```

`structure-mode`：

- `assisted`：调用 LLM 输出 harness JSON 候选；失败时自动降级 deterministic
- `deterministic`：完全脚本生成，质量较保守但稳定

`taxonomy-review`：

- `off`：不做 taxonomy/test 覆盖缺口分析
- `auto`：低风险自动继续；发现新二级方向时生成 review 产物
- `always`：总是执行 analyze，并在需要时生成 review 产物

### 5.3 analyze：分析已有 segments.json

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video analyze \
  --project-root "<project-root>" \
  --input-transcript "<segments.json>" \
  --output "<analysis.json>"
```

用途：

- 已经有转录分块文件时，单独分析是否需要新增 `secondaryHints`
- 检查某个样本是否适合成为 golden test
- 调试 taxonomy 覆盖情况

### 5.4 validate：校验 memory-source 终态

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video validate \
  --project-root "<project-root>"
```

校验重点：

- `raw/03-transcripts/` 只能包含 Markdown
- raw 中不能出现 JSON/TXT/SRT/音视频/图片/过程文件
- transcript Markdown 必须有 `source_type: transcript`
- `review_status` 必须是 `pending`
- `primary_domain` 必须合法
- Markdown 必须包含时间戳

---

## 6. harness taxonomy 维护原则

配置文件：

```text
skills/transcribe-video/config/content_taxonomy.json
```

当前结构：

```text
creatorProfile
primaryCategories
  ├── culture_life_aesthetics
  ├── general_reflection
  ├── ai_technology
  ├── business_marketing
  ├── data_analysis
  ├── knowledge_workflow
  ├── content_creation
  └── generic
```

一级分类必须稳定，后期不要频繁新增。

二级方向使用 `secondaryHints`：

```json
{
  "culture_life_aesthetics": {
    "secondaryHints": [
      "poetry",
      "su_dongpo",
      "tea_culture",
      "object_aesthetics",
      "ru_porcelain",
      "spiritual_space"
    ]
  }
}
```

维护原则：

- 新方向优先补 `secondaryHints`，不要新增一级分类
- 不要为新领域新增 Markdown 模板
- 不要为新领域新增 schema 字段
- 不要把一次性词汇立刻晋升为正式 hint
- 新 hint 最好有多个证据片段或多个样本支撑
- 高价值新增方向应补 golden test

---

## 7. 遇到新增领域时怎么处理

当 `analyze` 输出 `decision: stage_and_pause` 时，先看：

```text
<projectRoot>/.cache/transcribe-video/<workId>/review/analysis-report.md
<projectRoot>/.cache/transcribe-video/<workId>/review/taxonomy-candidates.json
<projectRoot>/.cache/transcribe-video/<workId>/review/golden-test-candidates.json
```

### 7.1 什么时候新增 secondaryHint

可以新增：

- transcript 中多处稳定出现同一主题
- 多个 transcript 重复出现同一主题
- 属于长期会处理的方向
- 现有 hint 无法表达该主题
- 有明确 evidence 支撑

不要新增：

- 只是一次性口头表达
- 和已有 hint 只是近义重复
- 只有模型猜测，没有原文证据
- 会导致一级分类边界变模糊

### 7.2 新增 hint 的格式

规则：

- 小写英文
- 使用下划线
- 不超过 48 个字符
- 不使用中文、空格或特殊符号

示例：

```text
context_engineering
agent_skill_design
brand_strategy
tea_room_design
song_lifestyle
```

### 7.3 新增 hint 的流程

推荐流程：

```text
1. 查看 review/taxonomy-candidates.json
2. 检查是否与已有 secondaryHints 重复
3. 确认 evidence 来自原文
4. 如确实长期有用，加入 content_taxonomy.json 对应 primaryCategory.secondaryHints
5. 为该方向补测试样本或断言
6. 运行 transcribe-video 测试
```

不要让 LLM 无审核直接修改正式 taxonomy。

---

## 8. golden test 维护原则

测试文件：

```text
skills/transcribe-video/tests/test_pipeline.py
skills/transcribe-video/tests/test_transcribe_video.py
```

当前测试风格：

- 使用 Python 标准库 `unittest`
- 测试数据优先内联 JSON
- 大样本才考虑放入 `tests/fixtures/`
- 外部转录/LLM 调用必须 mock 或使用 deterministic 路径

新增领域时优先补测试，而不是改模板。

测试应该验证：

- `primaryCategory` 是否合理
- `secondaryCategories` 是否包含关键 hint
- `topics/keyPoints/concepts` 是否有 evidence
- 非目标领域不会被误判到核心领域
- `analyze` 是否生成或不生成候选 hint

示例断言方向：

```text
苏东坡 / 诗词 / 心境      → culture_life_aesthetics + su_dongpo / poetry / spiritual_space
Agent Skill / context tax  → ai_technology + agent_skill_design / context_engineering
品牌定位 / 用户洞察         → business_marketing + brand_strategy / user_insight
SQL / 指标 / 看板           → data_analysis + sql / metrics / dashboard
```

---

## 9. LLM 结构化规则

配置文件：

```text
skills/transcribe-video/config/llm.json
skills/transcribe-video/config/llm_schema.json
```

默认模型：

```text
assisted       nvidia / moonshotai/kimi-k2.6
premiumReview  pqapi / gpt-5.5
fallback       litellm / glm-5.1-xhigh
```

LLM 只能输出 harness JSON，不能写最终 Markdown。

主要字段：

```text
titleCandidate
primaryCategory
secondaryCategories
contentType
confidence
keyPoints
concepts
quotes
actionableInsights
openQuestions
warnings
reviewRequired
```

所有重要候选必须带：

```json
{
  "text": "原文片段",
  "start": 0.0,
  "end": 12.5,
  "blockId": "b001"
}
```

如果模型输出不合法，流程会降级到 deterministic。

---

## 10. 统一 Markdown 模板

最终 Markdown 由 `scripts/structure.py` 渲染，统一结构：

```markdown
# 视频转录：标题

## 资料说明

## 分类结果

## 主题结构

## 关键观点

## 概念 / 术语

## 重要原文摘录

## 可行动洞察候选

## 待确认问题

## 原文转录

## 处理警告
```

不要为不同领域新增模板。不同领域的差异应进入：

```text
secondaryCategories
keyPoints
concepts
quotes
actionableInsights
```

---

## 11. 验证命令

### 11.1 transcribe-video 测试

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m unittest discover -s tests -p 'test_*.py'
```

### 11.2 document-parser 回归

因为两个 skill 共用 `skills/` 级 uv runtime，修改依赖或共享配置后应回归：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser -- \
  python -m unittest discover -s tests -p 'test_*.py'
```

### 11.3 uv lock

```bash
uv lock --check
```

### 11.4 CLI smoke

至少验证：

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video dry-run --project-root "<project-root>"

uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video validate --project-root "<project-root>"

uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video analyze \
  --project-root "<project-root>" \
  --input-transcript "<segments.json>" \
  --output "<analysis.json>"
```

---

## 12. 常见问题

### 12.1 `analyze` 发现新 hint，是否直接加入 taxonomy？

不要直接加入。先检查候选是否有足够证据、是否与已有 hint 重复、是否是长期方向。

### 12.2 新领域是否要新增一级分类？

通常不要。优先放进已有一级分类的 `secondaryHints`。

只有当一个方向长期稳定、跨大量资料、且无法归入现有一级分类时，才考虑新增一级分类。

### 12.3 是否要为新领域新增 Markdown 模板？

不要。统一模板是降低维护成本的关键。

### 12.4 LLM 能不能写最终 Markdown？

不能。LLM 只能输出 JSON 候选，最终 Markdown 必须由脚本渲染。

### 12.5 review 产物能不能进入 raw？

不能。`raw/03-transcripts/` 只放最终 Markdown。

### 12.6 为什么 `raw` 中默认 `review_status: pending`？

因为 transcript raw material 仍需人工或后续 workflow 复核，尤其是诗词出处、文化判断、技术概念和行动建议。

---

## 13. 维护底线

新增方向时遵循这个顺序：

```text
先看 analyze review
  ↓
确认 evidence
  ↓
必要时补 secondaryHints
  ↓
补测试样本或断言
  ↓
运行测试
```

不要走这个方向：

```text
新增领域
  ↓
改 schema
  ↓
改 prompt 分支
  ↓
改 Markdown 模板
  ↓
改后处理逻辑
```

长期维护目标是：

```text
代码结构稳定
schema 稳定
Markdown 模板稳定
一级分类稳定
secondaryHints 渐进扩展
测试样本持续补充
```

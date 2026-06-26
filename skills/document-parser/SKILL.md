---
name: document-parser
description: |
  通用文档解析服务（多后端）。当用户需要解析 PDF/Word/PPT/图片文件，并希望提取文字、结构化内容、Markdown/JSON 输出时使用。

  默认使用 MinerU v4 精准解析；仅当 MinerU 明确命中“额度/限流”类错误时，才会对 PDF/图片自动回退 PaddleOCR Jobs API（降级 OCR-only 输出，并在结果中标注 warnings）。如果需要禁用 fallback provider，必须在 `parse` 子命令里显式 opt-in `--no-fallback`；它不会改变默认路线，也不同于只控制 postprocess 的 `--parse-only`。

  触发场景：
  - “帮我解析这个 PDF/Word/PPT/图片”
  - “把这份扫描件 OCR 出文字”
  - “把文档转成 Markdown/JSON”
  - 用户上传文档并要求提取、识别、转换
---

# document-parser（Agent 执行版）

这个 skill 面向 OpenCode Agent 的 `/document-parser` 斜杠命令使用场景。

用户通常会在某个项目根目录里直接调用 `/document-parser`，Agent 需要自己判断项目路径、选择 source-kind、调用解析流程、整理 staging、最后校验终态。

## 1. 你要做什么

当用户要求解析一个文档时，Agent 先判断当前项目是否允许写 `memory-source/raw`、`memory-source/assets` 或 `memory-source/wiki`。

- 通用默认工作流仍然可用：确认 `projectRoot`，判断 `sourceKind`，先做 `dry-run`，再做 `parse`，需要终态落库时再做 `postprocess` 和 `validate`。
- 但在 culture-system 或任何明确禁止 raw/assets/wiki 写入的项目里，默认 containment 路线应改为：`dry-run`，`parse`，按需加 `--page-range` 与核心解析参数，并显式使用 `--parse-only` 或 `--no-postprocess`。
- 如果这类受限项目仍需要把结果落到本地证据目录，只能额外显式运行 `postprocess --output-profile evidence-local --output-root .omo/evidence/...`。
- `legacy-memory` postprocess 仍是通用 CLI 的兼容默认行为，但在 culture-system 里不是默认安全路线，只有项目规则或单独计划明确授权时才能执行。

目标不是让用户手动跑 CLI，而是让 Agent 自动完成正确的那条流程。

## 2. 项目根目录判断

### 优先级

1. 用户显式给出的项目路径
2. 当前工作目录
3. 当前工作目录的合理父级路径

### 识别规则

如果目录同时满足这些条件，优先视为项目根目录：

- 存在 `memory-source/`
- 存在 `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md`
- 存在 `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md`
- 存在 `memory-source/raw/`
- 存在 `memory-source/assets/`

说明：

- `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 是项目级 Agent 说明，用于确认这个目录是目标工程。
- `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 是 memory-source 子系统说明，用于约束 raw/assets/图片引用等知识库维护规则。
- 两者不是备份关系，而是父项目规则与子系统规则的关系。

如果项目根目录不明确，先尝试从上下文推断；只有在确实无法确认时才询问用户。

## 3. source-kind 选择

可选值：

- `book`：书籍、教材、长篇专著
- `article`：文章、普通文档、报告
- `paper`：论文、学术文献
- `web`：网页、在线文章、博客

选择原则：

- 用户明确说明时，直接采用用户指定值
- 未明确时，根据文件名、内容和项目语境判断
- 仍无法判断时，优先询问一次，而不是盲猜

## 4. 推荐执行方式

### 4.1 Runtime 约定

本 skill 是本地 Python CLI skill，优先使用 `skills/` 级 uv 工程运行：

- uv project：`$HOME/.config/opencode/skills`
- uv group：`document-parser`
- workdir：`$HOME/.config/opencode/skills/document-parser`
- Python 版本：`>=3.12`

注意：`skills/pyproject.toml` 只服务需要本地依赖的 CLI 型 skill；纯提示词、纯文档或纯 Agent workflow skill 不需要接入 uv。

### 4.2 Agent 推荐入口

不要要求用户切到 skill 目录后再手动跑命令。Agent 应在工具调用时把 `workdir` 设置为 skill 目录，然后通过共享 uv project 和本 skill 的 dependency group 执行：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run --project-root "<project-root>"
```

工具调用建议：

```text
workdir = $HOME/.config/opencode/skills/document-parser
command = uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser ...
```

如果 `uv` 不可用，才允许临时回退到系统 `python3`；回退时必须在最终回复中说明原因，并显式设置 `PYTHONPATH`：

```bash
SKILL_DIR="$HOME/.config/opencode/skills/document-parser"
PYTHONPATH="$SKILL_DIR" python3 -m scripts.document_parser dry-run --project-root "<project-root>"
```

手动进入 skill 目录只用于调试，不是正常使用方式。

## 5. 标准工作流

### 5.1 dry-run

先检查项目结构与路径策略：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root "<project-root>"
```

dry-run 只检查：

- `memory-source/` 是否存在
- `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 是否存在
- `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 是否存在
- `memory-source/raw/` 是否存在
- `memory-source/assets/` 是否存在
- staging 是否不在 `memory-source/` 内

### 5.2 parse

解析到项目级 staging：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root "<project-root>" \
  --input "<input-file-or-url>" \
  [--page-range "2,4-6"] \
  [--model-version "<model-version>"] \
  [--language "zh"] \
  [--is-ocr false] \
  [--enable-table true] \
  [--enable-formula true] \
  [--parse-only]
```

parse 的输出写入：

```text
<project-root>/.cache/document-parser/
```

然后由后端在其下生成 `document_parser_output/<backend-stem>/`。

bounded parse 约定：

- `--page-range` 支持 `N`、`N-M`、逗号分隔片段，如 `2,4-6`
- 语义为 1-based、闭区间，本地 PDF 会先做页数预检并拒绝越界范围
- 本地非 PDF 输入不接受 `--page-range`
- URL 输入保留 `--page-range`，但跳过本地 PDF 预检
- `--parse-only` 是规范写法，`--no-postprocess` 是同语义别名，二者都只控制 parse 后是否继续进入 postprocess，不改变 parse 仍然只写 staging 这一事实，也不改变 provider fallback 策略
- 默认不加 `--no-fallback` 时，quota-like MinerU 错误在 PaddleOCR 支持的 PDF 或图片上仍保持兼容回退行为
- `--no-fallback` 只能显式 opt-in 使用；它会禁用 fallback providers，在原本可回退的 MinerU 配额或限流类错误上 fail closed
- 如果 provider 返回页数超限错误，Agent 应保留结构化错误并根据 `suggestedPageRange` 重试，不要自动拆分 PDF，也不要把这类错误转成 PaddleOCR 回退

### 5.3 postprocess

通用默认 CLI 路线下，`postprocess` 会按兼容方式把 staging 整理成最终 `memory-source/` 结构。当前默认 profile 仍是 `legacy-memory`：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root "<project-root>" \
  --source-kind "<book|article|paper|web>" \
  --staging-doc-root "<staging-doc-root>" \
  [--output-profile legacy-memory]
```

如果用户只有原始输入文件，也可以用 `--input` 模式，但前提是 staging 已经存在并能由输入内容定位到对应目录。

### 5.4 culture-system containment 路线

当项目规则禁止 raw/assets/wiki 写入时，不要把 `postprocess` 当成 parse 后的默认下一步。优先使用：

1. `dry-run`
2. `parse --page-range ... --parse-only`，或在相同语义下使用 `--no-postprocess`；如果任务像 R021 一样对 source-sensitive OCR 有要求，需要证明没有走回退 provider，则改用 `parse --page-range ... --parse-only --no-fallback`
3. 只有确实需要把解析结果写到项目内证据目录时，才显式运行：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root "<project-root>" \
  --source-kind "<book|article|paper|web>" \
  --staging-doc-root "<staging-doc-root>" \
  --output-profile evidence-local \
  --output-root ".omo/evidence/<run-dir>"
```

这条 containment 路线的约束：

- `evidence-local` 只允许写入项目内 `.omo/evidence/**`
- 输出只包含 `normalized/document.md`、`normalized/document.json`、`normalized/images.manifest.json`
- 不复制图片或 PDF 二进制
- 如果没有单独授权，不要在 culture-system 里执行 `legacy-memory` postprocess
- `--parse-only` / `--no-postprocess` 只控制是否继续 `postprocess`，不等于禁用 provider 回退
- `--no-fallback` 是显式 opt-in 的 fail-closed provider 开关，不是默认 parse 路线
- 这次 no-fallback amendment 只补齐工具能力，不代表 R021 页发现成功，也不代表 source-lock、ingest、wiki 或下游流程已准备好
- `LIVE_SMOKE_MISSING_NORMALIZED_OUTPUTS` 仍是单独未解决的 blocker；这里的 no-fallback 文档更新不能被解释成 live-smoke 成功

### 5.5 validate

最后做终态校验：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root "<project-root>"
```

## 6. 输出约束

### 6.1 staging

解析过程工件放在：

```text
<project-root>/.cache/document-parser/
```

不要把 staging 当成最终知识库内容。

### 6.2 终态 raw / assets

只有在显式选择 `legacy-memory` profile，并且项目规则允许写终态知识资产时，内容才应进入 `memory-source/`。

常见映射：

- `book` -> `raw/04-books/` + `assets/raw/books/`
- `article` -> `raw/01-articles/` + `assets/raw/articles/`
- `paper` -> `raw/02-papers/` + `assets/raw/papers/`
- `web` -> `raw/07-web/` + `assets/raw/web/`

这些映射描述的是通用 CLI 兼容行为，不是 culture-system 当前上下文里的默认安全落点。

### 6.3 evidence-local

在受限项目里，如果需要把 parse 结果整理成可复核证据，应使用 `postprocess --output-profile evidence-local --output-root .omo/evidence/...`。

该 profile 只写：

- `normalized/document.md`
- `normalized/document.json`
- `normalized/images.manifest.json`

不要把 `evidence-local` 输出解释成 ingest 完成、wiki 写入许可或后续创作流程激活。

### 6.4 图片引用

终态 Markdown 中的图片引用必须使用 Obsidian embed：

```markdown
![[assets/raw/<bucket>/<finalStem>/<fileName>]]
```

不要保留标准 Markdown 图片语法，也不要保留 HTML `<img>`。

## 7. 安全与质量约束

- `raw/` 必须保持纯度，不能混入图片、PDF、zip、jsonl、pyc、tmp 等过程文件
- `raw/05-images/` 只允许 Markdown 清单文件
- 只有在执行 `legacy-memory` 终态路线时，`validate` 才是最终交付前的必经步骤
- 在 culture-system 或其他受限项目里，若规则禁止 raw/assets/wiki 写入，默认使用 `--parse-only` 或 `--no-postprocess`，只在需要证据落地时额外使用 `evidence-local`
- 如果任务像 R021 一样需要 source-sensitive OCR 证据，必须显式 opt-in `--no-fallback`；不要把 `--parse-only` 误当成禁用回退 provider 的开关
- MinerU token 只从 `~/.config/opencode/keys/mineru.key` 读取；`MINERU_TOKEN` 环境变量不是 MinerU 凭据来源
- 记录执行证据时只能保留 token 存在性或已脱敏状态，不能回显或落盘真实凭据值
- 当前 PaddleOCR 边界仍然只是 Jobs API 回退，`/ocr` service adapter 属于 future boundary，不要把它写成当前可用流程
- 发现路径不明确时，先推断再验证，只有必要时才问用户
- 不要建议用户手动进入 skill 目录执行 CLI，正常入口是 `/document-parser`

## 8. 什么时候不应该触发

- 用户在问代码怎么写，不是在解析文档
- 用户要写新文档模板，不是在处理已有文档
- 用户只是想解释文本含义，不是在做文档解析

## 9. 常见失败处理

- token 缺失：MinerU 检查 `~/.config/opencode/keys/mineru.key`；PaddleOCR 检查 `PADDLEOCR_TOKEN` 或 `~/.config/opencode/keys/paddleocr.key`
- `projectRoot` 不存在：重新确认项目路径
- `memory-source/` 不完整：先补齐项目结构
- `stagingDocRoot` 不存在：先确认 `parse` 是否成功执行
- MinerU 页数超限：保留结构化错误，参考 `suggestedPageRange` 改用 bounded parse；不要自动拆分 PDF，也不要把 `-60006` 转成 PaddleOCR 回退
- `validate` 失败：先看错误码，再修正 raw/assets 结构

## 10. 最小原则

Agent 的默认目标是：

> 在用户给定的项目上下文里，自动选择安全的解析路线，必要时完成整理和校验，但不把 CLI 使用负担转给用户，也不越过项目写入边界。

---
name: document-parser
description: |
  通用文档解析服务（多后端）。当用户需要解析 PDF/Word/PPT/图片文件，并希望提取文字、结构化内容、Markdown/JSON 输出时使用。

  默认使用 MinerU v4 精准解析；仅当 MinerU 明确命中“额度/限流”类错误时，才会对 PDF/图片自动回退 PaddleOCR Jobs API（降级 OCR-only 输出，并在结果中标注 warnings）。

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

当用户要求解析一个文档时，Agent 应按下面顺序执行：

1. 确认当前项目根目录 `projectRoot`
2. 判断输入类型与 `sourceKind`
3. 先做 `dry-run`
4. 再做 `parse`
5. 再做 `postprocess`
6. 最后做 `validate`

目标不是让用户手动跑 CLI，而是让 Agent 自动完成整条流程。

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

### Agent 推荐入口

不要要求用户切到 skill 目录后再手动跑命令。Agent 应在工具调用时把 `workdir` 设置为 skill 目录，然后用模块方式执行：

```bash
python3 -m scripts.document_parser dry-run --project-root "<project-root>"
```

工具调用建议：

```text
workdir = $HOME/.config/opencode/skills/document-parser
command = python3 -m scripts.document_parser ...
```

如果确实需要从任意 shell 目录直接执行，则显式设置 `PYTHONPATH`：

```bash
SKILL_DIR="$HOME/.config/opencode/skills/document-parser"
PYTHONPATH="$SKILL_DIR" python3 -m scripts.document_parser dry-run --project-root "<project-root>"
```

手动进入 skill 目录只用于调试，不是正常使用方式。

## 5. 标准工作流

### 5.1 dry-run

先检查项目结构与路径策略：

```bash
python3 -m scripts.document_parser dry-run \
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
python3 -m scripts.document_parser parse \
  --project-root "<project-root>" \
  --input "<input-file-or-url>"
```

parse 的输出写入：

```text
<project-root>/.cache/document-parser/
```

然后由后端在其下生成 `document_parser_output/<backend-stem>/`。

### 5.3 postprocess

把 staging 整理成最终 `memory-source/` 结构：

```bash
python3 -m scripts.document_parser postprocess \
  --project-root "<project-root>" \
  --source-kind "<book|article|paper|web>" \
  --staging-doc-root "<staging-doc-root>"
```

如果用户只有原始输入文件，也可以用 `--input` 模式，但前提是 staging 已经存在并能由输入内容定位到对应目录。

### 5.4 validate

最后做终态校验：

```bash
python3 -m scripts.document_parser validate \
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

终态内容只应进入 `memory-source/`。

常见映射：

- `book` -> `raw/04-books/` + `assets/raw/books/`
- `article` -> `raw/01-articles/` + `assets/raw/articles/`
- `paper` -> `raw/02-papers/` + `assets/raw/papers/`
- `web` -> `raw/07-web/` + `assets/raw/web/`

### 6.3 图片引用

终态 Markdown 中的图片引用必须使用 Obsidian embed：

```markdown
![[assets/raw/<bucket>/<finalStem>/<fileName>]]
```

不要保留标准 Markdown 图片语法，也不要保留 HTML `<img>`。

## 7. 安全与质量约束

- `raw/` 必须保持纯度，不能混入图片、PDF、zip、jsonl、pyc、tmp 等过程文件
- `raw/05-images/` 只允许 Markdown 清单文件
- `validate` 必须在最终交付前执行
- 发现路径不明确时，先推断再验证，只有必要时才问用户
- 不要建议用户手动进入 skill 目录执行 CLI，正常入口是 `/document-parser`

## 8. 什么时候不应该触发

- 用户在问代码怎么写，不是在解析文档
- 用户要写新文档模板，不是在处理已有文档
- 用户只是想解释文本含义，不是在做文档解析

## 9. 常见失败处理

- token 缺失：检查 `MINERU_TOKEN` / `PADDLEOCR_TOKEN` 或 `~/.config/opencode/keys/*.key`
- `projectRoot` 不存在：重新确认项目路径
- `memory-source/` 不完整：先补齐项目结构
- `stagingDocRoot` 不存在：先确认 `parse` 是否成功执行
- `validate` 失败：先看错误码，再修正 raw/assets 结构

## 10. 最小原则

Agent 的默认目标是：

> 在用户给定的项目上下文里，自动完成解析、整理和校验，不把 CLI 使用负担转给用户。

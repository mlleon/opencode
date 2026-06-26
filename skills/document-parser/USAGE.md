# document-parser 使用文档

`document-parser` 是一个通用文档解析 skill，用于把 PDF、Word、PPT、图片、扫描件或 URL 内容解析成规范化 Markdown / JSON，并把结果整理成可离线复现、可校验、可追溯的文档资产。

## 1. 适用场景

适合使用 `document-parser` 的场景：

- 解析 PDF、Word、PPT、图片或扫描件
- 把文档转换成 Markdown / JSON
- 对扫描件做 OCR 并保留原始解析工件
- 在允许写终态知识资产的通用项目里，把解析结果整理到项目级 `memory-source/` 结构中
- 在 culture-system 这类受限项目里，只做 bounded parse、staging 解析或 `.omo/evidence/**` 本地证据落地
- 在写入最终知识库前校验 `raw/` 和图片引用是否符合约束

不适合使用 `document-parser` 的场景：

- 解释代码或报错
- 写简历、合同、文章等新内容
- 对已经解析好的 Markdown 做纯内容创作
- 纯问答或总结任务

## 2. 支持的输入与后端

### 2.1 输入来源

- 本地文件路径
- URL

旧式批量接口支持多个输入，但本地文件和 URL 不能混用。

### 2.2 主后端：MinerU v4

默认优先使用 MinerU v4 解析。MinerU 负责精准文档解析，并输出规范化 Markdown、JSON、图片和原始工件。

### 2.3 回退后端：PaddleOCR Jobs API

PaddleOCR 只作为保守回退方案使用。

默认 parse 路线保持兼容行为，不加 `--no-fallback` 时，quota-like MinerU 错误在 PaddleOCR 支持的 PDF 或图片上仍可能自动回退到 PaddleOCR。

触发条件：

- MinerU 明确命中配额或限流类错误
- 输入类型是 PaddleOCR 支持的 PDF 或图片

PaddleOCR 支持的后缀：

- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`
- `.bmp`
- `.tiff`
- `.tif`

PaddleOCR 回退结果会在 JSON 中记录 `DEGRADED_OCR_FALLBACK` warning。

只有在 `parse` 子命令里显式 opt-in `--no-fallback` 时，才会禁用 fallback providers；这会让原本可回退的 MinerU 配额或限流类错误 fail closed。`--parse-only` 与 `--no-postprocess` 不控制 provider fallback，它们只控制 parse 之后是否继续走 postprocess。

### 2.4 future boundary：PaddleOCR `/ocr` service adapter

当前实现只有 PaddleOCR Jobs API 回退。

`/ocr` service adapter 仍然属于 future boundary，本版 skill 不把它当成当前可调用路径，也不会把 MinerU 页数超限错误自动改走 `/ocr`。

## 3. 凭据配置

### 3.1 MinerU 本地 key 文件

MinerU token 只从本地 key 文件读取：

```text
~/.config/opencode/keys/mineru.key
```

`MINERU_TOKEN` 环境变量不会被 document-parser 用作 MinerU 凭据来源。

### 3.2 PaddleOCR 环境变量

PaddleOCR token 可以通过环境变量提供：

```bash
export PADDLEOCR_TOKEN="你的 PaddleOCR token"
```

### 3.3 本地 key 文件

PaddleOCR 也可以写入本地 key 文件：

```text
~/.config/opencode/keys/paddleocr.key
```

### 3.4 读取优先级

MinerU 读取规则：

1. `~/.config/opencode/keys/mineru.key`
2. 文件不存在或为空时报错

PaddleOCR 读取顺序为：

1. `PADDLEOCR_TOKEN` 环境变量
2. `~/.config/opencode/keys/paddleocr.key`
3. 都不存在时报错

### 3.5 凭据脱敏规则

- 可以记录“凭据已配置”这一事实
- 不要在 stdout、stderr、evidence、截图或提交内容里回显真实 token
- 如果需要排查环境，只记录来源，例如“MinerU 来自本地 key 文件”或“PaddleOCR 来自环境变量”，不要记录值

## 4. 输出结构

基础解析输出统一位于：

```text
<output-dir>/document_parser_output/<stem>/
```

标准结构：

```text
document_parser_output/<stem>/
├── normalized/
│   ├── document.md
│   ├── document.json
│   └── images/
└── raw/
    ├── mineru/
    └── paddleocr/
```

目录说明：

- `normalized/document.md`：规范化 Markdown
- `normalized/document.json`：规范化 JSON envelope
- `normalized/images/`：本地化图片
- `raw/mineru/`：MinerU 原始工件
- `raw/paddleocr/`：PaddleOCR 原始工件

规范化 Markdown 不允许保留远程图片链接，图片必须本地化。

### 4.1 `parse` 子命令的项目级 staging

`parse --project-root ...` 会把 staging 根目录固定到：

```text
<project-root>/.cache/document-parser/
```

然后由后端在其下生成：

```text
<project-root>/.cache/document-parser/document_parser_output/<backend-stem>/
```

这一步只写 staging，不直接写 `memory-source/`。

### 4.2 `evidence-local` 输出 profile

当 `postprocess --output-profile evidence-local` 被显式选择时，输出根必须位于项目内 `.omo/evidence/**`，并固定产出：

```text
<project-root>/.omo/evidence/<run-dir>/
└── normalized/
    ├── document.md
    ├── document.json
    └── images.manifest.json
```

这个 profile 不复制图片或 PDF 二进制，也不代表获得了 ingest、wiki 写入或稳定 memory 更新许可。

## 5. 命令总览

正常使用由 Agent 调用 `/document-parser` 完成，用户不需要把手工 CLI 当成日常入口。下面的命令只用于 Agent 执行参考或本地调试时核对参数。

当前 CLI 支持 5 类入口，并通过 `skills/` 级共享 uv project 加载 `document-parser` dependency group：

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser <inputs...> [--output-dir <dir>]
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser parse --project-root <project> --input <file-or-url> [--page-range <range>] [--model-version <value>] [--language <code>] [--is-ocr <true|false>] [--enable-table <true|false>] [--enable-formula <true|false>] [--parse-only | --no-postprocess] [--no-fallback]
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser dry-run --project-root <project>
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser postprocess --project-root <project> --source-kind <kind> (--input <file> | --staging-doc-root <dir>) [--sha12 <sha12>] [--output-profile <legacy-memory|evidence-local>] [--output-root <project-relative-.omo/evidence/...>]
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser validate --project-root <project>
```

运行环境约定：

- uv project：`$HOME/.config/opencode/skills`
- uv group：`document-parser`
- workdir：`$HOME/.config/opencode/skills/document-parser`
- Python 版本：`>=3.12`

如果 `uv` 不可用，才临时回退到系统 `python3`，并显式设置 `PYTHONPATH`；正常 `/document-parser` 调用由 Agent 自动执行，不要求用户手动操作 CLI。

对 culture-system 一类受限项目，命令总览还要额外记住两条：

- `legacy-memory` 仍是通用 CLI 的兼容默认行为，但不是该项目里的默认安全路线
- 当项目规则禁止 raw/assets/wiki 写入时，优先使用 `parse --page-range ... --parse-only`，只有需要本地证据时才显式加 `postprocess --output-profile evidence-local --output-root .omo/evidence/...`
- `--no-fallback` 不是默认 parse 路线，只有在需要 fail-closed provider 证明时才显式加上
- 对 R021 一类 source-sensitive OCR，如果目标是证明没有走 PaddleOCR 回退，应使用 `parse --page-range ... --parse-only --no-fallback`
- 这条 no-fallback amendment 只代表工具能力补齐，不代表 R021 页发现成功，也不代表 source-lock、ingest、wiki 或下游 readiness
- `LIVE_SMOKE_MISSING_NORMALIZED_OUTPUTS` 仍是单独未解决的 live-smoke blocker，不要把本次文档更新当成 live-smoke 修复

## 6. 旧式批量解析模式

未指定子命令时，会进入兼容旧接口的批量解析模式。

### 6.1 解析一个本地文件

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser /path/to/file.pdf
```

### 6.2 解析多个本地文件

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser /path/to/a.pdf /path/to/b.pdf
```

### 6.3 指定输出目录

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser /path/to/file.pdf --output-dir /path/to/output
```

### 6.4 规则

- 不传 `--output-dir` 时，输出根目录为当前工作目录
- URL 与本地文件不能混用
- 成功时 stdout 会打印每个结果的 `normalized/document.md` 路径

## 7. `parse`：解析到项目级 staging

`parse` 用于把输入解析到项目级 staging 目录，不直接写入 `memory-source/`。

### 7.1 参数

```text
--project-root    必填，目标项目根目录
--input           必填，本地文件路径或 URL
--page-range      可选，bounded parse 范围，支持 N、N-M、2,4-6
--model-version   可选，透传给 MinerU v4 的模型版本参数
--language        可选，透传给 MinerU v4 的语言参数
--is-ocr          可选，布尔值，控制 OCR 行为
--enable-table    可选，布尔值，控制表格抽取
--enable-formula  可选，布尔值，控制公式抽取
--parse-only      可选，parse-only 规范写法
--no-postprocess  可选，与 --parse-only 同语义的别名，只能二选一
--no-fallback     可选，显式 opt-in 禁用 fallback providers，遇到原本可回退的 MinerU 配额或限流类错误时 fail closed
```

虽然 argparse 层没有把参数声明为 required，但运行时会强制校验，缺少参数会返回错误。

### 7.2 `--page-range` 规则

- 支持 `N`、`N-M`、逗号分隔片段，如 `2,4-6`
- 语义为 1-based、闭区间，内部会标准化为升序、去重后的页段
- 会拒绝 `0`、负数、空片段、反向区间、非整数和本地 PDF 越界范围
- 本地非 PDF 输入不接受 `--page-range`
- URL 输入保留 `--page-range`，但跳过本地 PDF 预检
- 本地 PDF 预检会记录页数元数据，但在未显式传入 `--page-range` 时，不会只因为 PDF 总页数很大就阻止 provider 调用

### 7.3 示例

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/book.pdf \
  --page-range 12-20
```

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/book.pdf \
  --page-range 2,4-6 \
  --model-version mineru-v4 \
  --language zh \
  --is-ocr false \
  --enable-table true \
  --enable-formula true \
  --parse-only
```

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input https://example.com/sample.pdf \
  --page-range 1-3 \
  --no-postprocess
```

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/source-sensitive.pdf \
  --page-range 1-1 \
  --parse-only \
  --no-fallback
```

### 7.4 `--parse-only` / `--no-postprocess` / `--no-fallback` 语义

- `--parse-only` 是规范写法
- `--no-postprocess` 是同语义别名，主要用于强调“这次 parse 结束后不要继续走 postprocess”
- 二者只能二选一，且只允许出现在 `parse` 子命令上
- `postprocess` 子命令如果收到这两个参数，会直接报参数错误
- 无论是否传入它们，`parse` 本身都只写 staging；它们表达的是调用方的流程意图和 containment 边界
- `--no-fallback` 是独立的 provider policy 开关，只能显式 opt-in 使用，默认不启用
- 不加 `--no-fallback` 时，quota-like MinerU 错误在 PaddleOCR 支持的 PDF 或图片上仍可能自动回退到 PaddleOCR，并记录 `DEGRADED_OCR_FALLBACK`
- 加上 `--no-fallback` 时，同类 fallback-eligible MinerU 错误会 fail closed，不会调用 PaddleOCR
- MinerU 页数超限错误保持结构化失败，不会因为这些参数而改走 PaddleOCR
- 对 culture-system 或 R021 一类 source-sensitive OCR，如果既要 containment 又要证明没有走回退 provider，应使用 `--parse-only --no-fallback`
- 这不代表 R021 页发现成功，也不代表 source-lock、ingest、wiki 或 live-smoke 已就绪；`LIVE_SMOKE_MISSING_NORMALIZED_OUTPUTS` 仍是单独未解决的 blocker

### 7.5 输出位置

```text
<project-root>/.cache/document-parser/document_parser_output/<backend-stem>/
```

`<backend-stem>` 由具体解析后端根据输入名称或 URL 生成。当前 `parse` 会把项目级 staging 根目录固定为：

```text
<project-root>/.cache/document-parser/
```

然后由 MinerU 或 PaddleOCR 在该目录下创建 `document_parser_output/<backend-stem>/`。

### 7.6 成功输出

成功时 stdout 打印 `normalized/document.md` 路径。

### 7.7 结构化页数超限指引

当 MinerU 返回页数超限错误时，当前实现会把它归类成稳定的结构化错误，而不是自动重试或自动拆分 PDF。

典型信号：

- provider 错误码 `-60006`
- 明确表达页数超限的 provider 错误消息

结构化错误会包含这类字段：

- `errorCode`
- `provider`
- `pdfPageCount`，本地 PDF 预检可用时
- `requestedPageRange`
- `suggestedPageRange`
- `retryHint`

处理原则：

- 根据 `suggestedPageRange` 改成 bounded parse
- 不自动拆分 PDF
- 不自动 provider retry
- 不因为 `-60006` 自动回退到 PaddleOCR

### 7.8 失败返回码

- `1`：解析后端失败
- `2`：参数错误，例如缺少 `--project-root` 或 `--input`
- `3`：路径或项目根目录错误

## 8. `dry-run`：检查项目路径策略

`dry-run` 不调用解析后端，也不写入文件，只检查项目结构和路径策略。

### 8.1 参数

```text
--project-root  必填，目标项目根目录
```

### 8.2 示例

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system
```

### 8.3 校验内容

- `projectRoot` 存在
- `memory-source/` 存在
- `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 存在
- `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 存在
- `memory-source/raw` 存在
- `memory-source/assets` 存在
- staging 目录不在 `memory-source/` 内

### 8.4 成功输出

成功时 stdout 只输出一行 JSON：

```json
{"projectRoot":"...","vaultRoot":"...","stagingRoot":"...","rawRoot":"...","assetsRoot":"...","manifestRoot":"...","policy":{"projectRootRequired":true,"stagingOutsideVault":true,"rawNoBinaries":true,"imageLinkStyle":"obsidian-embed"}}
```

失败时 stdout 为空，错误写入 stderr，并以 `ERROR:` 开头。

## 9. `postprocess`：整理 staging 到终态结构

`postprocess` 用于把 staging 中的 `normalized/document.md`、`document.json` 和图片整理成显式选择的输出 profile。

当前通用 CLI 默认 profile 仍是 `legacy-memory`，也就是兼容旧行为的 `memory-source/` 终态路线。对 culture-system 这类禁止 raw/assets/wiki 写入的项目，不应把它当成默认安全路线；那类项目应优先停在 `parse --parse-only`，或显式改用 `evidence-local`。

### 9.1 参数

```text
--project-root       必填，目标项目根目录
--source-kind        必填，内容类型
--input              与 --staging-doc-root 二选一，本地输入文件
--staging-doc-root   与 --input 二选一，已有 staging 文档目录
--sha12              可选，仅用于 --staging-doc-root 模式，必须是 12 位小写十六进制
--output-profile     可选，`legacy-memory` 或 `evidence-local`
--output-root        可选，`evidence-local` 时必填，且必须位于项目内 `.omo/evidence/**`
```

`--source-kind` 可选值：

- `book`
- `article`
- `paper`
- `web`

补充说明：

- `--output-profile` 不传时，当前 CLI 兼容默认值是 `legacy-memory`
- `--output-root` 只给 `evidence-local` 使用
- `--parse-only` 和 `--no-postprocess` 只属于 `parse`，不是 `postprocess` 参数

### 9.2 输出 profile

#### `legacy-memory`

- 通用 CLI 的兼容默认行为
- 会把内容整理到项目 `memory-source/` 的 raw/assets 终态结构
- 适合明确允许写终态知识资产的项目
- 在 culture-system 里，只有单独授权时才应使用

#### `evidence-local`

- 显式 opt-in 的 containment profile
- 必须配合 `--output-root .omo/evidence/<run-dir>`
- `--output-root` 只能是项目相对路径，并且解析后必须仍位于 `.omo/evidence/**`
- 会拒绝绝对路径、`..` 跳转、symlink escape 和任何项目内非 `.omo/evidence/**` 路径
- 只写文本、JSON 和图片清单，不复制图片或 PDF 二进制
- 不代表已经获得 ingest、wiki 写入或 stable memory 更新许可

### 9.3 使用 `--input`

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --input /path/to/book.pdf
```

该模式会根据 input 文件内容计算 sha12，并寻找：

```text
<project-root>/.cache/document-parser/document_parser_output/<sha12>/
```

注意：这要求 staging 目录已经存在，并且目录名与 input 文件内容 sha12 一致。若前一步 `parse` 由后端生成的是文件名 stem，而不是 sha12 stem，则应优先使用 `--staging-doc-root` 显式传入实际 staging 目录。

### 9.4 使用 `--staging-doc-root`

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/example
```

### 9.5 `evidence-local` 示例

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/example \
  --output-profile evidence-local \
  --output-root .omo/evidence/document-parser-example
```

这条命令适合 parse-only 之后的本地证据落地。它不会把结果写进 `memory-source/raw/04-books`、`memory-source/assets/raw/*` 或 `memory-source/wiki/**`。

### 9.6 指定 sha12

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind web \
  --staging-doc-root /path/to/staging/doc-root \
  --sha12 abc123def456
```

### 9.7 项目结构要求

目标项目必须包含：

```text
<project-root>/memory-source/
├── CLAUDE.md
├── raw/
└── assets/
```

否则 `postprocess` 会失败。

### 9.8 source-kind 与终态 bucket

当 profile 为 `legacy-memory` 时，`postprocess` 会根据 `source-kind` 写入对应 raw bucket 和 assets bucket。

常见映射：

```text
book    -> raw/04-books/      + assets/raw/books/
article -> raw/01-articles/   + assets/raw/articles/
paper   -> raw/02-papers/     + assets/raw/papers/
web     -> raw/07-web/        + assets/raw/web/
```

这些映射描述的是通用兼容终态，不是 culture-system 当前项目里的默认安全落点。

### 9.9 `evidence-local` 输出布局

`evidence-local` 固定只写：

```text
<project-root>/.omo/evidence/<run-dir>/
└── normalized/
    ├── document.md
    ├── document.json
    └── images.manifest.json
```

`images.manifest.json` 用于记录 staging 图片来源信息，例如相对路径、hash、字节数和 `sourceKind`。它不会复制图片或 PDF 二进制。

### 9.10 图片引用规则

`legacy-memory` 终态 Markdown 中不保留标准 Markdown 图片语法：

```markdown
![alt](image.png)
```

也不保留 HTML 图片：

```html
<img src="image.png">
```

会重写为 Obsidian embed：

```markdown
![[assets/raw/books/<finalStem>/<fileName>]]
```

`books` 会根据 source-kind 替换为 `articles`、`papers` 或 `web`。

### 9.11 成功输出

成功时 stdout 只输出一行 JSON。

`legacy-memory` 常见字段包括：

- `projectRoot`
- `sourceKind`
- `finalStem`
- `stagingDocRoot`
- `rawDir`
- `assetsDir`
- `metaPath`
- `manifestPath`
- `writtenFiles`

`evidence-local` 成功输出至少会包含：

- `projectRoot`
- `sourceKind`
- `stagingDocRoot`
- `outputProfile`
- `outputRoot`
- `writtenFiles`

并且不会返回 legacy raw/assets 终态目录字段作为目标路径。

### 9.12 失败返回码

- `2`：参数错误
- `3`：项目结构、输入文件或 staging 路径错误
- `6`：目标已存在
- `7`：后处理过程失败

## 10. 书籍后处理与拆分

当 profile 为 `legacy-memory`，且 `--source-kind book` 时，会进入书籍后处理流程。

### 10.1 主要输出

终态会写入：

```text
memory-source/raw/04-books/<finalStem>/
memory-source/assets/raw/books/<finalStem>/
memory-source/raw/05-images/<finalStem>.md
```

staging 中会保留：

```text
<staging-doc-root>/postprocess/document.postprocessed.md
```

### 10.2 拆分原则

书籍拆分使用确定性规则，不依赖大模型。

它会根据 Markdown 标题、目录线索和候选边界生成章节文件：

```text
ch-01.md
ch-02.md
...
```

如果候选边界过多，会进入 chunk 模式。

### 10.3 元数据

`meta.json` 会记录可追溯信息，例如：

- `sha12`
- `humanStem`
- `titleExtracted`
- `splitMode`
- `strongCount`
- `candidateCount`
- `tocRanges`
- `chunks`
- `postprocessedDocumentPath`
- `postprocessedDocumentSha256`

## 11. `validate`：校验终态结构

`validate` 用于检查 `memory-source/` 终态是否符合约束。

它面向 `legacy-memory` 终态路线。`evidence-local` 不把结果写进 `memory-source/`，因此默认不需要把 `validate` 当成下一步。

### 11.1 参数

```text
--project-root  必填，目标项目根目录
```

### 11.2 示例

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

### 11.3 校验内容

#### 项目结构校验

- `memory-source/` 必须存在
- `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 必须存在
- `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 必须存在
- `memory-source/raw` 必须存在
- `memory-source/assets` 必须存在

两层说明文件的区别：

- `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 是项目级 Agent 说明，用于确认项目根目录和整体协作规则。
- `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 是 memory-source 子系统说明，用于约束 raw/assets/分类/图片引用等知识库维护规则。
- 两者不是备份关系，而是父项目规则与子系统规则的关系。

#### raw 纯度校验

`raw/` 下不允许出现以下二进制或过程工件：

- 图片：`.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`
- 文档或压缩包：`.pdf`、`.zip`
- 过程文件：`.jsonl`、`.pyc`、`.pyo`、`.tmp`、`.part`、`.crdownload`
- 过程目录：`__pycache__`
- 系统文件：`.ds_store`、`thumbs.db`

#### raw/05-images 规则

`raw/05-images/` 下只允许 `.md` 文件。

#### Markdown 图片规则

终态 raw Markdown 中禁止：

```markdown
![alt](...)
```

也禁止：

```html
<img src="...">
```

只允许 Obsidian embed，并且目标必须匹配：

```text
assets/raw/<bucket>/<finalStem>/<fileName>
```

其中 `<bucket>` 只能是：

- `books`
- `articles`
- `papers`
- `web`

### 11.4 validate 输出格式

错误输出到 stderr，格式稳定：

```text
ERROR_CODE:<CODE> message="..." path="..." file="..." ref="..."
```

最后输出汇总：

```text
SUMMARY ok=<0|1> errors=<int>
```

### 11.5 validate 返回码

- `0`：无错误
- `3`：项目结构或读取错误
- `4`：`raw/` 纯度错误
- `5`：终态 Markdown / embed 引用错误

## 12. 推荐工作流

正常使用仍然应该由 Agent 执行 `/document-parser`。下面工作流是给 Agent 指令编写者和本地调试者参考的，不是要求用户把手工 CLI 当成常规入口。

### 12.1 通用兼容流程，显式允许终态写入时使用

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/source.pdf

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/<backend-stem> \
  --output-profile legacy-memory

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

### 12.2 culture-system containment 流程，默认优先

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/source.pdf \
  --page-range 12-20 \
  --model-version mineru-v4 \
  --language zh \
  --is-ocr false \
  --enable-table true \
  --enable-formula true \
  --parse-only

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/<backend-stem> \
  --output-profile evidence-local \
  --output-root .omo/evidence/document-parser-example
```

这条流程里，`postprocess` 是可选步骤，只在需要把 parse 结果整理到项目内证据目录时才运行。

### 12.3 已有 staging 的 containment 流程

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /path/to/document_parser_output/<stem> \
  --output-profile evidence-local \
  --output-root .omo/evidence/document-parser-existing-staging
```

除非有单独授权，否则不要把这条 containment 流程替换成 `legacy-memory`，也不要据此推断已经允许写 `memory-source/wiki/**` 或执行 ingest。

## 13. 常见问题

### 13.1 为什么必须传 `--project-root`？

为了避免解析结果写错项目。项目根目录由调用者明确指定，staging 固定写在：

```text
<project-root>/.cache/document-parser/
```

不会自动猜测项目位置。

### 13.2 为什么 staging 不放进 `memory-source/`？

`memory-source/` 是最终知识资产目录，应保持干净、可同步、可校验。解析过程工件放在项目级 `.cache/document-parser/`，避免污染最终知识库。

### 13.3 为什么 raw 下不能放图片？

`raw/` 用于保存纯文本事实材料。图片属于资产文件，应放到：

```text
memory-source/assets/raw/<bucket>/<finalStem>/
```

Markdown 通过 Obsidian embed 引用这些图片。

### 13.4 为什么 validate 会禁止 `![alt](...)`？

终态 raw Markdown 统一使用 Obsidian embed，便于在 Obsidian 中阅读，并避免相对路径在移动或同步后失效。

### 13.5 parse 成功但 postprocess 失败怎么办？

优先检查：

1. `--project-root` 是否正确
2. `<project-root>/CLAUDE.md` 或 `<project-root>/AGENTS.md` 是否存在
3. `memory-source/CLAUDE.md` 或 `memory-source/AGENTS.md` 是否存在
4. `memory-source/raw` 和 `memory-source/assets` 是否存在
5. staging 目录下是否存在 `normalized/document.md`
6. 使用 `--input` 时，staging 是否位于对应 sha12 目录

如果这次走的是 `evidence-local`，再额外检查：

7. `--output-profile` 是否显式设置为 `evidence-local`
8. `--output-root` 是否是项目相对路径，且位于 `.omo/evidence/**`
9. 路径中是否包含 `..` 或 symlink escape

### 13.6 什么时候会使用 PaddleOCR？

只有 MinerU 明确出现额度或限流类错误，并且输入是 PDF 或图片时，才会回退到 PaddleOCR Jobs API。

页数超限错误，例如 `-60006`，不会自动触发 PaddleOCR 回退。

### 13.7 PaddleOCR `/ocr` 为什么没出现？

因为当前 skill 只实现了 Jobs API 回退。

`/ocr` service adapter 仍然是 future boundary。文档里提到它，只是为了说明边界，不代表当前 CLI 或 Agent 流程已经支持。

### 13.8 什么时候不该把 `legacy-memory` 当默认下一步？

当项目规则明确禁止写 `memory-source/raw`、`memory-source/assets` 或 `memory-source/wiki` 时，不该把 `legacy-memory` 当 parse 之后的默认动作。

对 culture-system，默认路线应是：

1. `dry-run`
2. `parse --page-range ... --parse-only`
3. 只有需要本地证据时，才显式运行 `postprocess --output-profile evidence-local --output-root .omo/evidence/...`

## 14. 最小示例

这些示例只用于参数参考。正常使用仍然应由 Agent 调用 `/document-parser`。

### 14.1 显式授权的通用终态流程

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system \

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /home/mleon/bookfiles/example.pdf

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/<backend-stem> \
  --output-profile legacy-memory

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

### 14.2 culture-system parse-only + evidence-local

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /home/mleon/bookfiles/example.pdf \
  --page-range 12-20 \
  --parse-only

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/<backend-stem> \
  --output-profile evidence-local \
  --output-root .omo/evidence/document-parser-example
```

## 15. 事实与注意事项

事实：

- 当前实现包含 `parse`、`dry-run`、`postprocess`、`validate` 四个显式子命令。
- 未指定子命令时，会走兼容旧接口的批量解析模式。
- `parse` 会调用真实解析后端，需要有效 token，并支持 `--page-range`、`--model-version`、`--language`、`--is-ocr`、`--enable-table`、`--enable-formula`、`--parse-only`、`--no-postprocess`。
- `dry-run` 不调用解析后端，也不写文件。
- `postprocess` 的通用 CLI 默认 profile 仍是 `legacy-memory`，但它不是 culture-system 里的默认安全路线。
- `evidence-local` 是显式 containment profile，只允许写项目内 `.omo/evidence/**`，并且不复制图片或 PDF 二进制。
- MinerU 页数超限会返回结构化错误和 `suggestedPageRange`，不会自动拆分 PDF，也不会自动回退到 PaddleOCR。
- 当前 PaddleOCR `/ocr` service adapter 仍是 future boundary，不属于本版 skill 的可用路径。
- `postprocess` 要求项目根和 `memory-source/` 都有 `CLAUDE.md` 或 `AGENTS.md`，并且 `memory-source/raw`、`memory-source/assets` 存在。
- `validate` 的错误输出是结构化 stderr，最后以 `SUMMARY` 收尾。

注意事项：

- 不要把 `.cache/document-parser/` 当成最终知识库内容。
- 不要手动把图片、PDF、zip 或临时文件放入 `memory-source/raw/`。
- 不要在 stdout、stderr、evidence 或提交记录里泄露真实 token。
- 不要把 `memory-source/raw/04-books`、`memory-source/assets/raw/*` 或 `memory-source/wiki/**` 当成 culture-system 当前任务里的默认活动输出。
- 不要把 `evidence-local` 输出误读成 ingest 完成、wiki 写入许可或 source-lock 完成。
- 如果手动修改终态 Markdown，修改后应重新运行 `validate`。
- URL 与本地文件在旧式批量模式下不能混用。

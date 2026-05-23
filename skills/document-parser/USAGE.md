# document-parser 使用文档

`document-parser` 是一个通用文档解析 skill，用于把 PDF、Word、PPT、图片、扫描件或 URL 内容解析成规范化 Markdown / JSON，并把结果整理成可离线复现、可校验、可追溯的文档资产。

## 1. 适用场景

适合使用 `document-parser` 的场景：

- 解析 PDF、Word、PPT、图片或扫描件
- 把文档转换成 Markdown / JSON
- 对扫描件做 OCR 并保留原始解析工件
- 将解析结果整理到项目级 `memory-source/` 结构中
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

## 3. 凭据配置

### 3.1 环境变量

可以通过环境变量提供 token：

```bash
export MINERU_TOKEN="你的 MinerU token"
export PADDLEOCR_TOKEN="你的 PaddleOCR token"
```

### 3.2 本地 key 文件

也可以写入本地 key 文件：

```text
~/.config/opencode/keys/mineru.key
~/.config/opencode/keys/paddleocr.key
```

### 3.3 读取优先级

读取顺序为：

1. 环境变量
2. 本地 key 文件
3. 都不存在时报错

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

## 5. 命令总览

当前 CLI 支持 5 类入口。正常调试时从 skill 目录执行，并通过 `skills/` 级共享 uv project 加载 `document-parser` dependency group：

```bash
cd "$HOME/.config/opencode/skills/document-parser"

uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser <inputs...> [--output-dir <dir>]
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser parse --project-root <project> --input <file-or-url>
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser dry-run --project-root <project>
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser postprocess --project-root <project> --source-kind <kind> (--input <file> | --staging-doc-root <dir>) [--sha12 <sha12>]
uv run --project "$HOME/.config/opencode/skills" --group document-parser python -m scripts.document_parser validate --project-root <project>
```

运行环境约定：

- uv project：`$HOME/.config/opencode/skills`
- uv group：`document-parser`
- workdir：`$HOME/.config/opencode/skills/document-parser`
- Python 版本：`>=3.12`

如果 `uv` 不可用，才临时回退到系统 `python3`，并显式设置 `PYTHONPATH`；正常 `/document-parser` 调用由 Agent 自动执行，不要求用户手动操作 CLI。

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
--project-root  必填，目标项目根目录
--input         必填，本地文件路径或 URL
```

虽然 argparse 层没有把参数声明为 required，但运行时会强制校验，缺少参数会返回错误。

### 7.2 示例

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/book.pdf
```

### 7.3 输出位置

```text
<project-root>/.cache/document-parser/document_parser_output/<backend-stem>/
```

`<backend-stem>` 由具体解析后端根据输入名称或 URL 生成。当前 `parse` 会把项目级 staging 根目录固定为：

```text
<project-root>/.cache/document-parser/
```

然后由 MinerU 或 PaddleOCR 在该目录下创建 `document_parser_output/<backend-stem>/`。

### 7.4 成功输出

成功时 stdout 打印 `normalized/document.md` 路径。

### 7.5 失败返回码

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

`postprocess` 用于把 staging 中的 `normalized/document.md`、`document.json` 和图片整理到项目的 `memory-source/` 终态结构。

### 9.1 参数

```text
--project-root       必填，目标项目根目录
--source-kind        必填，内容类型
--input              与 --staging-doc-root 二选一，本地输入文件
--staging-doc-root   与 --input 二选一，已有 staging 文档目录
--sha12              可选，仅用于 --staging-doc-root 模式，必须是 12 位小写十六进制
```

`--source-kind` 可选值：

- `book`
- `article`
- `paper`
- `web`

### 9.2 使用 `--input`

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

### 9.3 使用 `--staging-doc-root`

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /home/mleon/workspace/culture-system/.cache/document-parser/document_parser_output/example
```

### 9.4 指定 sha12

```bash
uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind web \
  --staging-doc-root /path/to/staging/doc-root \
  --sha12 abc123def456
```

### 9.5 项目结构要求

目标项目必须包含：

```text
<project-root>/memory-source/
├── CLAUDE.md
├── raw/
└── assets/
```

否则 `postprocess` 会失败。

### 9.6 source-kind 与终态 bucket

`postprocess` 会根据 `source-kind` 写入对应 raw bucket 和 assets bucket。

常见映射：

```text
book    -> raw/04-books/      + assets/raw/books/
article -> raw/01-articles/   + assets/raw/articles/
paper   -> raw/02-papers/     + assets/raw/papers/
web     -> raw/07-web/        + assets/raw/web/
```

### 9.7 图片引用规则

终态 Markdown 中不保留标准 Markdown 图片语法：

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

### 9.8 成功输出

成功时 stdout 只输出一行 JSON，包含：

- `projectRoot`
- `sourceKind`
- `finalStem`
- `stagingDocRoot`
- `rawDir`
- `assetsDir`
- `metaPath`
- `manifestPath`
- `writtenFiles`

### 9.9 失败返回码

- `2`：参数错误
- `3`：项目结构、输入文件或 staging 路径错误
- `6`：目标已存在
- `7`：后处理过程失败

## 10. 书籍后处理与拆分

当 `--source-kind book` 时，会进入书籍后处理流程。

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

### 12.1 项目级标准流程

```bash
cd "$HOME/.config/opencode/skills/document-parser"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /path/to/source.pdf \
  > /tmp/document-parser-normalized-path.txt

normalizedMarkdownPath="$(cat /tmp/document-parser-normalized-path.txt)"
stagingDocRoot="$(dirname "$(dirname "$normalizedMarkdownPath")")"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --staging-doc-root "$stagingDocRoot"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

### 12.2 已有 staging 的流程

```bash
cd "$HOME/.config/opencode/skills/document-parser"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind article \
  --staging-doc-root /path/to/document_parser_output/<stem>

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

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

### 13.6 什么时候会使用 PaddleOCR？

只有 MinerU 明确出现额度或限流类错误，并且输入是 PDF 或图片时，才会回退到 PaddleOCR。

## 14. 最小示例

### 14.1 解析并整理一本书

```bash
cd "$HOME/.config/opencode/skills/document-parser"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser parse \
  --project-root /home/mleon/workspace/culture-system \
  --input /home/mleon/bookfiles/example.pdf \
  > /tmp/document-parser-normalized-path.txt

normalizedMarkdownPath="$(cat /tmp/document-parser-normalized-path.txt)"
stagingDocRoot="$(dirname "$(dirname "$normalizedMarkdownPath")")"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser postprocess \
  --project-root /home/mleon/workspace/culture-system \
  --source-kind book \
  --staging-doc-root "$stagingDocRoot"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser validate \
  --project-root /home/mleon/workspace/culture-system
```

### 14.2 只检查项目路径策略

```bash
cd "$HOME/.config/opencode/skills/document-parser"

uv run --project "$HOME/.config/opencode/skills" --group document-parser \
  python -m scripts.document_parser dry-run \
  --project-root /home/mleon/workspace/culture-system
```

## 15. 事实与注意事项

事实：

- 当前实现包含 `parse`、`dry-run`、`postprocess`、`validate` 四个显式子命令。
- 未指定子命令时，会走兼容旧接口的批量解析模式。
- `parse` 会调用真实解析后端，需要有效 token。
- `dry-run` 不调用解析后端，也不写文件。
- `postprocess` 要求项目根和 `memory-source/` 都有 `CLAUDE.md` 或 `AGENTS.md`，并且 `memory-source/raw`、`memory-source/assets` 存在。
- `validate` 的错误输出是结构化 stderr，最后以 `SUMMARY` 收尾。

注意事项：

- 不要把 `.cache/document-parser/` 当成最终知识库内容。
- 不要手动把图片、PDF、zip 或临时文件放入 `memory-source/raw/`。
- 如果手动修改终态 Markdown，修改后应重新运行 `validate`。
- URL 与本地文件在旧式批量模式下不能混用。

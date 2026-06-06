# OpenCode LSP 使用指南

## 核心策略

推荐策略：**全局保持 LSP 开启，项目内通过 `AGENTS.md` 明确真实验证命令。**

这句话的意思是：让 OpenCode 的 LSP 一直作为“背景辅助检查”开着，但不要把 LSP 当作项目是否正确的最终标准。真正判断项目能不能运行、代码有没有问题，要靠每个项目自己的验证命令，并把这些命令写进该项目的 `AGENTS.md`。

可以理解为两层检查：

| 层级 | 工具 | 作用 | 可信度 |
| --- | --- | --- | --- |
| 第一层 | LSP | 修改过程中快速发现明显问题 | 中等 |
| 第二层 | 项目验证命令 | 验证项目真实能不能运行 | 高 |

简化理解：

```text
LSP = 过程中的提醒
AGENTS.md 里的命令 = 最终验收标准
```

## 为什么要这样做

OpenCode 的 LSP 可以给 agent 提供代码诊断，例如：

- TypeScript 类型错误
- Python 类型错误
- Rust analyzer 诊断
- Go gopls 诊断
- ESLint / Biome 问题

但 LSP 有局限：

- 项目依赖没装全时可能误报
- 复杂 monorepo 中可能识别不准
- 有些错误只有构建时才能发现
- 有些错误只有测试运行时才能发现
- 有些框架问题 LSP 看不到，例如 Next.js build 错误、Vite 构建错误、pytest fixture 问题

所以更稳妥的做法是：

1. 全局开启 LSP，让 OpenCode 在编辑过程中尽早发现问题。
2. 每个项目用 `AGENTS.md` 告诉 OpenCode 最终必须运行哪些真实命令。
3. 修改完成后，以 lint、typecheck、test、build 等项目命令作为最终验证依据。

## 当前全局配置

当前 `opencode.json` 已经启用 LSP：

```json
"lsp": true
```

这表示以后使用 OpenCode 进入任何项目，只要项目满足对应语言的条件，OpenCode 就可以自动使用对应 LSP。

例如：

| 项目类型 | OpenCode 可能使用的 LSP |
| --- | --- |
| TypeScript / JavaScript | typescript、eslint、biome |
| Python | pyright、basedpyright |
| Rust | rust-analyzer |
| Go | gopls |

但“全局开启”不代表所有语言马上都能工作。每个语言服务器仍然需要满足自己的依赖条件。

## 当前环境状态

根据当前 OpenCode 环境检测结果：

| 语言 / 工具 | 当前状态 | 说明 |
| --- | --- | --- |
| TypeScript / JavaScript | 未就绪 | `typescript` LSP 缺项目依赖 |
| ESLint | 未就绪 | 项目里需要 `eslint` 依赖 |
| Python | 已就绪 | `basedpyright`、`pyright` 已安装 |
| Rust | 已就绪 | `rust-analyzer` 已安装 |
| Go | 未就绪 | 需要 `go` / `gopls` 可用 |
| Biome | 已就绪 | 可用于 TS/JS/JSON/CSS 等 |

## OpenCode LSP 的作用边界

OpenCode 的 LSP 主要用于给 agent 提供诊断，不是像编辑器那样以补全为核心。

启用 LSP 后，当 OpenCode 打开某个文件时，会按文件扩展名匹配对应语言服务器。如果服务器可用，就会自动启动。

适合依赖 LSP 的场景：

- 修改过程中快速发现类型错误
- 检查单个文件或局部修改是否有明显问题
- 给 agent 提供额外诊断上下文

不适合只依赖 LSP 的场景：

- 判断整个项目是否能构建
- 判断测试是否通过
- 判断生产构建是否成功
- 判断框架配置是否正确
- 判断运行时行为是否符合预期

最终原则：**LSP 提供即时反馈，项目命令提供最终可信验证。**

## 为什么每个项目都需要 AGENTS.md

不同项目的真实验证命令不一样。即使都是 TypeScript 项目，也可能分别使用 npm、pnpm、bun、yarn、turbo 或 nx。

例如 TypeScript 项目可能使用：

```bash
npm run typecheck
npm test
```

也可能使用：

```bash
pnpm typecheck
pnpm test
```

或者：

```bash
bun run typecheck
bun test
```

Python 项目也一样，可能使用：

```bash
pytest
```

也可能使用：

```bash
uv run pytest
```

或者：

```bash
poetry run pytest
```

如果项目没有 `AGENTS.md`，OpenCode 只能根据经验猜测验证命令。写了 `AGENTS.md` 后，OpenCode 会优先按项目规则执行。

## AGENTS.md 应该写什么

每个项目根目录建议放一个 `AGENTS.md`，至少包含：

1. 项目技术栈
2. 包管理器
3. 类型检查命令
4. Lint 命令
5. 测试命令
6. 构建命令
7. 修改后的验证要求

推荐结构：

```md
# 项目规则

## 技术栈

- TypeScript
- React
- Vite

## 包管理器

- npm

## 验证命令

- 类型检查：npm run typecheck
- Lint：npm run lint
- 测试：npm test
- 构建：npm run build

## 要求

- 修改 TypeScript / JavaScript 文件后必须运行 npm run typecheck
- 修改业务逻辑后必须运行 npm test
- 修改构建配置后必须运行 npm run build
- 不要只依赖 LSP 诊断
```

## TypeScript / JavaScript 项目

OpenCode 的 TypeScript LSP 要求项目中安装 `typescript`。

建议每个 TypeScript / JavaScript 项目至少安装：

```bash
npm install -D typescript
```

如果项目使用 ESLint：

```bash
npm install -D eslint
```

如果项目使用 Biome：

```bash
npm install -D @biomejs/biome
```

推荐在 `package.json` 中配置脚本：

```json
{
  "scripts": {
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "format": "biome format .",
    "check": "biome check ."
  }
}
```

对应的 `AGENTS.md` 可以写：

```md
# 项目规则

## 技术栈

- TypeScript / JavaScript

## 验证命令

- 类型检查：npm run typecheck
- Lint：npm run lint
- 测试：npm test
- 构建：npm run build

## 要求

- 修改 TypeScript / JavaScript 文件后必须运行 npm run typecheck
- 修改业务逻辑后必须运行 npm test
- 修改构建配置后必须运行 npm run build
- 不要只依赖 LSP 诊断
```

## Python 项目

当前环境中 Python LSP 已经可用：`basedpyright` 和 `pyright` 都已安装。

建议 Python 项目安装：

```bash
pip install basedpyright ruff pytest
```

如果使用 `uv`：

```bash
uv add --dev basedpyright ruff pytest
```

推荐验证命令：

```bash
basedpyright
ruff check .
pytest
```

对应的 `AGENTS.md` 可以写：

```md
# 项目规则

## 技术栈

- Python
- pytest
- ruff
- basedpyright

## 验证命令

- 类型检查：basedpyright
- Lint：ruff check .
- 测试：pytest

## 要求

- 修改 Python 文件后必须运行 basedpyright
- 修改格式或导入后必须运行 ruff check .
- 修改业务逻辑后必须运行 pytest
- 不要只依赖 LSP 诊断
```

如果项目使用 `uv`，可以改成：

```md
## 验证命令

- 类型检查：uv run basedpyright
- Lint：uv run ruff check .
- 测试：uv run pytest
```

如果项目不需要严格类型检查，可以在 `pyproject.toml` 中调整 pyright / basedpyright 配置。但长期项目建议保留类型检查。

## Rust 项目

当前环境中 Rust LSP 已经可用：`rust-analyzer` 已安装。

Rust 项目推荐主要依赖 Cargo 命令验证：

```bash
cargo check
cargo test
cargo clippy
cargo fmt --check
```

对应的 `AGENTS.md` 可以写：

```md
# 项目规则

## 技术栈

- Rust

## 验证命令

- 检查：cargo check
- Lint：cargo clippy
- 测试：cargo test
- 格式检查：cargo fmt --check

## 要求

- 修改 Rust 文件后必须运行 cargo check
- 修改业务逻辑后必须运行 cargo test
- 提交前运行 cargo clippy 和 cargo fmt --check
- 不要只依赖 LSP 诊断
```

LSP 可以辅助发现问题，但 Rust 项目的最终验证应以 `cargo check`、`cargo test` 和 `cargo clippy` 为准。

## Go 项目

当前环境中 Go LSP 未就绪，需要确保系统里有 Go 和 gopls。

安装 gopls：

```bash
go install golang.org/x/tools/gopls@latest
```

确保 `$GOPATH/bin` 在 `PATH` 中：

```bash
export PATH="$PATH:$(go env GOPATH)/bin"
```

Go 项目推荐验证命令：

```bash
go test ./...
go vet ./...
gofmt -w .
```

对应的 `AGENTS.md` 可以写：

```md
# 项目规则

## 技术栈

- Go

## 验证命令

- 测试：go test ./...
- 静态检查：go vet ./...
- 格式化：gofmt -w .

## 要求

- 修改 Go 文件后必须运行 go test ./...
- 修改公共 API 后必须运行 go vet ./...
- 提交前运行 gofmt -w .
- 不要只依赖 LSP 诊断
```

如果只是偶尔写 Go，可以等真正进入 Go 项目时再安装 `gopls`。

## 推荐的 OpenCode LSP 配置

当前配置已经够用：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": true
}
```

如果想对 TypeScript 做更细配置，可以改成对象形式：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": {
    "typescript": {
      "initialization": {
        "preferences": {
          "importModuleSpecifierPreference": "relative"
        }
      }
    }
  }
}
```

但对日常使用来说，不是必须修改。

## 最适合当前使用习惯的落地方案

你常用 TypeScript、JavaScript、Python，偶尔使用 Go 和 Rust。建议采用以下策略：

1. 全局保持 `"lsp": true`。
2. TS/JS 项目中安装 `typescript`。
3. 需要 lint 的 TS/JS 项目安装 `eslint` 或 `@biomejs/biome`。
4. Python 项目使用 `basedpyright + ruff + pytest`。
5. Rust 项目使用 `rust-analyzer` 辅助，最终以 Cargo 命令验证。
6. Go 项目等实际需要时再安装 `gopls`。
7. 每个项目维护自己的 `AGENTS.md`，明确验证命令。

最终原则：**全局 LSP 负责快速提醒，项目 `AGENTS.md` 负责定义最终验收命令。**

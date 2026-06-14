# Markdown LSP 配置指南

## 概述

opencode 默认没有内置 Markdown LSP 服务器，需要手动配置。本文档记录如何配置 markdown-oxide 作为 Markdown 文件的 LSP，以及配置过程中涉及的源码分析。

## 为什么选择 markdown-oxide

### 对比分析

| 特性 | markdown-oxide | marksman | ltex-ls |
|------|---------------|----------|---------|
| 设计目标 | Obsidian PKM 专用 | 通用 Markdown | 拼写/语法检查 |
| 语言 | Rust | Rust | Java |
| Wikilinks `[[]]` | ✅ 完整支持 | ❌ | ❌ |
| Embeds `![[]]` | ✅ | ❌ | ❌ |
| Callouts `> [!note]` | ✅ 自动补全 | ❌ | ❌ |
| Tags `#tag` | ✅ 自动补全 | ❌ | ❌ |
| 反向链接 | ✅ | ❌ | ❌ |
| 块引用 `^block-id` | ✅ | ❌ | ❌ |
| 每日笔记导航 | ✅ | ❌ | ❌ |
| 重命名链接 | ✅ 自动更新所有引用 | ❌ | ❌ |
| 拼写检查 | ❌ | ❌ | ✅ |

### 结论

- **Obsidian 用户首选**：markdown-oxide
- **拼写检查需求**：可搭配 ltex-ls
- **通用 Markdown**：marksman（不支持 Obsidian 特性）

---

## 核心发现：opencode 有两套独立的 LSP 系统

opencode 中存在两套 LSP 系统，**配置文件不同，互不读取**：

| 系统 | 提供方 | 配置文件 | 提供的工具 |
|------|--------|---------|-----------|
| opencode 原生 LSP | opencode 核心 | `opencode.json` 的 `lsp` 字段 | opencode 内置诊断 |
| oh-my-openagent lsp-tools-mcp | oh-my-openagent 插件 | `~/.codex/lsp-client.json` | `lsp_diagnostics`、`lsp_goto_definition`、`lsp_find_references`、`lsp_symbols`、`lsp_rename` 等 |

**必须同时配置两处，才能让所有 LSP 工具正常工作。**

### 源码依据

#### 1. oh-my-openagent 已移除对 `opencode.json` 中 `lsp` 字段的支持

源码位置：`oh-my-openagent/dist/index.js:8840-8843`

```javascript
if (copy.lsp !== undefined) {
    const droppedServers = copy.lsp && typeof copy.lsp === "object" ? Object.keys(copy.lsp) : [];
    log("Removed obsolete 'lsp' config key from oh-my-opencode config. Custom LSP servers are now configured in .opencode/lsp.json at the project root (consumed by the 'lsp' MCP server). Move any server definitions there to restore them.", { configPath, droppedServers });
    delete copy.lsp;
}
```

**结论**：在 `opencode.json` 中配置的 `lsp` 字段只对 opencode 原生系统生效，oh-my-openagent 会忽略（甚至自动删除）。

#### 2. oh-my-openagent 的 LSP MCP 架构

源码位置：`oh-my-openagent/dist/index.js`

```javascript
// 环境变量定义
var PROJECT_LSP_CONFIGS = [".opencode/lsp.json", ".omo/lsp.json", ".omo/lsp-client.json"];

// 创建 LSP MCP 配置
function createLspMcpConfig(options = {}) {
  const resolvedCommand = resolveLspCommand(options);
  return {
    type: "local",
    command: resolvedCommand.command,
    enabled: resolvedCommand.exists,
    environment: {
      LSP_TOOLS_MCP_PROJECT_CONFIG: PROJECT_LSP_CONFIGS.join(delimiter2)
    }
  };
}
```

**结论**：oh-my-openagent 通过环境变量 `LSP_TOOLS_MCP_PROJECT_CONFIG` 告诉 `lsp-tools-mcp` 去读取 `.opencode/lsp.json` 等路径。但**没有设置** `LSP_TOOLS_MCP_USER_CONFIG`。

#### 3. lsp-tools-mcp 的配置加载逻辑

源码位置：`packages/lsp-tools-mcp/dist/lsp/config-loader.js`

```javascript
function getProjectConfigPaths() {
    const projectOverride = contextEnv("LSP_TOOLS_MCP_PROJECT_CONFIG");
    if (projectOverride) {
        return projectOverride.split(delimiter).filter(Boolean).map(resolveProjectConfigPath);
    }
    return [join(contextCwd(), ".codex", "lsp-client.json")];  // 默认回退
}

function getUserConfigPath() {
    const userOverride = contextEnv("LSP_TOOLS_MCP_USER_CONFIG");
    if (!userOverride)
        return join(homedir(), ".codex", "lsp-client.json");  // 默认回退
    return isAbsolute(userOverride) ? userOverride : join(homedir(), userOverride);
}
```

**结论**：
- 项目级配置：通过 `LSP_TOOLS_MCP_PROJECT_CONFIG` 环境变量指定，相对于 `lsp-daemon` 的工作目录（即当前项目根目录）
- 用户级配置：oh-my-openagent 未设置 `LSP_TOOLS_MCP_USER_CONFIG`，回退到 lsp-tools-mcp 默认路径 `~/.codex/lsp-client.json`

#### 4. lsp-tools-mcp 的诊断实现

源码位置：`packages/lsp-tools-mcp/dist/tools.js`

```javascript
// lsp_diagnostics 工具定义
{
    name: "diagnostics",
    aliases: ["lsp_diagnostics"],
    title: "LSP Diagnostics",
    description: "Get errors, warnings, and hints for a source file or directory.",
    inputSchema: objectSchema({
        filePath: { type: "string", description: "File or directory path to check." },
        severity: {
            type: "string",
            enum: ["error", "warning", "information", "hint", "all"],
            description: "Severity filter. Defaults to all.",
        },
    }, ["filePath"]),
    execute: executeLspDiagnostics,
}

// 诊断执行逻辑
async function executeLspDiagnostics(params, signal) {
    const filePath = requireString(params, "filePath");
    const severity = severityFilter(params);
    // ...
    const result = await withLspClient(filePath, async (client) => client.diagnostics(filePath), "diagnostics", clientOptions(signal));
    const diagnostics = filterDiagnosticsBySeverity(asDiagnosticArray(result), severity);
    // ...
}
```

#### 5. 服务器查找逻辑

源码位置：`packages/lsp-tools-mcp/dist/lsp/server-resolution.js`

```javascript
function findServerForExtension(ext) {
    const servers = getMergedServers();
    for (const server of servers) {
        if (server.extensions.includes(ext) && isServerInstalled(server.command)) {
            return { status: "found", server: { ... } };
        }
    }
    for (const server of servers) {
        if (server.extensions.includes(ext)) {
            return { status: "not_installed", server: { ... }, installHint };
        }
    }
    return { status: "not_configured", extension: ext, availableServers };
}
```

**结论**：找不到配置的服务器时，返回错误信息 `No LSP server configured for extension: ${ext}`。

#### 6. lsp_diagnostics 错误信息来源

源码位置：`packages/lsp-tools-mcp/dist/lsp/client-wrapper.js`

```javascript
export function formatServerLookupError(result) {
    if (result.status === "not_installed") {
        return formatNotInstalled(result);
    }
    return [
        `No LSP server configured for extension: ${result.extension}`,
        "",
        `Available servers: ${result.availableServers.slice(0, 10).join(", ")}...`,
        "",
        "Configure a custom server in '.codex/lsp-client.json':",
        "  {",
        '    "lsp": {',
        '      "my-server": {',
        '        "command": ["my-lsp", "--stdio"],',
        `        "extensions": ["${result.extension}"]`,
        "      }",
        "    }",
        "  }",
    ].join("\n");
}
```

---

## 安装步骤

### 第一步：安装 markdown-oxide 二进制

```bash
# 下载最新版本
curl -fsSL https://github.com/Feel-ix-343/markdown-oxide/releases/latest/download/markdown-oxide-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/bin/

# 验证安装
markdown-oxide --version
```

### 第二步：配置 opencode 原生 LSP

在 `~/.config/opencode/opencode.json` 中添加 `lsp` 字段：

```json
{
  "lsp": {
    "markdown-oxide": {
      "command": ["markdown-oxide", "--stdio"],
      "extensions": [".md", ".markdown"]
    }
  }
}
```

### 第三步：配置 oh-my-openagent lsp-tools-mcp

创建用户级配置文件 `~/.codex/lsp-client.json`：

```bash
mkdir -p ~/.codex
cat > ~/.codex/lsp-client.json << 'EOF'
{
  "lsp": {
    "markdown-oxide": {
      "command": ["markdown-oxide", "--stdio"],
      "extensions": [".md", ".markdown"]
    }
  }
}
EOF
```

### 第四步：创建符号链接（可选，便于管理）

```bash
mkdir -p ~/.config/opencode/.opencode
ln -s ~/.codex/lsp-client.json ~/.config/opencode/.opencode/lsp.json
```

### 第五步：重启 opencode

配置完成后需要**重启 opencode** 才能生效。

---

## 验证配置

### 验证 1：检查 LSP 状态

```
lsp_status
```

应显示：
```
- markdown-oxide: installed; source=user; extensions=.md, .markdown
```

### 验证 2：测试诊断功能

创建测试文件 `lsp-test.md`：

```markdown
# 测试

断开的链接 [[nonexistent-file]]

另一个断开的链接 [[完全不存在的笔记]]

断开的嵌入 ![[nonexistent-image.png]]

正常内容不应该有诊断。
```

运行诊断：

```
lsp_diagnostics(filePath="lsp-test.md")
```

预期输出：
```
information[Obsidian LS] at 3:15: Unresolved Reference
information[Obsidian LS] at 5:9: Unresolved Reference
information[Obsidian LS] at 7:7: Unresolved Reference
```

### 验证 3：severity 过滤

```
lsp_diagnostics(filePath="lsp-test.md", severity="error")
```

预期输出：`No diagnostics found`（markdown-oxide 的诊断都是 information 级别）

---

## 配置文件位置汇总

| 文件 | 作用 | 必须 |
|------|------|------|
| `~/.config/opencode/opencode.json` 的 `lsp` 字段 | opencode 原生 LSP 配置 | ✅ |
| `~/.codex/lsp-client.json` | oh-my-openagent 用户级 LSP 配置（配置源） | ✅ |
| `~/.config/opencode/.opencode/lsp.json` | 符号链接 → `~/.codex/lsp-client.json` | 可选 |
| `~/.config/moxide/settings.toml` | markdown-oxide 全局设置 | ❌ 可选 |
| `项目目录/.moxide.toml` | markdown-oxide 项目级设置 | ❌ 可选 |

---

## 关于 unresolved_diagnostics

**不需要关闭**，因为：

1. `[[wikilinks]]` 是 Obsidian 特有语法
2. 普通 Markdown 文档不会使用这种语法
3. 只有文档中有 `[[...]]` 时才会触发解析

默认行为：`unresolved_diagnostics = true`，普通 Markdown 文件不会有警告。

## 可选：自定义 markdown-oxide 设置

如果需要修改默认行为，创建 `~/.config/moxide/settings.toml`：

```toml
# 关闭未解析引用诊断（默认: true）
unresolved_diagnostics = false

# 关闭语义高亮（默认: true）
semantic_tokens = false

# 关闭鼠标悬停预览（默认: true）
hover = false

# 其他可选配置
heading_completions = true
title_headings = true
tags_in_codeblocks = false
references_in_codeblocks = false
include_md_extension_md_link = false
include_md_extension_wikilink = false
case_matching = "Smart"
inlay_hints = true
block_transclusion = true
heading_slug = false
```

## 已知问题

### 代码块中的 `[[]]` 误识别

```python
data = [[1, 2], [3, 4]]  # 可能被误识别为 wikilinks
```

已在最新版修复（PR #464）。

---

## 参考链接

- [markdown-oxide 官网](https://oxide.md/)
- [GitHub 仓库](https://github.com/Feel-ix-343/markdown-oxide)
- [opencode LSP 文档](https://opencode.ai/docs/lsp/)
- [lsp-tools-mcp 源码](https://github.com/code-yeongyu/lsp-tools-mcp)
- [oh-my-openagent 源码](https://github.com/code-yeongyu/oh-my-openagent)

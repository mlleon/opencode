# Markdown LSP 配置指南

## 概述

opencode 默认没有内置 Markdown LSP 服务器，需要手动配置。本文档介绍如何配置 markdown-oxide 作为 Markdown 文件的 LSP。

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

## 配置方法

### opencode.json 配置

在 `~/.config/opencode/opencode.json` 中添加：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "autoupdate": true,
  "lsp": {
    "markdown-oxide": {
      "command": ["markdown-oxide"],
      "extensions": [".md", ".markdown"]
    }
  }
}
```

### 配置说明

- `command`：LSP 服务器的可执行命令
- `extensions`：支持的文件扩展名

## 关于 unresolved_diagnostics

### 问题

是否需要关闭 `unresolved_diagnostics` 来避免普通 Markdown 文件误报？

### 答案

**不需要**，因为：

1. `[[wikilinks]]` 是 Obsidian 特有语法
2. 普通 Markdown 文档不会使用这种语法
3. 只有文档中有 `[[...]]` 时才会触发解析

### 默认行为

- `unresolved_diagnostics = true`（默认值）
- 普通 Markdown 文件**不会有警告**
- Obsidian 风格文档中如果 `[[link]]` 指向不存在的文件，会显示警告

## 配置文件位置

| 文件 | 作用 | 是否必须 |
|------|------|----------|
| `~/.config/opencode/opencode.json` | LSP 服务器配置 | ✅ 必须 |
| `~/.config/moxide/settings.toml` | markdown-oxide 全局设置 | ❌ 可选 |
| `项目目录/.moxide.toml` | 项目级设置 | ❌ 可选 |

### 配置优先级

```
项目目录/.moxide.toml  >  ~/.config/moxide/settings.toml（全局）
```

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

## 生效方式

配置完成后需要**重启 opencode** 才能生效。

## 验证配置

重启后，打开 `.md` 文件，检查：

1. LSP 状态：`lsp_status` 应显示 markdown-oxide
2. 诊断功能：在 Obsidian 文档中使用 `[[]]` 语法测试

## 参考链接

- [markdown-oxide 官网](https://oxide.md/)
- [GitHub 仓库](https://github.com/Feel-ix-343/markdown-oxide)
- [opencode LSP 文档](https://opencode.ai/docs/lsp/)

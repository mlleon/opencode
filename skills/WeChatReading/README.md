# 微信读书 Skills

为 AI Agent 提供微信读书能力的 Skill 集合，支持搜书、书架管理、笔记导出、阅读统计等功能。

## 配置

使用前需要设置微信读书 API Key：

1. 前往 [https://weread.qq.com/r/weread-skills](https://weread.qq.com/r/weread-skills) 获取你的 API Key
2. 在启动 OpenCode 的 shell 环境中设置环境变量。

直接执行 `export` 只对当前终端有效，关闭终端后不会保留：

```bash
export WEREAD_API_KEY=wrk-xxxxxxxx
```

如果希望以后新开终端后直接运行 `opencode` 就能使用，需要把同一行写入当前 shell 的启动文件。Bash 写入 `~/.bashrc`，Zsh 写入 `~/.zshrc`。

Bash 用户首次配置可以直接追加到 `~/.bashrc`：

```bash
echo 'export WEREAD_API_KEY="wrk-你的真实key"' >> ~/.bashrc
```

Zsh 用户对应写入 `~/.zshrc`：

```bash
echo 'export WEREAD_API_KEY="wrk-你的真实key"' >> ~/.zshrc
```

不要只在终端里执行一次 `export`；那只对当前终端临时有效。重复执行上面的追加命令会产生重复配置，已经配置过时先检查：

```bash
grep -n 'WEREAD_API_KEY' ~/.bashrc
```

写入后只需要让当前终端重新加载一次配置：可以重新打开终端，或在当前终端手动执行一次：

```bash
source ~/.bashrc
echo "${WEREAD_API_KEY:+set}"
```

如果输出 `set`，说明当前终端已经有 `WEREAD_API_KEY`。之后从这个终端启动 OpenCode：

```bash
opencode
```

以后新打开的终端会自动读取 `~/.bashrc` / `~/.zshrc`，不需要每次手动 `source`。日常使用时直接运行 `opencode` 即可；只有刚修改启动文件、且不想重新打开终端时，才需要手动 `source` 一次。

全局安装和项目安装的配置方式相同：无论 Skill 位于 `~/.config/opencode/skills/WeChatReading`，还是项目内的 `.opencode/skills/WeChatReading`，API Key 都通过启动 OpenCode 的进程环境传入，而不是从 Skill 目录读取。项目安装时也只需要确保在启动该项目的 OpenCode 前，当前 shell 中已经存在 `WEREAD_API_KEY`。

不要把真实 API Key 提交到项目仓库；如果需要示例配置，只提交占位值。

> API Key 绑定用户身份，所有需要用户身份的接口会自动注入，无需手动传入。

## 使用

安装后直接用自然语言与 Agent 对话即可：

```
"帮我搜一下三体"
"看看我的书架"
"我这个月读了多久"
"导出我在这本书里的划线"
"给我推荐几本书"
"这本书有什么热门划线"
"三体有什么点评"
```

## 功能

| 能力     | 说明                                             | 详细文档                           |
| -------- | ------------------------------------------------ | ---------------------------------- |
| 搜索书籍 | 书城搜索，支持电子书/有声书/网文/作者/全文等类型 | [`search.md`](skills/search.md)     |
| 书籍信息 | 书籍详情、章节目录、阅读进度                     | [`book.md`](skills/book.md)         |
| 书架管理 | 查看书架（电子书 + 有声书 + 文章收藏）           | [`shelf.md`](skills/shelf.md)       |
| 笔记划线 | 笔记概览、划线内容、个人想法、热门划线           | [`notes.md`](skills/notes.md)       |
| 阅读统计 | 阅读时长、天数、排行、偏好分析                   | [`readdata.md`](skills/readdata.md) |
| 书籍点评 | 公开点评浏览与筛选                               | [`review.md`](skills/review.md)     |
| 推荐发现 | 个性化推荐、相似书推荐                           | [`discover.md`](skills/discover.md) |

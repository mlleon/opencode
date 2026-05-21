# Git 多端白名单协同与同步操作手册

在跨设备协作中，我们通常需要保障两项原则：
1. **远程为主**：多端共用的公共文件、公共配置、核心代码等强制以 GitHub 远程仓库为最新标准。
2. **本地为主**：各设备本地特有的敏感文件（如密钥、本地私有配置等）只保留在本地，绝不上报且绝不被远程覆盖。

本手册详细介绍了如何基于 Git 的白名单和忽略保护机制实现完美的跨设备同步。

---

## 一、 核心机制：.gitignore 白名单配置

通过在 `.gitignore` 中配置反向排除（即白名单模式），让 Git 仅追踪极少数公共文件，而自动隐藏并保护其余所有本地特有文件。

### 示例配置 (`.gitignore`)
```text
# 1. 先忽略项目下的所有文件和目录
*

# 2. 逐步解禁特定目录和文件（白名单）
!/.gitignore
!/bakeup/
!/bakeup/**
!/skills/
!/skills/**
!/oh-my-openagent.json
!/opencode.json
```

> **⚠️ 重要说明**：仅用 `!/bakeup/` 解禁目录本身是不够的，还必须加上 `!/bakeup/**` 才能解禁**目录内所有层级**的子文件和子目录。`*` 规则会递归匹配所有路径，没有 `**` 后缀则目录内的文件依然被忽略。

* **原理**：处于 `*` 范围内的本地敏感文件（如 `/keys/`、私有临时文件等）在 Git 树中是 `Untracked` 且被忽略的状态。Git 在执行拉取、重置等更新操作时，默认**绝对不会修改或删除未追踪的文件**。

---

## 二、 另一台设备（同步端）首次初始化与拉取

如果另一台设备本地已经有了项目的所有文件，且目前**只是普通文件夹（完全没有 `.git` 文件夹）**，请按照以下步骤执行首次同步：

### 1. 初始化本地 Git 仓库并关联远程
打开终端，进入项目根目录，运行：
```bash
git init
git remote add origin git@github.com:mlleon/opencode.git
```

### 2. 拉取远程仓库的分支信息
```bash
git fetch origin master
```
*(注意：如果主分支名为 `main`，请将上述及后续步骤中的 `master` 替换为 `main`)*

### 3. 强制对齐远程仓库（核心操作）
```bash
git reset --hard origin/master
```
* **效果说明**：
  * **同名文件（GitHub 有，本地也有）**：本地版本会被远程仓库的最新版**强制覆盖**。
  * **本地特有文件（GitHub 没有，本地有）**：由于远程没有这些文件，它们会被视作 `Untracked` 状态而**100%安全地保留**在本地，原封不动。
  * **安全建议**：在首次执行 `git reset --hard` 前，建议将本地整个项目文件夹做个复制备份。

### 4. 绑定远程分支（建立追踪关系）
```bash
git branch --set-upstream-to=origin/master master
```
* **效果**：将本地的 `master` 分支与远程 `origin/master` 彻底绑定，永久避免后续执行普通 `git pull` 时提示 `There is no tracking information...` 错误。

---

## 三、 日常同步与协作

绑定关系建立好后，后续的日常维护非常简单和纯净：

### 1. 正常更新公共文件
当远程仓库的白名单文件有新推送时，只需在本地简单运行：
```bash
git pull
```
* **效果**：Git 只会默默更新白名单里的公共文件。本地特有的未追踪文件既不会被覆盖，也绝不会被不小心上传。

### 2. 强力“一键对齐远程”
如果本地无意中改动了公共文件并导致拉取冲突，想要直接放弃本地对公共文件的修改，强制以 GitHub 远程仓库为最新基准，可以直接执行：
```bash
git fetch origin
git reset --hard origin/master
```
* **效果**：本地被 Git 追踪的所有公共文件瞬间恢复到和远程一致，而本地特有的未追踪文件继续安全保留。

---

## 四、VS Code 集成：自动检测远程更新

另一台设备在使用 VS Code 时，默认不会自动检测远程仓库的新提交，需要在 VS Code 中进行配置才能让右下角状态栏显示拉取提示。

### 1. 开启自动 Fetch（推荐）

在 VS Code 中按 `Ctrl+,` 打开设置，搜索并勾选：

```
git.autofetch → ✅ 勾选
```

或者在 `settings.json` 中手动添加：

```json
"git.autofetch": true
```

开启后，VS Code 会每隔 **60 秒**自动执行 `git fetch`，当检测到远程有新提交时，右下角状态栏会显示 **↓ N** (N 为落后提交数) 的拉取提示图标，点击即可拉取。

### 2. 相关辅助设置

```json
// 自动 fetch 的时间间隔（单位：秒，默认 60）
"git.autofetchPeriod": 60

// 在状态栏显示同步按钮（拉取/推送）
"git.showSyncCommand": true
```

### 3. 手动刷新（不依赖自动检测）

如果不想开启自动 fetch，随时可以通过以下方式手动检查：
* 点击 VS Code 左下角状态栏的分支名称（如 `master`）
* 在弹出的菜单中选择 **"拉取"（Pull）**
* 或者使用快捷键 `Ctrl+Shift+P`，输入 `Git: Pull` 执行

---

## 五、 常见问题与防错指南

1. **同名文件冲突（最常见）**：
   * **场景**：主设备（设备 A）在 GitHub 仓库新提交了一个文件（如 `config.key`），而另一台设备（设备 B）本地恰好也有一个同名但未被追踪的 `config.key`。
   * **现象**：执行 `git pull` 会报 *The following untracked working tree files would be overwritten by merge...*。
   * **解决办法**：设备 B 需先临时将本地的 `config.key` 重命名（如 `config_local.key`），拉取完毕后再重新处理或改回。
   ```
   mv bakeup/git-sync-guide.md bakeup/git-sync-guide.md.bak
   git pull
   ```

2. **白名单解禁后远程拉取失败**：
   * **场景**：设备 A 更新了 `.gitignore` 白名单（如添加了 `!/bakeup/**`），使之前被忽略的文件变为可追踪，并推送了这些文件。设备 B 本地原本就有这些文件（处于忽略/未追踪状态）。
   * **现象**：设备 B 执行 `git pull` 时，报 *The following untracked working tree files would be overwritten by merge...*。
   * **原因**：Git 的合并操作不允许覆盖本地已有的未追踪文件，即使该文件内容与远程一致。
   * **解决办法**：设备 B 先将本地的冲突文件备份或删除，再拉取：
   ```bash
   # 备份本地同名的未追踪文件
   mv bakeup/git-sync-guide.md bakeup/git-sync-guide.md.bak
   # 拉取远程最新更新
   git pull
   # 确认拉取成功后删除备份（内容通常一致，无需保留）
   rm bakeup/git-sync-guide.md.bak
   ```

3. **全局忽略同步**：
   * 确保两端使用相同的 `.gitignore` 配置。任何一端对 `.gitignore` 的白名单解禁改动，在通过 Git 推送/拉取后，都会立即在对方设备上同步生效，从而统一排除规则。

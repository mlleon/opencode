# Git 双设备同步方案

## 一、方案说明

- **主设备（本机）**：负责修改文件、提交、推送到 `master`
- **副设备**：提交自己的改动后推送，推送冲突时先 rebase 再推送

---

## 二、核心机制

### 白名单 .gitignore

只有白名单内的文件才会被 git 追踪和同步，其余全部忽略：

```text
# 先忽略所有文件和目录
*

# 逐步解禁需要同步的文件（白名单）
!/.gitignore
!/opencode.json
!/oh-my-openagent.json
!/bakeup/
!/bakeup/**
!/skills/
!/skills/**
```

白名单之外再追加排除规则，防止 Python 缓存文件混入：

```text
**/__pycache__/
**/*.pyc
**/*.pyo
**/*.pyd
```

### 停止追踪已提交的文件

对于已经在仓库中但不想继续同步的文件，需执行一次：

```bash
git rm --cached <文件名>
git commit -m "stop tracking <文件名>"
git push origin master
```

> 执行后本地文件不受影响，git 永久忽略其改动。
> **注意**：此操作会在远程产生新提交，副设备下次推送前需先 `git pull --rebase origin master`。

---

## 三、日常操作

### 提交并推送

```bash
git add .
git status          # 确认只有白名单内的文件被暂存
git commit -m "..."
git push origin master
```

### 推送被拒绝（rejected, fetch first）

**原因**：远程有新提交，本地落后了。

**解决**：

```bash
git pull --rebase origin master
git push origin master
```

### .gitignore 产生冲突时

rebase 期间如果 `.gitignore` 报冲突，采用远程版本覆盖本地：

```bash
git checkout --theirs .gitignore
git add .gitignore
git rebase --continue
git push origin master
```

> `--theirs` 在 rebase 期间指的是远程（`origin/master`）的版本。

### 推送后再次被拒绝

如果 rebase 成功但推送仍被拒绝，说明对方在此期间又推了新提交，再执行一次：

```bash
git pull --rebase origin master
git push origin master
```

---

## 四、当前白名单内容

| 路径 | 说明 |
|------|------|
| `.gitignore` | 白名单规则本身 |
| `opencode.json` | opencode 主配置 |
| `oh-my-openagent.json` | oh-my-openagent 主配置 |
| `bakeup/` | 配置文件备份及文档 |
| `skills/` | opencode skills（排除 `__pycache__` 等缓存） |

---

## 五、不追踪的文件

以下文件在本地存在但 git 完全不感知：

| 路径 | 原因 |
|------|------|
| `node_modules/` | 依赖包，不应入库 |
| `bun.lock` / `package-lock.json` | 由 `*` 规则默认忽略 |
| `keys/` | 密钥目录 |
| `auto-update.log` | 运行日志 |
| `**/__pycache__/`、`**/*.pyc` | Python 缓存，不应入库 |

---

## 六、常见问题

### 推送被拒绝（rejected, fetch first）

**原因**：远程有另一台设备产生的新提交，本地落后了。

**解决**：

```bash
git pull --rebase origin master
git push origin master
```

### 拉取提示"divergent branches"

**原因**：两端各自有提交，分叉了。

**解决**：同上，用 `--rebase` 拉取。或一次性设置默认行为：

```bash
git config --global pull.rebase true
```

设置后以后直接 `git pull` 即可，无需每次加 `--rebase`。

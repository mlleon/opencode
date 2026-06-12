# Git 同步策略说明

## 一、方案说明

本仓库用于同步 opencode 的配置文件和 skills，采用**白名单 `.gitignore`** 策略：

- 只有白名单内的文件才会被 git 追踪和同步，其余全部忽略
- `opencode.json`、`oh-my-openagent.json` 等运行时配置文件**不纳入追踪**，本地修改不会产生 git 状态变化

---

## 二、核心机制

### 白名单 .gitignore

```text
# 先忽略所有文件和目录
*

# 逐步解禁需要同步的文件（白名单）
!/.gitignore
!/bakeup/
!/bakeup/**
!/skills/
!/skills/**
```

同时追加排除规则，防止 Python 缓存文件混入：

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

---

## 四、当前白名单内容

| 路径 | 说明 |
|------|------|
| `.gitignore` | 白名单规则本身 |
| `bakeup/` | 配置文件备份（opencode、oh-my-openagent 等） |
| `skills/` | opencode skills（排除 `__pycache__` 等缓存） |
| `git-sync-strategy.md` | 本文档 |

---

## 五、不追踪的文件

以下文件在本地存在但 git 完全不感知：

| 路径 | 原因 |
|------|------|
| `opencode.json` | 运行时配置，含 API keys，设备间有差异 |
| `oh-my-openagent.json` | 同上 |
| `node_modules/` | 依赖包，不应入库 |
| `bun.lock` / `package-lock.json` | 由 `*` 规则默认忽略 |
| `keys/` | 密钥目录 |
| `auto-update.log` | 运行日志 |
| `**/__pycache__/`、`**/*.pyc` | Python 缓存，不应入库 |

# VS Code 双设备 Git 分支协作同步指南

## 一、场景说明

- **设备 A（主设备）**：负责提交推送到 `main` 分支，也从 `main` 拉取
- **设备 B（本机）**：有本地改动，推送到专属分支 `local-dev`，但从 `main` 拉取更新

**核心原则**：只要不合并 `local-dev` → `main`，主仓库永远干净，本地改动不会污染远程。

---

## 二、一次性初始化（设备 B）

### 1. 创建本地分支（VS Code GUI）

左下角点击分支名（显示 `main`）→ **"创建新分支"** → 输入 `local-dev` → 回车 → **"发布分支"**

或终端执行：
```bash
git checkout -b local-dev
git push -u origin local-dev
```

---

## 三、日常操作（设备 B，全程 VS Code GUI）

### 提交并推送到 `local-dev`

源代码管理面板 → 输入提交信息 → 点 **"提交"** → 点 **"同步更改"**

> 确保左下角分支名显示 `local-dev`，推送会自动打到 `origin/local-dev`，不会碰 `main`

### 从 `main` 拉取另一台电脑的更新

源代码管理面板 → 右上角 **"..."** → **"拉取，推送"** → **"从以下位置拉取..."** → 选 `origin` → 选 `main`

或终端执行：
```bash
git fetch origin
git merge origin/main
```

---

## 四、流程图

```
设备 A 推送到 main
        ↓
设备 B："从以下位置拉取..." → origin/main（获取最新内容）
        ↓
设备 B 在 local-dev 上工作、提交
        ↓
"同步更改" → 推送到 origin/local-dev（main 完全不受影响）
```

---

## 五、白名单 .gitignore 配置

只同步部分文件，其余全部忽略：

```text
# 先忽略所有文件和目录
*

# 逐步解禁需要同步的文件（白名单）
!/.gitignore
!/scripts/
!/scripts/**
!/setting-backups/
!/setting-backups/**
!/onlyoffice-providers/
!/onlyoffice-providers/**
!/litellm-config.yaml
```

> **注意**：解禁目录时必须同时加 `!/dir/` 和 `!/dir/**`，否则目录内文件仍被忽略

---

## 六、停止追踪已提交的文件

`.gitignore` 只能忽略从未被追踪的文件，对已追踪文件无效。
如果某个文件已在仓库中但不想再同步（如 `settings.json`），需执行一次：

```bash
git rm --cached settings.json
git commit -m "stop tracking settings.json"
```

> `git rm --cached` 不会删除本地文件，只是告诉 git 停止追踪

---

## 七、常见问题

### VS Code 工作区显示不想提交的文件有改动

原因：该文件之前已被提交过，`.gitignore` 对已追踪文件无效。
解决：执行上方第六节的命令停止追踪。

### 拉取时报冲突（untracked working tree files would be overwritten）

原因：远程新增了一个文件，本地恰好有同名的未追踪文件。
解决：
```bash
mv <冲突文件> <冲突文件>.bak
git pull
# 确认无误后删除备份
rm <冲突文件>.bak
```

### 确保左下角始终显示正确分支

设备 B 日常操作前确认左下角显示 `local-dev`，不要切回 `main` 提交。

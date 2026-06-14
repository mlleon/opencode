# oh-my-openagent 版本管理指南

> 本文档整理了 oh-my-openagent 插件的版本管理、更新、检查和清理方法，解决版本卡住（如 4.8.0）或显示 "unknown" 的问题。

## 目录

- [核心概念](#核心概念)
- [版本检查](#版本检查)
- [安装方法](#安装方法)
- [更新方法](#更新方法)
- [问题排查](#问题排查)
- [旧版本清理](#旧版本清理)
- [根因分析](#根因分析)
- [预防措施](#预防措施)
- [快速参考](#快速参考)
- [参考 Issues](#参考-issues)

---

## 核心概念

### 包名重命名历史

| 旧包名 | 新包名 | 说明 |
|--------|--------|------|
| `oh-my-opencode` | `oh-my-openagent` | 项目已重命名，旧包名仍存在于某些全局安装中 |

### 三种安装位置

```
┌─────────────────────────────────────────────────────────────────┐
│                        安装位置对比                              │
├─────────────────────┬─────────────────────┬─────────────────────┤
│   bun 全局安装       │  opencode 插件安装   │   项目本地安装       │
├─────────────────────┼─────────────────────┼─────────────────────┤
│ ~/.bun/install/     │ ~/.config/opencode/ │ ~/projects/myapp/   │
│ global/             │ node_modules/       │ node_modules/       │
├─────────────────────┼─────────────────────┼─────────────────────┤
│ 所有 bun 项目       │ 所有 opencode 会话   │ 仅当前项目          │
├─────────────────────┼─────────────────────┼─────────────────────┤
│ bun add -g xxx      │ opencode plugin xxx │ bun add xxx         │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

**关键点**：
- oh-my-openagent 是 opencode 的插件，应该安装在 `~/.config/opencode/node_modules/`
- **不要**使用 `bun add -g` 全局安装，这会干扰 opencode 插件的正常工作
- `~/.config/opencode/` 是 opencode 的**全局配置目录**，不是项目目录，在任何项目下启动 opencode 都会加载这里的插件

### 为什么 bun 全局安装会干扰

```
执行: bunx oh-my-openagent get-local-version

bun 的查找顺序:
1. 先检查 ~/.bun/install/global/ → 找到 oh-my-opencode@4.0.0 (旧包名)
2. 直接使用，不再往下找
3. 旧版本代码无法识别新配置 → 显示 "unknown"

删除全局旧版本后:
1. 检查 ~/.bun/install/global/ → 未找到
2. 使用 ~/.config/opencode/node_modules/ 的版本
3. 正常显示 4.10.0
```

### 当前最新版本

**v4.10.0**（2026-06-15）

---

## 版本检查

### 快速检查（推荐）

```bash
bunx oh-my-openagent get-local-version
```

**正常输出**：
```
oh-my-openagent Version Information
──────────────────────────────────────────────────

  Current Version: 4.10.0
  Latest Version:  4.10.0

  [OK] You're up to date!
```

**异常输出 1** - 版本卡住：
```
  Current Version: 4.8.0
  Latest Version:  4.10.0

  [!] Update available
```

**异常输出 2** - 显示 unknown：
```
  Current Version: unknown

  [i] Version information unavailable
```

### 健康检查

```bash
bunx oh-my-openagent doctor
```

### 详细检查（排查问题时使用）

```bash
# 检查 opencode 插件目录版本
cat ~/.config/opencode/node_modules/oh-my-openagent/package.json | grep '"version"'

# 检查 bun 全局安装（应该为空）
bun pm ls -g | grep oh-my

# 检查缓存目录版本
cat ~/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/package.json | grep '"version"' 2>/dev/null || echo "缓存不存在"

# 检查 package.json 版本约束
cat ~/.config/opencode/package.json | grep oh-my-openagent

# 检查 bun.lock 锁定版本
grep '"oh-my-openagent":' ~/.config/opencode/bun.lock | head -3
```

### 一键检查脚本

```bash
#!/bin/bash
echo "=== 1. opencode 插件目录版本 ==="
cat ~/.config/opencode/node_modules/oh-my-openagent/package.json 2>/dev/null | grep '"version"' || echo "未找到"

echo -e "\n=== 2. bun 全局安装（应该为空）==="
bun pm ls -g 2>/dev/null | grep oh-my || echo "无全局安装（正常）"

echo -e "\n=== 3. 缓存目录版本 ==="
cat ~/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/package.json 2>/dev/null | grep '"version"' || echo "缓存不存在"

echo -e "\n=== 4. package.json 版本约束 ==="
grep oh-my-openagent ~/.config/opencode/package.json 2>/dev/null || echo "未找到"

echo -e "\n=== 5. bun.lock 锁定版本 ==="
grep -A1 '"oh-my-openagent":' ~/.config/opencode/bun.lock 2>/dev/null | head -3 || echo "未找到"
```

---

## 安装方法

### 首次安装

```bash
bunx oh-my-openagent install
```

### 非交互式安装（自动化推荐）

```bash
bunx oh-my-openagent install \
  --no-tui \
  --skip-auth \
  --claude=<no|yes|max20> \
  --gemini=<no|yes> \
  --copilot=<no|yes>
```

**示例**：
```bash
bunx oh-my-openagent install --no-tui --skip-auth --claude=yes --gemini=yes --copilot=no
```

### ⚠️ 注意事项

| ❌ 不要这样做 | ✅ 应该这样做 |
|--------------|--------------|
| `bun add -g oh-my-openagent` | `bunx oh-my-openagent install` |
| `npm install -g oh-my-openagent` | `bunx oh-my-openagent install` |
| `bunx omo install` | `bunx oh-my-openagent install` |

- `omo` 是另一个不相关的 npm 包
- 全局安装会干扰 opencode 插件机制

---

## 更新方法

### ⚠️ 为什么 `bunx oh-my-openagent install` 不会更新

根据官方 Issue [#2495](https://github.com/code-yeongyu/oh-my-openagent/issues/2495) 和 [#4318](https://github.com/code-yeongyu/oh-my-openagent/issues/4318)：

1. installer 写入精确版本（如 `oh-my-openagent@4.8.0`）
2. Auto-updater 将精确版本视为 "user-pinned"，跳过更新
3. 存在 path mismatch bug：更新写入的路径与 OpenCode 实际加载的路径不一致

### ✅ 正确的更新命令

```bash
cd ~/.config/opencode && bun update oh-my-openagent
```

### 更新后验证

```bash
bunx oh-my-openagent get-local-version
```

---

## 问题排查

### 问题 1: 版本卡住（如 4.8.0）

**症状**：`get-local-version` 显示旧版本，不是最新版

**原因**：
- 缓存目录残留旧版本（`~/.cache/opencode/packages/`）
- package.json 使用精确版本而非 `^` 前缀

**解决步骤**：

```bash
# 步骤 1: 清理缓存
rm -rf ~/.cache/opencode/packages/oh-my-openagent@latest
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-openagent*
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-opencode*

# 步骤 2: 更新到最新版
cd ~/.config/opencode && bun update oh-my-openagent

# 步骤 3: 验证
bunx oh-my-openagent get-local-version
```

### 问题 2: 显示 "unknown"

**症状**：`get-local-version` 显示 `Current Version: unknown`

**原因**：bun 全局安装了旧版本的包（`oh-my-opencode@4.0.0`）

**检查方法**：
```bash
bun pm ls -g | grep oh-my
```

**解决步骤**：

```bash
# 步骤 1: 删除 bun 全局安装的旧版本
bun remove -g oh-my-opencode

# 步骤 2: 验证
bunx oh-my-openagent get-local-version
```

### 问题 3: `bunx` 和 `bunx --bun` 结果不同

**症状**：
- `bunx oh-my-openagent get-local-version` → unknown
- `bunx --bun oh-my-openagent get-local-version` → 4.10.0

**原因**：`bunx` 默认使用 npm 缓存，`--bun` 强制使用本地 bun 环境

**建议**：先删除全局旧版本（见问题 2），之后两种命令都会返回正确结果

---

## 旧版本清理

### 清理位置清单

| # | 位置 | 路径 | 可能残留 | 检查命令 |
|---|------|------|----------|----------|
| 1 | bun 全局安装 | `~/.bun/install/global/` | `oh-my-opencode@4.0.0` | `bun pm ls -g \| grep oh-my` |
| 2 | npm 全局安装 | `~/.nvm/...` | 旧版本 | `npm list -g \| grep oh-my` |
| 3 | opencode 插件目录 | `~/.config/opencode/node_modules/` | 旧版本 | `ls ~/.config/opencode/node_modules/ \| grep oh-my` |
| 4 | opencode 缓存 | `~/.cache/opencode/packages/` | 4.7.5, 4.8.0 | `find ~/.cache/opencode -name "*oh-my*" -type d` |
| 5 | bun 缓存 | `~/.bun/install/cache/` | 4.7.5, 4.8.0 | `find ~/.bun/install/cache -name "*oh-my*" -type d` |
| 6 | npm 缓存 | `~/.npm/_npx/` | `oh-my-opencode` | `find ~/.npm -name "*oh-my*" -type d` |
| 7 | tmp 目录 | `/tmp/` | 日志、临时文件 | `find /tmp -name "*oh-my*"` |

### 一键检查脚本

```bash
#!/bin/bash
echo "=== oh-my-openagent 旧版本残留检查 ==="
echo ""

echo "1. bun 全局安装:"
result=$(bun pm ls -g 2>/dev/null | grep oh-my)
[ -z "$result" ] && echo "   ✅ 无" || echo "   ❌ $result"

echo ""
echo "2. npm 全局安装:"
result=$(npm list -g 2>/dev/null | grep oh-my)
[ -z "$result" ] && echo "   ✅ 无" || echo "   ❌ $result"

echo ""
echo "3. opencode 插件目录:"
if [ -f ~/.config/opencode/node_modules/oh-my-openagent/package.json ]; then
  version=$(grep '"version"' ~/.config/opencode/node_modules/oh-my-openagent/package.json | head -1)
  echo "   $version"
else
  echo "   ⚠️ 未找到"
fi

echo ""
echo "4. opencode 缓存:"
result=$(find ~/.cache/opencode -name "*oh-my*" 2>/dev/null | wc -l)
[ "$result" -eq 0 ] && echo "   ✅ 无残留" || echo "   ❌ $result 个文件/目录"

echo ""
echo "5. bun 缓存 (旧版本):"
result=$(find ~/.bun/install/cache -name "*oh-my-opencode*" -o -name "*oh-my-openagent@4.7*" -o -name "*oh-my-openagent@4.8*" 2>/dev/null | wc -l)
[ "$result" -eq 0 ] && echo "   ✅ 无旧版本" || echo "   ❌ $result 个旧版本文件"

echo ""
echo "6. npm 缓存:"
result=$(find ~/.npm -name "*oh-my*" 2>/dev/null | wc -l)
[ "$result" -eq 0 ] && echo "   ✅ 无" || echo "   ❌ $result 个文件"

echo ""
echo "7. /tmp 残留:"
result=$(find /tmp -name "*oh-my*" 2>/dev/null | wc -l)
[ "$result" -eq 0 ] && echo "   ✅ 无" || echo "   ❌ $result 个文件"

echo ""
echo "8. 版本验证:"
bunx oh-my-openagent get-local-version 2>&1 | grep -E "Current|Latest|OK|unknown"
```

### 一键清理脚本

```bash
#!/bin/bash
echo "=== oh-my-openagent 旧版本清理 ==="
echo ""

echo "1. 清理 bun 全局安装..."
bun remove -g oh-my-opencode 2>/dev/null && echo "   ✅ 已删除" || echo "   ⏭️ 无需清理"

echo ""
echo "2. 清理 opencode 缓存..."
rm -rf ~/.cache/opencode/packages/oh-my-openagent@latest
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-openagent*
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-opencode*
rm -f ~/.cache/opencode/packages/node_modules/.bin/oh-my-opencode
rm -f ~/.cache/opencode/packages/node_modules/.bin/oh-my-openagent
echo "   ✅ 已清理"

echo ""
echo "3. 清理 bun 缓存旧版本..."
rm -rf ~/.bun/install/cache/oh-my-opencode*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.8.0*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.8.0*
echo "   ✅ 已清理"

echo ""
echo "4. 清理 npm 缓存..."
rm -rf ~/.npm/_npx/*/node_modules/oh-my-opencode
echo "   ✅ 已清理"

echo ""
echo "5. 清理 /tmp 残留..."
rm -f /tmp/oh-my-opencode.log
rm -rf /tmp/bunx-*-oh-my-openagent@*
echo "   ✅ 已清理"

echo ""
echo "=== 清理完成，验证结果 ==="
echo ""
bunx oh-my-openagent get-local-version
```

### 分步清理（手动执行）

#### 步骤 1: 清理 bun 全局安装

```bash
# 检查
bun pm ls -g | grep oh-my

# 如果有旧版本，删除
bun remove -g oh-my-opencode
```

#### 步骤 2: 清理 opencode 缓存

```bash
rm -rf ~/.cache/opencode/packages/oh-my-openagent@latest
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-openagent*
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-opencode*
rm -f ~/.cache/opencode/packages/node_modules/.bin/oh-my-opencode
rm -f ~/.cache/opencode/packages/node_modules/.bin/oh-my-openagent
```

#### 步骤 3: 清理 bun 缓存旧版本

```bash
# 删除旧版本 (4.7.5, 4.8.0)
rm -rf ~/.bun/install/cache/oh-my-opencode*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.8.0*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.8.0*
```

#### 步骤 4: 清理 npm 缓存

```bash
rm -rf ~/.npm/_npx/*/node_modules/oh-my-opencode
```

#### 步骤 5: 清理 /tmp 残留

```bash
rm -f /tmp/oh-my-opencode.log
rm -rf /tmp/bunx-*-oh-my-openagent@*
```

#### 步骤 6: 验证清理结果

```bash
# 验证全局安装已清理
bun pm ls -g | grep oh-my  # 应无输出

# 验证缓存已清理
find ~/.cache/opencode -name "*oh-my*" 2>/dev/null | wc -l  # 应为 0

# 验证 bun 缓存旧版本已清理
find ~/.bun/install/cache -name "*oh-my-opencode*" 2>/dev/null | wc -l  # 应为 0

# 验证版本
bunx oh-my-openagent get-local-version  # 应显示最新版本
```

### 完整重置（最后手段）

如果上述清理后仍有问题，执行完整重置：

```bash
# 1. 清理所有残留（使用上面的一键清理脚本）

# 2. 删除 opencode 插件目录
rm -rf ~/.config/opencode/node_modules/oh-my-openagent*

# 3. 重新安装
cd ~/.config/opencode && bun update oh-my-openagent

# 4. 验证
bunx oh-my-openagent get-local-version
```

### 实际清理案例（2026-06-15）

**清理前状态**：

| 位置 | 发现的问题 |
|------|-----------|
| bun 全局安装 | `oh-my-opencode@4.0.0` |
| opencode 缓存 | bin 符号链接残留 |
| bun 缓存 | 4.7.5, 4.8.0, 4.10.0 混合 |
| npm 缓存 | `oh-my-opencode` |
| /tmp | `oh-my-opencode.log` |

**执行的清理命令**：

```bash
# 1. 删除 bun 全局旧版本
bun remove -g oh-my-opencode

# 2. 清理 opencode 缓存
rm -rf ~/.cache/opencode/packages/oh-my-openagent@latest
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-openagent*
rm -rf ~/.cache/opencode/packages/node_modules/oh-my-opencode*

# 3. 清理 bun 缓存旧版本
rm -rf ~/.bun/install/cache/oh-my-opencode*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent@4.8.0*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.7.5*
rm -rf ~/.bun/install/cache/oh-my-openagent-linux-*@4.8.0*

# 4. 清理 npm 缓存
rm -rf ~/.npm/_npx/*/node_modules/oh-my-opencode

# 5. 清理 /tmp
rm -f /tmp/oh-my-opencode.log
rm -rf /tmp/bunx-*-oh-my-openagent@*
```

**清理后状态**：

| 位置 | 状态 |
|------|------|
| bun 全局安装 | ✅ 无 |
| npm 全局安装 | ✅ 无 |
| opencode 插件目录 | ✅ 4.10.0 |
| opencode 缓存 | ✅ 已清理 |
| bun 缓存 | ✅ 仅保留 4.10.0 |
| npm 缓存 | ✅ 已清理 |
| /tmp | ✅ 已清理 |
| 版本验证 | ✅ 4.10.0 |

---

## 根因分析

### 版本卡住的 4 个原因

| 原因 | 位置 | 说明 |
|------|------|------|
| 1. 缓存目录残留旧版本 | `~/.cache/opencode/packages/` | OpenCode 可能从缓存加载旧版本 |
| 2. 自动更新机制损坏 | - | installer 锁定精确版本，auto-updater 跳过更新 |
| 3. Path mismatch bug | - | 更新写入路径与实际加载路径不一致 |
| 4. package.json 版本约束 | `~/.config/opencode/package.json` | 使用精确版本而非 `^` 前缀 |

### 显示 "unknown" 的原因

| 原因 | 位置 | 说明 |
|------|------|------|
| bun 全局安装旧版本 | `~/.bun/install/global/` | 旧包名 `oh-my-opencode@4.0.0` 干扰 |

### 版本加载优先级

```
bun 全局安装 > opencode 缓存 > opencode 插件目录
~/.bun/        ~/.cache/         ~/.config/opencode/
install/global/ opencode/         node_modules/
```

---

## 预防措施

### 1. 不要全局安装

```bash
# ❌ 不要这样做
bun add -g oh-my-openagent
bun add -g oh-my-opencode

# ✅ 应该这样做
bunx oh-my-openagent install
```

### 2. 使用 `^` 前缀的版本约束

确保 `~/.config/opencode/package.json` 中：
```json
{
  "dependencies": {
    "oh-my-openagent": "^4.10.0"
  }
}
```

### 3. 更新后立即验证

每次更新后执行：
```bash
bunx oh-my-openagent get-local-version
```

### 4. 定期检查全局安装

```bash
bun pm ls -g | grep oh-my
# 应无输出，如果有则删除
```

### 5. 使用正确的更新命令

**永远使用**：
```bash
cd ~/.config/opencode && bun update oh-my-openagent
```

**不要使用**：
- `bunx oh-my-openagent install`（不会更新实际加载的版本）
- 依赖自动更新（已损坏）

---

## 快速参考

### 常用命令速查

| 操作 | 命令 |
|------|------|
| 检查版本 | `bunx oh-my-openagent get-local-version` |
| 健康检查 | `bunx oh-my-openagent doctor` |
| 更新插件 | `cd ~/.config/opencode && bun update oh-my-openagent` |
| 检查全局安装 | `bun pm ls -g \| grep oh-my` |
| 删除全局旧版本 | `bun remove -g oh-my-opencode` |
| 清理缓存 | `rm -rf ~/.cache/opencode/packages/oh-my-openagent@latest ~/.cache/opencode/packages/node_modules/oh-my-openagent* ~/.cache/opencode/packages/node_modules/oh-my-opencode*` |
| 完整重置 | `rm -rf ~/.cache/opencode/{bun.lock,package.json,node_modules} && cd ~/.config/opencode && bun update oh-my-openagent` |

### 版本信息

| 项目 | 值 |
|------|-----|
| GitHub 仓库 | [code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) |
| 旧包名 | `oh-my-opencode`（已重命名） |
| 新包名 | `oh-my-openagent`（当前使用） |
| 当前最新版本 | v4.10.0 |
| 官方安装命令 | `bunx oh-my-openagent install` |
| 正确更新命令 | `cd ~/.config/opencode && bun update oh-my-openagent` |

### 安装位置速查

| 位置 | 路径 | 用途 |
|------|------|------|
| opencode 插件目录 | `~/.config/opencode/node_modules/` | 插件实际安装位置（✅ 正确） |
| opencode 缓存 | `~/.cache/opencode/packages/` | 插件缓存（可能残留旧版本） |
| bun 全局安装 | `~/.bun/install/global/` | bun 全局包（❌ 不应该有 oh-my-openagent） |
| bun 缓存 | `~/.bun/install/cache/` | bun 包缓存（可能残留旧版本） |
| npm 缓存 | `~/.npm/_npx/` | npx 缓存（可能残留旧版本） |
| tmp 目录 | `/tmp/` | 临时文件和日志 |

### 一键脚本速查

| 脚本 | 用途 | 位置 |
|------|------|------|
| 一键检查脚本 | 检查所有 7 个位置的残留 | 见[旧版本清理](#一键检查脚本) |
| 一键清理脚本 | 清理所有旧版本残留 | 见[一键清理脚本](#一键清理脚本) |

---

## 参考 Issues

| Issue | 描述 | 状态 |
|-------|------|------|
| [#2495](https://github.com/code-yeongyu/oh-my-openagent/issues/2495) | 自动更新损坏，临时方案见官方维护者 @acamq 的回复 | Open |
| [#4318](https://github.com/code-yeongyu/oh-my-openagent/issues/4318) | Auto-update 写入错误路径，导致版本永远不切换 | Open |
| [#4734](https://github.com/code-yeongyu/oh-my-openagent/issues/4734) | 版本锁定损坏：配置指定旧版本但实际加载新版本 | Open |
| [#4451](https://github.com/code-yeongyu/oh-my-openagent/issues/4451) | 全局 CLI 版本与运行版本不匹配 | Open |
| [#3660](https://github.com/code-yeongyu/oh-my-openagent/issues/3660) | 插件重新安装后仍显示 unknown | Open |
| [#3662](https://github.com/code-yeongyu/oh-my-openagent/issues/3662) | 插件和 Agent 更新工具的 Feature Request | Open |
| [#4735](https://github.com/code-yeongyu/oh-my-openagent/issues/4735) | 缺少统一的 `update` 命令，正在规划中 | Open |

---

*文档创建时间：2026-06-15*
*最后更新：2026-06-15（添加完整清理流程和实际案例）*
*基于 oh-my-openagent v4.10.0*

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

绑定关系建立好后，日常同步的关键不是死记命令，而是先判断三件事：

1. **我本地有没有改动？** 用 `git status` 看。
2. **本地改动要不要保留？** 要保留就 `commit` 或 `stash`，不要保留就 `restore` 或 `reset --hard`。
3. **远程有没有别人/另一台设备推送的新内容？** 用 `git fetch` 或 VS Code 自动 fetch 看。

> 小白安全原则：不确定本地修改要不要时，优先用 `git stash` 临时保存；不要一上来就 `git reset --hard`。

### 快速选择表

| 我现在想做什么 | 优先用哪个命令 | 会发生什么 | 主要风险 |
| --- | --- | --- | --- |
| 开始工作前先同步远程 | `git pull --rebase --autostash` | 自动临时保存本地修改、拉取远程、再恢复本地修改 | 两边改同一段时仍可能冲突 |
| 确定本地没有修改，只想拉远程 | `git pull --rebase` | 把远程新提交同步到本地 | 工作区不干净时会报错 |
| 本地修改要保留，但还不想提交 | `git stash push -u -m "before pull"` | 把本地修改临时收起来，之后可恢复 | `stash pop` 恢复时可能冲突 |
| 本地修改要同步给其他设备 | `git add` + `git commit` + `git push` | 把本地修改变成远程可拉取的正式版本 | 可能误提交密钥或本机私有配置 |
| 只想丢弃某几个文件的本地修改 | `git restore <文件>` | 指定文件回到上一次提交状态 | 指定文件的未提交修改会丢失 |
| 本地公共文件全乱了，想完全以远程为准 | `git fetch origin` + `git reset --hard origin/master` | 所有已追踪公共文件强制对齐远程 | 会丢弃所有已追踪文件的本地修改 |
| pull/rebase 冲突了，想继续 | `git add <文件>` + `git rebase --continue` | 标记冲突已解决并继续同步 | 冲突没处理干净会留下错误内容 |
| rebase 搞乱了，想退回操作前 | `git rebase --abort` | 取消本次 rebase，回到开始前 | 只适用于正在 rebase 的状态 |

---

### 1. 最推荐的日常开始方式：自动临时保存后拉取

每天开始改配置或代码前，建议先执行：

```bash
git pull --rebase --autostash
```

* **适用场景**：
  * 本地可能有一点没提交的修改，但你想先同步远程最新内容。
  * 你不确定 VS Code 或工具是否自动格式化过文件。
  * 远程分支有更新，本地也可能有工作区改动。
* **效果说明**：
  * **本地没有修改**：直接拉取远程最新内容。
  * **本地有未提交修改**：Git 会先自动临时保存这些修改，再拉取远程，最后自动把本地修改放回来。
  * **远程和本地改了不同位置**：通常可以自动成功。
  * **远程和本地改了同一位置**：可能出现冲突，需要手动解决。
* **风险提醒**：
  * `--autostash` 不是万能保险，只是自动帮你做一次临时保存。
  * 如果最后自动恢复本地修改时冲突，仍然要人工判断保留哪一边。
* **后续动作**：
  * 成功后继续工作即可。
  * 如果出现冲突，跳到「五、常见问题与防错指南」里的冲突处理部分。

---

### 2. 确定本地没有修改：普通拉取

先检查：

```bash
git status
```

如果显示 `working tree clean` 或没有 modified 文件，再执行：

```bash
git pull --rebase
```

* **适用场景**：
  * 你只是想把另一台设备已经 push 的内容同步过来。
  * 当前设备没有任何本地修改。
* **效果说明**：
  * **远程有新提交**：本地公共文件更新到远程最新版。
  * **远程没有新提交**：提示已经是最新，不会改变文件。
  * **本地特有未追踪文件**：例如 `/keys/` 里的密钥文件，不会被 Git 修改或上传。
* **风险提醒**：
  * 如果本地其实有未提交修改，`pull --rebase` 可能报错：`cannot pull with rebase: You have unstaged changes`。
* **后续动作**：
  * 报错时不要慌，先执行 `git status` 看哪些文件被改了，再按下面第 3、4、5 种场景处理。

---

### 3. 本地修改要保留，但暂时不想提交：stash 后拉取

```bash
git stash push -u -m "before pull"
git pull --rebase
git stash pop
```

* **适用场景**：
  * 本地有未完成的修改。
  * 你还不想 commit，但又需要先同步远程。
  * 拉取时报 `cannot pull with rebase: You have unstaged changes`。
* **效果说明**：
  * `git stash push -u`：把本地已追踪文件的修改、以及未追踪文件一起临时收起来。
  * `git pull --rebase`：在干净工作区上拉取远程最新内容。
  * `git stash pop`：把刚才临时保存的本地修改重新放回工作区。
* **风险提醒**：
  * 如果远程和本地改了同一个位置，`stash pop` 可能产生冲突。
  * `stash pop` 成功后会自动删除这条 stash；如果担心误删，可以用 `git stash apply` 代替 `git stash pop`。
* **后续动作**：
  * 成功后继续修改。
  * 如果冲突，解决冲突后执行 `git add <文件>`。
  * 如果想查看还保存了哪些 stash：`git stash list`。

---

### 4. 本地修改已经确定要保留并同步给其他设备：提交后拉取再推送

```bash
git status
git add <要同步的文件>
git commit -m "Update config"
git pull --rebase
git push
```

* **适用场景**：
  * 这台设备的修改是正式修改，另一台设备以后也需要用。
  * 修改的是白名单公共文件，例如 `.gitignore`、`opencode.json`、`oh-my-openagent.json`、`skills/`、`bakeup/`。
* **效果说明**：
  * `git add`：选择哪些文件进入这次提交。
  * `git commit`：把本地修改保存成一个 Git 版本。
  * `git pull --rebase`：先把远程别人/另一台设备的新提交接到本地提交前面，避免历史分叉。
  * `git push`：把本地提交上传到 GitHub，其他设备才能拉取到。
* **风险提醒**：
  * 不要 `git add .` 前不看 `git status`，否则可能把不该同步的文件加入提交。
  * 密钥、私有 token、本机专属配置不要提交。
* **后续动作**：
  * 另一台设备执行 `git pull --rebase` 或 `git pull --rebase --autostash` 即可同步。

---

### 5. 本地修改不要了：只丢弃指定文件后拉取

如果 `git status` 显示只有某几个公共文件被误改，例如：

```text
modified: oh-my-openagent.json
modified: opencode.json
```

并且确认这些本地改动不要了，可以执行：

```bash
git restore oh-my-openagent.json opencode.json
git pull --rebase
```

* **适用场景**：
  * 本地只是格式化、字段顺序变化、误触保存。
  * 你明确想放弃某几个文件的本地修改。
  * 想解决 `cannot pull with rebase: You have unstaged changes`。
* **效果说明**：
  * **指定文件**：恢复到当前本地 `HEAD` 版本，也就是撤销这些文件的未提交修改。
  * **其他文件**：不会受影响。
  * **本地特有未追踪文件**：不会受影响。
* **风险提醒**：
  * 被 `git restore <文件>` 丢弃的未提交修改通常不好恢复。
  * 不确定时先用 `git diff <文件>` 看差异，或先用 `git stash` 保存。
* **后续动作**：
  * 工作区干净后，再执行 `git pull --rebase`。

---

### 6. 强力“一键对齐远程”：放弃所有已追踪文件的本地修改

如果本地公共文件改乱了，并且你想让本地完全回到 GitHub 远程最新版：

```bash
git fetch origin
git reset --hard origin/master
```

* **适用场景**：
  * 本地公共文件被工具自动改乱。
  * 你确定本地对已追踪文件的修改全部不要了。
  * 想让当前设备重新以 GitHub 远程为准。
* **效果说明**：
  * **Git 已追踪的公共文件**：全部强制变成 `origin/master` 的版本。
  * **本地未提交的公共文件修改**：全部丢弃。
  * **本地特有未追踪文件**：例如被 `.gitignore` 忽略的 `/keys/`，不会被 `reset --hard` 删除。
  * **远程没有、本地也没被 Git 追踪的文件**：会继续留在本地。
* **风险提醒**：
  * 这是高风险命令，会丢弃所有已追踪文件的本地修改。
  * 执行前建议先 `git status` 和 `git diff`，确认没有要保留的内容。
  * 如果不确定，先备份整个目录，或先执行 `git stash push -u -m "backup before hard reset"`。
* **后续动作**：
  * 执行后用 `git status` 确认状态。
  * 如果发现误丢修改，立即停止操作，尝试从备份或 stash 找回。

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

遇到任何 Git 报错时，先不要急着执行破坏性命令。建议先复制执行下面三条诊断命令：

```bash
git status --short --branch
git diff --stat
git stash list
```

* **效果说明**：
  * `git status --short --branch`：查看当前分支、是否落后远程、本地有哪些文件被改了。
  * `git diff --stat`：查看本地修改规模，方便判断是小改动还是大范围变化。
  * `git stash list`：查看以前是否临时保存过修改，防止误以为文件丢了。
* **风险提醒**：
  * 这三条都是只读或查看类命令，不会修改文件。
  * 如果你不确定下一步怎么做，先保存这三条命令的输出再判断。

---

### 1. 报错：`cannot pull with rebase: You have unstaged changes`

```text
error: cannot pull with rebase: You have unstaged changes.
error: please commit or stash them.
```

* **场景**：
  * 执行 `git pull`、VS Code 点击同步、或自动更新时失败。
  * 当前仓库配置了 `pull.rebase=true`，但工作区里有未提交修改。
* **原因**：
  * rebase 需要一个干净工作区。
  * Git 不知道你本地未提交的内容要不要保留，所以拒绝继续。

#### 方案 A：本地修改要保留，但暂时不提交

```bash
git stash push -u -m "before pull"
git pull --rebase
git stash pop
```

* **效果说明**：
  * 本地修改会先临时收起来。
  * 远程更新会被拉取下来。
  * 最后本地修改会重新放回当前工作区。
* **风险提醒**：
  * 如果两边改了同一段，`git stash pop` 可能冲突。
  * 不确定时可以把最后一步改成 `git stash apply`，这样 stash 不会自动删除。

#### 方案 B：本地修改已经确定要同步给其他设备

```bash
git add <要同步的文件>
git commit -m "Update config"
git pull --rebase
git push
```

* **效果说明**：
  * 本地修改会变成正式提交。
  * `pull --rebase` 会把远程新提交接到本地提交之前。
  * `push` 后其他设备才能拉到这次修改。
* **风险提醒**：
  * 不要把密钥、token、本机私有配置提交上去。
  * 执行 `git add` 前先看 `git status`，只添加你确定要同步的文件。

#### 方案 C：本地修改不要了，只丢弃指定文件

```bash
git restore <文件1> <文件2>
git pull --rebase
```

例如：

```bash
git restore oh-my-openagent.json opencode.json
git pull --rebase
```

* **效果说明**：
  * 只撤销指定文件的未提交修改。
  * 其他文件不受影响。
  * 本地未追踪文件不受影响。
* **风险提醒**：
  * 指定文件里的未提交内容会丢失。
  * 不确定时先执行 `git diff <文件>` 看看改了什么。

---

### 2. 报错：`The following untracked working tree files would be overwritten by merge`

```text
error: The following untracked working tree files would be overwritten by merge:
  path/to/file
Please move or remove them before you merge.
```

* **场景**：
  * 设备 A 把一个新文件提交到了 GitHub。
  * 设备 B 本地刚好也有同名文件，但这个文件在设备 B 上是未追踪文件。
  * 白名单规则更新后，原本被忽略的文件开始被 Git 追踪，也容易遇到这个问题。
* **原因**：
  * Git 不会直接覆盖本地未追踪文件，因为它担心你本地文件还没备份。

#### 推荐方案：先备份同名文件，再拉取

```bash
mv path/to/file path/to/file.local-backup
git pull --rebase
```

确认远程版本没问题后：

```bash
rm path/to/file.local-backup
```

如果本地备份里有需要保留的内容，就手动复制到拉取后的文件里。

* **效果说明**：
  * 本地同名未追踪文件会被先改名保留。
  * Git 可以顺利把远程同名文件拉下来。
  * 你可以事后对比 `.local-backup` 和远程版本。
* **风险提醒**：
  * 不要直接 `rm`，除非你确定本地同名文件完全不要。
  * 如果路径很多，先逐个处理，不要批量删除。

---

### 3. 两台设备都改了同一个公共文件

* **场景**：
  * 设备 A 改了 `opencode.json` 并 push。
  * 设备 B 也改了 `opencode.json`，再 pull 时出错或冲突。
* **推荐流程**：

```bash
git status
git stash push -u -m "before resolving two-device changes"
git pull --rebase
git stash pop
```

如果出现冲突，打开冲突文件，会看到类似：

```text
  <<<<<<< Updated upstream
远程版本
  =======
本地版本
  >>>>>>> Stashed changes
```

手动编辑成最终想要的内容，删除 `<<<<<<<`、`=======`、`>>>>>>>` 这些标记，然后执行：

```bash
git add <冲突文件>
git status
```

* **效果说明**：
  * 远程修改和本地修改都会展示出来。
  * 你可以人工选择保留远程、本地，或合并两边内容。
* **风险提醒**：
  * 冲突文件里不能保留 `<<<<<<<` 这些标记，否则配置文件通常会损坏。
  * JSON 文件解决后，建议用工具格式化或校验 JSON 是否有效。
* **后续动作**：
  * 如果这次冲突来自 `git pull --rebase`，解决并 `git add` 后执行 `git rebase --continue`。
  * 如果只是 `git stash pop` 后冲突，解决并 `git add` 后再按需 commit。

---

### 4. rebase 过程中冲突，不知道怎么继续

执行 `git status`，如果看到类似：

```text
You are currently rebasing branch 'master' on 'xxxxxxx'.
```

说明当前处于 rebase 中。

#### 继续 rebase

```bash
git status
# 手动解决冲突文件
git add <已解决的文件>
git rebase --continue
```

* **效果说明**：
  * Git 会继续把本地提交接到远程最新提交后面。
  * 如果还有下一个冲突，会继续停下来让你解决。
* **风险提醒**：
  * 不要在冲突没解决完时乱 `push`。
  * 每解决一个冲突文件，都要 `git add <文件>` 告诉 Git 已处理。

#### 放弃这次 rebase，回到操作前

```bash
git rebase --abort
```

* **效果说明**：
  * 取消当前 rebase。
  * 分支会尽量恢复到 rebase 开始前的状态。
* **风险提醒**：
  * 这是退出当前 rebase 的安全方式。
  * 不要用 `git reset --hard` 代替 `git rebase --abort`，除非你明确知道会丢什么。

---

### 5. 不小心 stash 后，文件好像“消失了”

```bash
git stash list
git stash show --stat stash@{0}
git stash apply stash@{0}
```

* **场景**：
  * 执行过 `git stash` 或 `git pull --rebase --autostash`。
  * 之后发现本地修改不见了。
* **效果说明**：
  * `git stash list`：列出所有临时保存记录。
  * `git stash show --stat stash@{0}`：查看最近一条 stash 里有哪些文件。
  * `git stash apply stash@{0}`：把这条 stash 重新应用回来，但不删除 stash 记录。
* **风险提醒**：
  * `git stash pop` 会应用并删除 stash；新手更建议先用 `apply`。
  * 如果 apply 后确认没问题，再执行 `git stash drop stash@{0}` 删除对应 stash。

---

### 6. VS Code 显示有同步按钮，但点了失败

* **场景**：
  * VS Code 源代码管理里显示同步、拉取或推送按钮。
  * 点击后失败，但错误提示不够清楚。
* **推荐处理**：

```bash
git status --short --branch
git pull --rebase --autostash
```

* **效果说明**：
  * 先用命令行看清楚当前分支和本地修改。
  * 再用 `--autostash` 尝试更稳妥地拉取。
* **风险提醒**：
  * VS Code 按钮背后仍然是 Git 命令。
  * 报错时不要反复点同步按钮，先看 `git status`。

---

### 7. `.gitignore` 白名单同步后，另一台设备行为变化

* **场景**：
  * 一台设备修改了 `.gitignore`，例如新增 `!/bakeup/**` 或 `!/skills/**`。
  * 另一台设备 pull 后，原本忽略的文件开始出现在 Git 状态里。
* **效果说明**：
  * `.gitignore` 是公共规则，只要被提交并 push，其他设备拉取后也会生效。
  * 新白名单里的文件可能从“本地私有文件”变成“公共同步文件”。
* **风险提醒**：
  * 白名单规则改变前，先确认不会把密钥、token、本机私有配置纳入追踪。
  * 如果某个文件已经被 Git 追踪，之后再写进 `.gitignore` 也不会自动取消追踪。
* **后续动作**：
  * 如果需要取消追踪但保留本地文件，使用：

```bash
git rm --cached <文件>
git commit -m "Stop tracking local-only file"
git push
```

* **效果说明**：
  * `git rm --cached`：只从 Git 追踪列表中移除，不删除本地文件。
  * commit/push 后，其他设备也会知道这个文件不再作为公共文件同步。

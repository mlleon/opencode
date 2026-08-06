# tmux 实战手册（WSL/Linux · AI Coding 版）

> **适用环境**：WSL2（Ubuntu 等）· Linux · Windows Terminal（作为 WSL 前端）· OpenCode · Codex CLI · Claude Code
>
> 本手册讲 tmux 基础操作、配置、以及「手机 SSH 远程」场景下的滚动与复制。**手机远程连接 WSL 的部署见 [手机Termux连WSL部署手册.md](手机Termux连WSL部署手册.md)。** Windows Terminal 与 VS Code Remote-WSL 仅作为访问 WSL 的前端工具说明，不展开其他操作系统。

---

## 快速速查（Cheat Sheet）

> 最常用的命令，遇到忘记先查这里。

> **关于前缀键 `Ctrl+b`**：tmux 快捷键都是两段式——先按住 `Ctrl` 同时按 `b`，**松开**，再按功能键。不是三个键一起按。

| 写法         | 实际操作                      |
| ------------ | ----------------------------- |
| `Ctrl+b c` | 按`Ctrl+b` 松开 → 按 `c` |
| `Ctrl+b d` | 按`Ctrl+b` 松开 → 按 `d` |
| `Ctrl+b ,` | 按`Ctrl+b` 松开 → 按 `,` |
| `Ctrl+b 1` | 按`Ctrl+b` 松开 → 按 `1` |
| `Ctrl+b [` | 按`Ctrl+b` 松开 → 按 `[` |

### Session

| 功能               | 操作                                   |
| ------------------ | -------------------------------------- |
| 创建/进入工作区    | `entry <项目名>`（推荐，见第七章）     |
| 创建 Session       | `tmux new -s <name>`                   |
| 临时退出（Detach） | `Ctrl+b d`                             |
| 查看所有 Session   | `tmux ls`                              |
| 进入 Session       | `tmux attach -t <name>`                |
| 重命名 Session     | `tmux rename-session -t <old> <new>`   |
| 删除 Session       | `tmux kill-session -t <name>`          |
| 删除所有 Session   | `tmux kill-server`                     |

### Window

| 功能                | 操作                          |
| ------------------- | ----------------------------- |
| 新建 Window         | `Ctrl+b c`                  |
| 查看所有 Window     | `Ctrl+b w`                  |
| 切换到编号 N        | `Ctrl+b N`（0~9）           |
| 下一个 Window       | `Ctrl+b n`                  |
| 上一个 Window       | `Ctrl+b p`                  |
| 重命名 Window       | `Ctrl+b ,`                  |
| 创建指定名称 Window | `tmux new-window -n <name>` |
| 关闭 Window         | `exit`                      |

### Pane

| 功能      | 操作              |
| --------- | ----------------- |
| 左右分屏  | `Ctrl+b %`      |
| 上下分屏  | `Ctrl+b "`      |
| 切换 Pane | `Ctrl+b 方向键` |
| 关闭 Pane | `exit`          |

### Copy Mode（vi 模式）

| 功能            | 键                        |
| --------------- | ------------------------- |
| 进入 Copy Mode  | `Ctrl+b [`              |
| 搜索            | `/`                     |
| 下一个 / 上一个 | `n` / `N`             |
| 开始选择        | `v`                     |
| 复制并退出      | `y`                     |
| 翻页            | `PageUp` / `PageDown` |
| 跳顶 / 跳底     | `g` / `G`             |
| 退出            | `q`                     |

> ⚠️ **电脑端复制不用 Copy Mode**，直接鼠标拖选即可（写 Windows 剪贴板）。手机端用「长按选文字」。详见第九章。

### OpenCode 键盘速查

| 功能        | 快捷键         | 说明                                     |
| ----------- | -------------- | ---------------------------------------- |
| 停止 Agent  | `Esc`        | 需配置`escape-time 10`                 |
| 换行 / 发送 | `Ctrl+Enter` | `Alt+Enter` 在 Windows Terminal 不可用 |

---

## 一、tmux 是什么

tmux（Terminal Multiplexer）是终端复用器，核心价值：

> **关闭终端窗口后，里面运行的程序仍然继续运行。**

对 AI Coding 至关重要——OpenCode、Codex、Claude Code 通常需要长时间运行，不能因为关闭 Windows Terminal 或断开 Remote-WSL 就中断。

```
Windows Terminal / VS Code（可以关闭）
        │
        ▼
      tmux Server（独立运行）
        │
        ▼
 OpenCode / Codex / Claude Code（不受影响）
```

重新连接：

```bash
tmux attach -t <session-name>
```

即可恢复之前的全部状态。

> **边界**：tmux 能抵抗「终端关闭 / VS Code Remote 断开 / SSH 断线」，无法跨越「WSL 关闭 / 系统重启」。`wsl --shutdown` 或重启 Windows 后 tmux Server 结束。

---

## 二、安装

```bash
sudo apt update && sudo apt install tmux

# 验证
tmux -V          # 例如：tmux 3.4
which tmux       # /usr/bin/tmux
```

---

## 三、三大核心概念

```
tmux Server
├── Session（项目）
│      ├── Window（AI Agent / 终端）
│      │      └── Pane（分屏）
│      └── Window
└── Session
```

| 层级    | 类比         | 推荐用途                      |
| ------- | ------------ | ----------------------------- |
| Session | 一个项目     | 一个项目对应一个 Session      |
| Window  | 一个独立终端 | 一个 AI Agent 对应一个 Window |
| Pane    | 终端内的分屏 | 临时查看日志、辅助命令        |

**核心原则：项目放 Session，AI Agent 放 Window。**

记忆口诀：

```
Session = 项目
Window  = AI Agent
Pane    = 分屏
```

推荐架构：

```
tmux Server
├── Session：llm-broker
│      ├── Window 0：Shell
│      ├── Window 1：OpenCode
│      ├── Window 2：Codex
│      └── Window 3：Claude Code
│
├── Session：router-api
│      ├── Window 0：Shell
│      └── Window 1：OpenCode
│
└── Session：poetry-video
       ├── Window 0：Shell
       └── Window 1：Codex
```

不推荐（AI 工具不应作为 Session 粒度）：

```
Session：OpenCode    ← ❌
Session：Codex
Session：Claude
```

---

## 四、Session 管理（tmux 会话）

### 创建 Session

> 日常推荐用 `entry <项目名>` 一键创建/进入工作区（自动建四窗口，见第七章）。下面手动方式用于理解原理或没装脚本时。

建议先进入项目目录再创建，tmux 会继承当前工作目录，新建的 Window 也会继承：

```bash
cd ~/workspace/llm-broker
tmux new -s llm-broker
```

进入后直接启动 AI Agent：

```bash
opencode    # 或 codex / claude
```

### 查看 / 进入 Session

```bash
tmux ls                       # 列出所有 Session
tmux attach -t llm-broker     # 进入指定 Session
tmux a                        # 若只有一个 Session，直接进入
```

### 临时退出（Detach）

```
Ctrl+b  →  松开  →  d
```

程序继续运行，之后通过 `tmux attach` 恢复。

> 正确顺序：按住 `Ctrl` → 按 `b` → 松开 → 再按 `d`，不是同时按。

### 重命名 Session

```bash
tmux rename-session -t opencode llm-broker
```

不中断任何运行中的程序，只改名称。可从任意目录执行（操作的是 tmux Server 内部状态，与当前目录无关）。

### 删除 Session

```bash
# 在 Session 内关闭最后一个 Window 时自动删除
exit

# 或从外部强制删除
tmux kill-session -t llm-broker

# 删除全部（谨慎，一般重置/维护时才用）
tmux kill-server
```

---

## 五、Window 管理（tmux 窗口）

### 5.1 创建

> 日常推荐用 `entry <项目名>` 一键建四窗口工作区（见第七章），不用手动一个个建。下面手动方式用于理解原理。

创建 Session 时，**Window 0 自动存在**，无需手动创建。之后每次 `Ctrl+b c` 新增一个。

完整步骤（以四 Window 工作区为例）：

**第一步：创建 Session**（自动有 Window 0，默认名 `bash`）

```bash
cd ~/workspace/llm-broker
tmux new -s llm-broker
```

**第二步：把 Window 0 改名为 Shell**（快捷键，不是命令）

按 `Ctrl+b` 松开，再按 `,` → 弹出输入框 → 输入 `Shell` → 回车。

**第三步：新建 Window 1 并启动 OpenCode**

1. 按 `Ctrl+b c` 新建 Window
2. 按 `Ctrl+b ,`，输入 `OpenCode` 改名
3. 运行命令：

```bash
opencode
```

**第四步：新建 Window 2 并启动 Codex**

1. 按 `Ctrl+b c` 新建
2. 按 `Ctrl+b ,`，输入 `Codex` 改名
3. 运行：

```bash
codex
```

**第五步：新建 Window 3 并启动 Claude**

1. 按 `Ctrl+b c` 新建
2. 按 `Ctrl+b ,`，输入 `Claude` 改名
3. 运行：

```bash
claude
```

完成后底部状态栏：

```
[llm-broker]  0:Shell  1:OpenCode  2:Codex  3:Claude*
```

命令方式创建指定名称 Window（适合脚本）：

```bash
tmux new-window -n OpenCode
tmux new-window -n Codex
tmux new-window -n Claude
```

### 5.2 切换 Window

```bash
Ctrl+b 0    # 切到 Shell
Ctrl+b 1    # 切到 OpenCode
Ctrl+b 2    # 切到 Codex
Ctrl+b 3    # 切到 Claude
Ctrl+b w    # 交互式列表，可上下选择
Ctrl+b n    # 下一个 Window
Ctrl+b p    # 上一个 Window
```

每个 Window 里的程序**独立运行，互不影响**，切换不会打断其他 Window 里正在运行的 Agent。

### 5.3 重命名 / 关闭

```
Ctrl+b ,        # 重命名当前 Window
exit             # 关闭当前 Window（其他 Window 不受影响）
```

### 5.4 查看所有 Window

```bash
Ctrl+b w          # 交互式
tmux list-windows  # 命令式，例如：0: Shell (1 panes)
```

### 5.5 推荐 Window 布局

每个项目保持统一结构，形成肌肉记忆：

```
0: Shell       ← Git、Docker、日常命令
1: OpenCode    ← 主要 AI 编码工具
2: Codex       ← 批量修改 / 重构
3: Claude      ← 架构分析 / 复杂推理
```

---

## 六、Pane 管理（tmux 分屏）

Pane 是 Window 内的分屏，适合临时使用，不适合长期运行 AI Agent。

```bash
Ctrl+b %        # 左右分屏
Ctrl+b "        # 上下分屏
Ctrl+b 方向键   # 在 Pane 间切换
exit            # 关闭当前 Pane
```

> **建议**：AI Agent 放 Window，临时查看日志 / 辅助命令才用 Pane。日常开发以 Window 为主，Pane 为辅。

---

## 七、AI Coding 工作流

### 整体架构

```
Windows Terminal
        │
        ▼
      WSL2
        │
        ▼
      tmux
        │
        ▼
  Session（项目）→ Window（AI Agent）
```

VS Code 与 tmux 职责分工：

| 工具                  | 职责                               |
| --------------------- | ---------------------------------- |
| VS Code（Remote-WSL） | 编辑代码、Git、调试、浏览项目      |
| tmux                  | 长期运行 AI Agent、Shell、后台任务 |

> **VS Code 负责编辑，tmux 负责运行。** VS Code Terminal 属于普通终端，关闭 VS Code 或断开 Remote-WSL 后进程通常结束；tmux 是独立 Server，不依赖任何前端。

### 命名规范

**Session 名**：直接使用项目目录名（`llm-broker`、`router-api`、`poetry-video`），保持项目目录与 Session 名一致。

**Window 名**：固定编号角色，跨项目统一：

```
0: Shell
1: OpenCode
2: Codex
3: Claude
4: Docker（按需）
5: Logs（按需）
```

### 一键创建工作区（脚本）

熟悉手动创建后，推荐用脚本一键完成。脚本会**自动判断**：Session 已存在就 attach，不存在就创建标准四窗口工作区。

**第一步：创建脚本**

```bash
mkdir -p ~/scripts ~/workspace
nano ~/scripts/new-project.sh
```

粘贴：

```bash
#!/bin/bash
# 一键创建/进入 tmux 工作区
# 用法：entry <项目名>   （或 bash ~/scripts/new-project.sh <项目名>）
# - Session 不存在：创建标准四窗口工作区（Shell/OpenCode/Codex/Claude）
# - Session 已存在：直接 attach 进去（不报错）

PROJECT=$1
WORKSPACE=~/workspace

# 1. 参数校验
if [ -z "$PROJECT" ]; then
  echo "用法：bash ~/scripts/new-project.sh <项目名>"
  exit 1
fi

# 2. Session 已存在 → 直接 attach，不重复创建
if tmux has-session -t "$PROJECT" 2>/dev/null; then
  echo "Session '$PROJECT' 已存在，attach 进去..."
  exec tmux attach -t "$PROJECT"
fi

# 3. Session 不存在 → 检查项目目录
if [ ! -d "$WORKSPACE/$PROJECT" ]; then
  echo "目录不存在：$WORKSPACE/$PROJECT"
  echo "先创建：mkdir -p $WORKSPACE/$PROJECT"
  exit 1
fi

cd "$WORKSPACE/$PROJECT" || { echo "无法进入：$WORKSPACE/$PROJECT"; exit 1; }

# 4. 创建 Session，Window 0 命名为 Shell
tmux new-session -d -s "$PROJECT" -n Shell

# 5. 创建其余三个 Window
tmux new-window -t "$PROJECT" -n OpenCode
tmux new-window -t "$PROJECT" -n Codex
tmux new-window -t "$PROJECT" -n Claude

# 6. 切到 Window 0（Shell）后进入
tmux select-window -t "$PROJECT:0"
tmux attach -t "$PROJECT"
```

保存：`Ctrl+O` → 回车 → `Ctrl+X`。

**第二步：赋权**

```bash
chmod +x ~/scripts/new-project.sh
```

**第三步：配别名**

在 `~/.bashrc` 末尾添加：

```bash
alias entry="bash ~/scripts/new-project.sh"
```

生效：

```bash
source ~/.bashrc
```

**第四步：使用**

```bash
entry llm-broker       # 第一次：创建工作区
# ... 在各 Window 启动 opencode/codex/claude ...
# Ctrl+b d 退出

entry llm-broker       # 第二次：Session 已存在，自动 attach（不报错）
entry router-api       # 另一个新项目，创建它的工作区
```

### 脚本逐段解释

| 段落                                                                                             | 作用                                                                         |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `PROJECT=$1` | 接收命令行第一个参数（项目名），`entry llm-broker` 里 `$1` = `llm-broker` |                                                                              |
| 参数校验`[ -z "$PROJECT" ]`                                                                    | 没传项目名就提示用法退出，防止空跑                                           |
| `tmux has-session -t "$PROJECT"`                                                               | **关键判断**：Session 已存在就 attach，避免 `duplicate session` 报错 |
| 目录检查`[ ! -d ... ]`                                                                         | 项目目录不存在就提示先建目录，防止 tmux 建在错地方                           |
| `tmux new-session -d -s ... -n Shell`                                                          | 后台创建 Session，Window 0 命名为 Shell（`-d` 不自动进入）                 |
| `tmux new-window -t ... -n OpenCode`                                                           | 在该 Session 里新建并直接命名 Window（省去`Ctrl+b ,` 改名）                |
| `tmux select-window -t "$PROJECT:0"`                                                           | 选中 Window 0（`Session名:Window编号` 语法）                               |
| `tmux attach -t "$PROJECT"`                                                                    | 最后才 attach 进去，看到 Shell 窗口                                          |

### 使用前提

脚本要求 `~/workspace/<项目名>` 目录已存在。第一次用某个项目先建目录：

```bash
mkdir -p ~/workspace/llm-broker
cd ~/workspace/llm-broker
git init          # 新项目
# 或 git clone <repo> .   # 已有仓库
```

### 日常只需记一个命令

```bash
entry <项目名>
```

- Session 不存在 → 创建工作区
- Session 已存在 → attach 进去

不用再区分「新建」和「attach」两个命令。

### 脚本只建空窗口，不自动启动 AI Agent

进 tmux 后手动切窗口启动工具：

```
Ctrl+b 1  → OpenCode 窗口 → 输 opencode
Ctrl+b 2  → Codex 窗口    → 输 codex
Ctrl+b 3  → Claude 窗口   → 输 claude
Ctrl+b 0  → Shell 窗口    → git/docker 等
```

每个项目 cd 目录、启动参数可能不同，自动化启动反而僵化，所以留给手动。

### 多项目并行

```bash
entry llm-broker       # 建第一个
# Ctrl+b d 退出
entry router-api       # 建第二个
# Ctrl+b d 退出
tmux ls               # 看所有 Session
tmux a -t llm-broker  # 切回第一个
```

切换项目 = 切换 Session，互不影响。

---

## 八、命名规范

> **Session 表示项目，Window 表示角色（AI Agent 或终端）。**

### Session 命名

推荐直接用项目名：

```
llm-broker
poetry-video
router-api
website
```

不推荐：`opencode`、`codex`、`project1`、`test`、`new`——无法体现属于哪个项目，项目多了会混乱。

### Window 命名

固定编号角色，所有项目保持一致：

```
0: Shell
1: OpenCode
2: Codex
3: Claude
```

统一命名的好处：肌肉记忆（`0=Shell, 1=OpenCode...`）、切换项目无学习成本、方便脚本自动化。

### 目录结构

```
~/workspace
├── llm-broker      → Session: llm-broker
├── poetry-video    → Session: poetry-video
├── router-api      → Session: router-api
└── website         → Session: website
```

项目目录与 Session 名一致，最易维护。

---

## 九、滚动与复制（电脑端 + 手机端）

> 本章解决两个场景的需求：**滚动看历史** 和 **复制文本**。
>
> - **电脑端**（Windows Terminal）：鼠标拖选直接复制到 Windows 剪贴板
> - **手机端**（Termux SSH）：长按选文字复制到手机剪贴板

### 9.0 电脑端复制（Windows Terminal）

电脑端 tmux 里复制文本，**不要用 Copy Mode**，直接鼠标拖选：

1. 滚轮上翻到目标位置（mouse on 状态下翻 tmux 历史）
2. **直接鼠标左键拖选**（不需要按 Shift）
3. 松开鼠标 → 自动复制到 Windows 剪贴板
4. 到任意 Windows 程序粘贴（`Ctrl+V`）

**注意事项**：
- 滚轮下滚到**接近底部**时会自动退出 copy-mode（tmux 3.4 默认行为，无法关闭）
- 要复制最后几行：滚到能看到目标就停止滚动，然后用鼠标拖选
- 或者按 `q` 退出 copy-mode 回到底部，再直接拖选

**配置**（`~/.tmux.conf`）：

```tmux
# 鼠标拖选松手：写 Windows 剪贴板，留在 copy-mode（不自动退出，可继续滚）
bind-key -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe "clip.exe"
```

**为什么不用 Shift+拖拽**：Windows Terminal 的 Shift+拖拽走原生选择，不能滚动选跨屏内容。tmux 的鼠标拖选可以滚屏选大范围内容，且通过 `clip.exe` 直接写 Windows 剪贴板，体验和原生一致。

### 9.1 为什么手机端要特殊处理

tmux 接管终端进入「alternate screen」模式后，**Termux 原生滚动条/滚动手势对 tmux 历史无效**——手指滑只能滚 Termux 自己的缓冲，滚不到 tmux 里的长历史。

复制也有障碍：tmux 鼠标模式开着时，会拦截触屏事件，Termux 原生长按选文字被 tmux 抢走。

### 9.2 方案：开鼠标 + 一键切换

`~/.tmux.conf` 配置（已在第十章）：

```tmux
# 默认开鼠标：手指滑动 = 翻 tmux 历史
set -g mouse on

# Ctrl+b m 切换鼠标开关
bind m set -g mouse \; display-message "mouse: #{?mouse,ON,OFF}"
```

**两个需求都满足**：

| 需求       | 操作                                                             | 鼠标状态   |
| ---------- | ---------------------------------------------------------------- | ---------- |
| 滚动看历史 | 手指上下滑                                                       | 开（默认） |
| 复制文本   | `Ctrl+b m` 关鼠标 → 长按选文字 → 复制 → `Ctrl+b m` 开回来 | 关         |

### 9.3 滚动看历史（鼠标开）

手指在 Termux 里上下滑 = 翻 tmux scrollback。和电脑端鼠标滚轮等效。

### 9.4 复制文本（关鼠标后长按）

1. 按 `Ctrl+b m`，底部显示 `mouse: OFF`
2. 长按终端某处 → 出现选择锚点
3. 拖动锚点选范围（真文字选择，精准）
4. 复制 → 进**手机自己的剪贴板**
5. 到任意 app（微信/备忘录）粘贴
6. 按 `Ctrl+b m` 开回鼠标，恢复滚动

### 9.5 关键事实：电脑端 vs 手机端复制目标不同

| 端     | 复制方式           | 复制到哪个剪贴板       | 说明                               |
| ------ | ------------------ | ---------------------- | ---------------------------------- |
| 电脑端 | 鼠标拖选           | Windows 系统剪贴板     | 通过 `clip.exe` 写入               |
| 手机端 | `Ctrl+b m` + 长按 | **手机自己的剪贴板** | 通过 Termux 原生选择写入           |

和向日葵方案的根本差异（向日葵已弃用）：向日葵复制进 Windows 剪贴板，SSH 方案下手机端复制进手机剪贴板。

### 9.6 Copy Mode 什么时候还用得到

**电脑端**：偶尔用 `Ctrl+b [` 进 Copy Mode，键盘翻历史 + 搜索（`/`、`n`）。日常复制用鼠标拖选（见 9.0）。

**手机端**：基本不用（手指滑动 + 长按更方便）。

Copy Mode 键位表见开头 Cheat Sheet。

---

## 十、配置文件 ~/.tmux.conf

针对 AI Coding 场景（WSL + Windows Terminal + 手机 SSH）优化。当前实际配置：

```tmux
# ─── 按键响应 ──────────────────────────────────────
# 提升 Esc 响应速度（OpenCode / Codex / Claude Code 用 Esc 中断时需要）
set -sg escape-time 10

# xterm-keys 保留（保证功能键正常）
set -g xterm-keys on

# 终端类型（保证 TUI 应用收到正确的 key sequence）
set -g default-terminal "xterm-256color"

# ─── 状态栏（显示完整 Session 名，不截断）──────────
# 左侧：完整 Session 名 + 当前 Window 信息
set -g status-left-length 50
set -g status-left "[#S] "

# 右侧：时间
set -g status-right-length 50
set -g status-right "%H:%M "

# Window 列表样式：名字完整显示
set -g window-status-format         " #I:#W "
set -g window-status-current-format " #I:#W*"

# ─── 鼠标模式 ─────────────────────────────────────────────
# 默认开鼠标：滚轮/手指滑动 = 翻 tmux 历史
# 电脑端复制：直接鼠标拖选（写 Windows 剪贴板）
# 手机端复制：prefix+m 关鼠标 → 长按选文字 → 复制 → prefix+m 开回来
set -g mouse on

# prefix + m 切换鼠标开关
bind m set -g mouse \; display-message "mouse: #{?mouse,ON,OFF}"

# ─── 复制优化 ─────────────────────────────────────────────
# 鼠标拖选松手：写 Windows 剪贴板，留在 copy-mode（不自动退出，可继续滚）
bind-key -T copy-mode MouseDragEnd1Pane send-keys -X copy-pipe "clip.exe"
```

修改后生效：

```bash
tmux source-file ~/.tmux.conf
```

或重启 tmux 自动加载。

**验证 Esc 传递**：

```bash
# 在 tmux 中运行 cat，按 Esc，若输出 ^[ 则说明 Esc 已正常传递
cat
```

> **关于已删除的配置**：早期向日葵方案用过的 `mode-keys vi` + `v`/`y` + `F8` 复合绑定已删除。`clip.exe` 在电脑端复制场景下重新引入（鼠标拖选写 Windows 剪贴板），但不再是向日葵方案的遗留。备份在 `~/.tmux.conf.bak.20260806`。

---

## 十一、常见问题（FAQ）

### Q1：`Esc` 按下去没有反应，无法停止 Agent（OpenCode / Codex / Claude Code）

**原因**：tmux 默认 `escape-time` 较高，会延迟或吞掉 Esc 信号。

**解决**：`~/.tmux.conf` 添加 `set -sg escape-time 10`，然后 `tmux source-file ~/.tmux.conf`。验证：tmux 中运行 `cat`，按 `Esc`，输出 `^[` 即正常。

### Q2：`Alt+Enter` 无法换行

**原因**：Windows Terminal 不生成独立的 `Alt+Enter` 键事件，tmux 无法识别——终端层限制，非 OpenCode / tmux 问题。

**替代**：用 `Ctrl+Enter` 代替换行 / 发送。

### Q3：`tmux new -s xxx` 报 `duplicate session`

Session 已存在，不要重复创建：

```bash
tmux ls                    # 查看已有 Session
tmux attach -t <name>      # 直接进入
```

### Q4：`tmux attach` 报 `can't find session`

Session 不存在（可能 WSL 重启过），重新创建：

```bash
cd ~/workspace/llm-broker
tmux new -s llm-broker
```

### Q5：关闭 Windows Terminal 后，tmux 还在运行吗？

| 操作                  | tmux 是否继续 |
| --------------------- | ------------- |
| 关闭 Windows Terminal | ✅ 继续运行   |
| 关闭 VS Code Remote   | ✅ 继续运行   |
| SSH 断线              | ✅ 继续运行   |
| `wsl --shutdown`    | ❌ tmux 结束  |
| 重启 Windows          | ❌ tmux 结束  |

### Q6：AI 工具支持 Resume，还需要 tmux 吗？

两者解决不同问题，建议同时用：

| 功能                   | tmux | Resume |
| ---------------------- | ---- | ------ |
| 终端关闭后程序继续运行 | ✅   | ❌     |
| 程序崩溃后恢复上下文   | ❌   | ✅     |

### Q7：VS Code 的终端可以代替 tmux 吗？

不能。VS Code Terminal 属于普通终端，关闭 VS Code 或断开 Remote-WSL 后进程通常结束。tmux 是独立 Server，不依赖任何前端终端。

### Q8：什么时候用 Pane，什么时候用 Window？

- **Window**：长期运行的 AI Agent、Shell 环境。
- **Pane**：临时查看日志、快速对比输出，任务完成后关闭。

### Q9：为什么建议先 `cd` 再 `tmux new`？

tmux 会继承创建 Session 时所在的目录，新建的 Window 也会继承，省去每次手动 `cd`。

### Q10：`rename-session` 需要先进入 Session 吗？

不需要，可从任意目录执行，操作的是 tmux Server 内部状态，与当前目录无关。

### Q11：手机端复制选不中文字？

手机 SSH（Termux）方案下，tmux 鼠标开着会拦截触屏，导致长按选不中文字。

**解决**：复制前先按 `Ctrl+b m` 关鼠标（底部显示 `mouse: OFF`），再长按选文字。复制完按 `Ctrl+b m` 开回来恢复滚动。

### Q12：电脑端 tmux 右侧有大片空白（被截断成 80 列）？

多个客户端同时 attach 同一个 Window 时，tmux 按最小宽度客户端渲染。手机 Termux 宽 80 列，会把电脑端也压缩成 80 列。

**解决**：错峰使用（不同时双端看同一窗口），或两端看不同 Window。彻底根治需 `aggressive-resize on`，但同一 Window 多客户端取最小宽度是 tmux 固有行为，无法完全解决。

### Q13：电脑端复制时滚轮下滚到底部附近会自动退出 copy-mode？

**原因**：tmux 3.4 默认行为，滚到历史缓冲底部时自动退出 copy-mode（无法通过配置关闭）。

**解决**：
- 滚到能看到目标就**停止滚动**，然后用鼠标拖选
- 或按 `q` 退出 copy-mode 回到底部，再直接拖选
- tmux 3.7+ 有 `scroll-exit-off` 命令可关闭此行为，但 Ubuntu 24.04 官方源只有 3.4

---

## 附录：进阶学习方向

本手册覆盖日常 95% 以上场景。进阶内容：

- 状态栏美化（powerline / tpm 插件）
- Session 自动恢复（`tmux-resurrect` / `tmux-continuum`）
- Window / Pane 布局保存与恢复
- 与 SSH、Docker 结合使用

建议先熟练本手册后再逐步扩展。

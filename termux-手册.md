# 手机 Termux SSH 连 WSL 部署手册

> **目标**：手机通过 Termux（SSH）连 WSL 里的 tmux，原生选中/复制终端长输出，粘贴到任意位置。
>
> **替代方案**：取代向日葵远程桌面（拖图像选文字极难用）。
>
> **环境**：Windows 10/11 · WSL2（Ubuntu 24.04）· Android 手机
>
> **两种网络场景**：
>
> - **在家（同一 WiFi）**：直接用局域网 IP，零额外配置
> - **外出（4G/5G/其他网络）**：用蒲公英异地组网，见「外网扩展方案：蒲公英」章节
>
> **架构**：
>
> ```
> 手机 Termux ──ssh -p 2222──> Windows:2222 ──portproxy──> WSL:22 ──> tmux
> （在家：直连 Windows 局域网 IP；外出：经蒲公英虚拟网连 Windows）
> ```
>
> **配套文档**：tmux 操作见 [tmux-手册.md](tmux-手册.md)。

---

## 角色分工说明

| 角色                             | 谁做                                   | 标记         |
| -------------------------------- | -------------------------------------- | ------------ |
| Windows 管理员操作（PowerShell） | **你**                           | 🔧 [你操作]  |
| WSL 内操作（装包、改配置）       | **Claude/Codex 等 AI 工具** 或你 | 🤖 [AI 操作] |
| 手机操作（装 Termux、连接）      | **你**                           | 📱 [你操作]  |

> AI 能直接跑 WSL 命令（装包、查状态、改文件），但 **Windows 管理员权限操作和手机操作 AI 无法代劳**，必须你做。

---

## 第一步：WSL 装 SSH 服务端 🤖 [AI 操作]

**交付给 AI 的指令**：

> 帮我装 openssh-server 并确认 22 端口在监听

AI 执行（参考步骤）：

```bash
# 检查是否已装
dpkg -l openssh-server | grep -E "^ii" && echo "已装" || echo "未装"

# 装包（需 sudo 密码，AI 跑不了就交给用户）
sudo apt-get install -y openssh-server

# 验证
which sshd                          # /usr/sbin/sshd
sudo service ssh status             # Ubuntu 24 可能显示 inactive，但 socket 激活
sudo ss -tlnp | grep ":22 "         # 22 端口监听即可
```

### 关键事实（Ubuntu 24.04）

- Ubuntu 24 用 **socket 激活**：`ssh.service` 可能显示 `inactive (dead)`，但 `ssh.socket` 在跑，22 端口在监听——**这是正常的，不用手动 start**。
- 验证标准：`ss -tlnp | grep ":22 "` 有 LISTENING 输出即可。

---

## 第二步：WSL 安装与启动验证 🤖 [AI 操作]

**交付给 AI 的指令**：

> 确认 sshd 22 端口从 WSL 本机能连

AI 执行：

```bash
# 端口连通性（不要密码的测法）
timeout 3 bash -c 'echo > /dev/tcp/localhost/22' && echo "端口通" || echo "端口不通"
timeout 3 bash -c 'echo > /dev/tcp/172.20.196.127/22' && echo "WSL IP 通" || echo "不通"
```

---

## 第三步：拿 WSL 的 IP 🤖 [AI 操作]

```bash
hostname -I
# 输出类似：172.20.196.127 172.18.0.1 172.17.0.1
# 第一个 172.x.x.x 是 WSL2 的 IP，记下来，第五步要用
```

> ⚠️ **WSL2 的 IP 每次重启会变**。本文档末尾有自动更新方案。

---

## 第四步：手机装 Termux 📱 [你操作]

### 下载渠道（唯一推荐）

**F-Droid 版**（官方推荐，唯一保持更新）：

```
https://f-droid.org/packages/com.termux
```

点 **Download APK** → 安装。

### ⚠️ 不要用 Google Play 版

Google Play 上的 Termux **已停更**，过时有 bug。**只用 F-Droid 版**。

### 备选渠道

GitHub Releases：`https://github.com/termux/termux-app/releases`

下 `termux-app_v0.118.x+github-debug_arm64-v8a.apk`（绝大多数现代 Android）。

---

## 第五步：Windows 配端口转发 🔧 [你操作]

### 为什么需要这步

WSL2 是虚拟机，sshd 的 22 端口被 `wslrelay.exe` 转发到 Windows，但**只绑 `127.0.0.1`（本机回环）**，手机从外部连不到。要用 `netsh portproxy` 把 Windows 的 2222 端口转发到 WSL 的 22。

### 为什么用 2222 不用 22

22 端口被 `wslrelay.exe` 占了（绑在 127.0.0.1:22），netsh portproxy 抢不到，所以换空闲端口 2222。

### 操作（管理员 PowerShell）

**1. 以管理员身份打开 PowerShell**：开始菜单搜 PowerShell → 右键「以管理员身份运行」

**2. 配端口转发**（把 `172.20.196.127` 换成第三步拿到的 WSL IP）：

```powershell
netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress=172.20.196.127
```

**3. 防火墙放行 2222**：

```powershell
New-NetFirewallRule -DisplayName "WSL SSH 2222" -Direction Inbound -LocalPort 2222 -Protocol TCP -Action Allow
```

**4. 验证配置**：

```powershell
netsh interface portproxy show v4tov4
# 应显示：0.0.0.0  2222  →  172.20.196.127  22
```

**5. 验证端口监听**：

```powershell
netstat -ano | findstr ":2222"
# 应显示：TCP  0.0.0.0:2222  LISTENING  xxxx
```

### ⚠️ 大坑：端口没监听怎么办

如果第 5 步**没有 LISTENING 输出**（端口没起来），是 `netsh portproxy` 依赖的 **IP Helper 服务（iphlpsvc）** 没跑或卡死。**这是最常见的坑，配置对了但端口不监听就是这个原因。**

管理员 PowerShell 重启该服务：

```powershell
Restart-Service iphlpsvc -Force
```

等 3 秒再查：

```powershell
netstat -ano | findstr ":2222"
```

应该就有 LISTENING 了。

> **经验**：我们这次部署就卡在这。配了 portproxy 2222 没监听，重启 iphlpsvc 后立刻就有了。

---

## 第六步：手机 Termux 基础配置 📱 [你操作]

### 1. 装 openssh 客户端

Termux 打开，跑：

```bash
pkg update -y && pkg install openssh -y
```

> Termux 可能自带 openssh，提示 `already the newest version` 即可，正常。

### 2. 拿 Windows 局域网 IP

Windows PowerShell（普通即可）跑：

```powershell
ipconfig | findstr IPv4
```

取 `192.168.x.x` 那个（局域网 IP，不是 `172.x.x.x` 的 WSL 虚拟网卡地址）。

### 3. 首次 SSH 连接测试

Termux 跑（IP 换成上一步拿到的）：

```bash
ssh -p 2222 你的WSL用户名@192.168.0.100
```

- 第一次问 `Are you sure...?` → 输 `yes`
- 输 WSL 密码（不显示字符，正常）

连上看到 WSL 提示符（如 `mleon@hostname:~$`）就是成功。

---

## 第七步：配置自动连接（核心优化）📱 [你操作]

> **目标**：打开 Termux 自动探测网络、自动选 IP、免密连接、**自动进默认项目的 tmux**。

### 7.1 创建智能连接脚本

在 Termux 里执行（逐行粘贴）：

```bash
mkdir -p ~/bin
echo '#!/bin/bash' > ~/bin/connect.sh
echo 'HOME_IP="192.168.0.100"' >> ~/bin/connect.sh
echo 'PGY_IP="172.16.2.86"' >> ~/bin/connect.sh
echo 'PORT="2222"' >> ~/bin/connect.sh
echo 'USER="mleon"' >> ~/bin/connect.sh
echo 'DEFAULT_PROJECT="openspec-dual-runtime-bridge"' >> ~/bin/connect.sh
echo '' >> ~/bin/connect.sh
echo 'can_reach() { ping -c 1 -W 2 "$1" &>/dev/null; }' >> ~/bin/connect.sh
echo '' >> ~/bin/connect.sh
echo 'if can_reach "$HOME_IP"; then' >> ~/bin/connect.sh
echo '  TARGET="$HOME_IP"; echo "[家中WiFi] 连接 $TARGET ..."' >> ~/bin/connect.sh
echo '  ssh -tt -p "$PORT" -o ConnectTimeout=5 "$USER@$TARGET" \' >> ~/bin/connect.sh
echo '    "bash ~/scripts/new-project.sh $DEFAULT_PROJECT"' >> ~/bin/connect.sh
echo 'else' >> ~/bin/connect.sh
echo '  echo "[外网模式] 尝试蒲公英..."' >> ~/bin/connect.sh
echo '  if can_reach "$PGY_IP"; then' >> ~/bin/connect.sh
echo '    TARGET="$PGY_IP"; echo "[蒲公英已连接] 连接 $TARGET ..."' >> ~/bin/connect.sh
echo '    ssh -tt -p "$PORT" -o ConnectTimeout=5 "$USER@$TARGET" \' >> ~/bin/connect.sh
echo '      "bash ~/scripts/new-project.sh $DEFAULT_PROJECT"' >> ~/bin/connect.sh
echo '  else' >> ~/bin/connect.sh
echo '    echo "请手动打开蒲公英 App（60秒内）..."' >> ~/bin/connect.sh
echo '    count=0' >> ~/bin/connect.sh
echo '    while [ $count -lt 30 ]; do' >> ~/bin/connect.sh
echo '      if can_reach "$PGY_IP"; then break; fi' >> ~/bin/connect.sh
echo '      sleep 2; count=$((count + 1)); echo "等待... ($((count * 2))s)"' >> ~/bin/connect.sh
echo '    done' >> ~/bin/connect.sh
echo '    if can_reach "$PGY_IP"; then' >> ~/bin/connect.sh
echo '      TARGET="$PGY_IP"; echo "[蒲公英已连接] 连接 $TARGET ..."' >> ~/bin/connect.sh
echo '      ssh -tt -p "$PORT" -o ConnectTimeout=5 "$USER@$TARGET" \' >> ~/bin/connect.sh
echo '        "bash ~/scripts/new-project.sh $DEFAULT_PROJECT"' >> ~/bin/connect.sh
echo '    else' >> ~/bin/connect.sh
echo '      echo "❌ 蒲公英连接超时（60秒）"' >> ~/bin/connect.sh
echo '    fi' >> ~/bin/connect.sh
echo '  fi' >> ~/bin/connect.sh
echo 'fi' >> ~/bin/connect.sh
chmod +x ~/bin/connect.sh
```

> **参数说明**：
>
> - `HOME_IP` 和 `PGY_IP` 换成你的实际 IP（见「关键参数模板」章节）
> - `DEFAULT_PROJECT` 是打开 Termux 自动进入的默认项目名（session 存在则 attach，不存在则建四窗口）。换默认项目改这一行即可

> **⚠️ 关键经验：长行必须用 `\` 续行拆短**
>
> Termux 粘贴**长命令行会自动折行**，导致 echo 字符串被断成两段、重定向 `>>` 漏到下一行，脚本结构损坏（症状：`source` 后只 echo 不连接、或 `syntax error: unexpected end of file`）。
>
> 上面的三处 ssh 行较长，已用 bash 行尾 `\` 续行拆成两短行（每段 < 70 字符）。**重建脚本时务必保留 `\`**，不要合并成单行。其他行都很短，不受影响。

### 7.2 配置 SSH 免密

```bash
# 生成密钥（一路回车，不设密码）
ssh-keygen -t ed25519 -N ""

# 传公钥到 WSL（要输一次 WSL 密码）
ssh-copy-id -p 2222 mleon@192.168.0.100
```

> 如果当前在外网（用蒲公英），把 IP 换成 `172.16.2.86`。

### 7.3 打开 Termux 自动触发

```bash
echo 'source ~/bin/connect.sh' >> ~/.bashrc
```

### 7.4 验证

```bash
# 手动跑一次测试
source ~/bin/connect.sh
```

看到 `[家中WiFi] 连接 ...` 或 `[外网模式] 尝试蒲公英...` 然后**直接进入默认项目的 tmux**（`openspec-dual-runtime-bridge`）即成功。

> 连上后直接 attach 在 tmux 里，键盘输入发给当前 window 的前台进程，不在 WSL shell。要敲 WSL 命令切到 Window 0（Shell）：`Ctrl+b 0`。`Ctrl+b d` detach 后会退回 Termux 本地（ssh 远程命令结束，连接关闭），不是 WSL shell——日常无需 detach，多项目切换走 `Ctrl+b s`（见第八步）。

### 7.5 自动连接逻辑说明

```
打开 Termux
  → 检测 192.168.0.100（家里 Windows IP）
    → 通 → SSH 直连
    → 不通 → 检测 172.16.2.86（蒲公英虚拟 IP）
      → 通 → SSH 直连
      → 不通 → 提示"请手动打开蒲公英 App（60秒内）"
        → 等待 60 秒（每 2 秒检测一次）
        → 期间手动打开蒲公英 App
        → 通了 → 自动 SSH 连接
        → 超时 → 提示失败，留在 Termux 本地

连上后（三种分支都一样）：
  → ssh -tt 执行 bash ~/scripts/new-project.sh $DEFAULT_PROJECT
    → 默认项目 session 存在 → attach 进去
    → 默认项目 session 不存在（WSL 重启过）→ 自动建四窗口工作区并 attach
```

> **设计说明**：蒲公英 App 无法被脚本自动拉起（Android 系统限制），所以采用"提示 + 等待"策略，用户在 60 秒内手动打开即可。

---

## 第八步：进 tmux 工作区 📱 [你操作]

配置好第七步后，**打开 Termux 即自动进入默认项目**（`openspec-dual-runtime-bridge`），无需手动敲命令。

只有以下情况需要手动操作：

```bash
# 改默认项目：编辑 ~/bin/connect.sh 顶部的 DEFAULT_PROJECT 变量
# 手动连（不用自动脚本）：第七步速查里的手动模式
```

### 切换到其他项目（tmux 内）

连上后已经在 tmux 里，**切换已有项目用 `Ctrl+b s`**：

1. 按 `Ctrl+b` 松开，再按 `s`
2. 弹出所有 Session（项目）列表，方向键上下选
3. 选中目标项目按回车 → 切过去

> `Ctrl+b s` 是 tmux 原生功能，在 tmux 内部切换 Session，不退出、不重连。新项目需先在**电脑端** `entry <项目名>` 建好（手机端只切不建），建好后手机 `Ctrl+b s` 即可看到并切换。

### 手动创建/进入工作区（不用自动脚本时）

```bash
# 推荐：装了 entry 脚本的话（见 tmux 手册「一键创建工作区」），一条命令通吃
entry llm-broker          # 存在则 attach，不存在则建四窗口工作区

# 或通用方式（不依赖脚本）：
tmux a -t llm-broker      # Session 已存在 → attach
tmux new -s llm-broker    # Session 不存在 → 新建（单窗口，需手动加 Window）
```

> 建议按项目名命名 Session（如 `llm-broker`、`router-api`），一个项目一个 Session，切换项目 = 切换 Session。

---

## 第九步：复制文本 📱 [你操作]

手机端复制分两种场景：

**A. 短内容（当前屏）**：`Ctrl+b m` 关鼠标 → 长按选文字 → 复制 → `Ctrl+b m` 开回来

1. 按 `Ctrl+b m` 关鼠标（底部显示 `mouse: OFF`）
2. **长按**终端 → 出现选择锚点
3. **拖动锚点**选范围
4. **复制** → 进手机剪贴板
5. 到任意 app 粘贴
6. 按 `Ctrl+b m` 开回鼠标，恢复滑动翻历史

**B. 长内容（跨屏）⭐**：滑动 → 方向键微调 → `Space` → 滚动 → `Enter`

1. **手指滑动**屏幕 → 自动进入 Copy Mode（右上角出现 `[x/总行]` 行号）
2. 滑动到起始位置附近（目标行出现在屏幕上即可，不用精确）
3. **用方向键微调** → 把光标精确移到起始行
4. **按 `Space`** 锁定起点（光标处，精准）
5. **手指上下滑动**翻页 → 选择延伸（被选文字变黄色），可跨屏
6. 滑到终点附近，**再用方向键微调**到结束行
7. **按 `Enter`** → 复制并退出 Copy Mode
8. 到任意 app 粘贴

> 关键：tmux 滚动时光标钉在屏幕固定位置不动（内容在光标下流动），所以滑动后必须用**方向键**把光标移到目标行，起点才准。方向键 Termux 自带，比 `j`/`k` 顺手。

> 详细说明与原理见 [tmux-手册.md 第九章](tmux-手册.md)。

---

## 验证网络层（排查时用）📱 [你操作]

如果连不上，先确认手机和电脑网络层通不通。

Termux 跑：

```bash
ping -c 4 192.168.0.100
```

- **能 ping 通**（0% 丢包）→ 网络层 OK，问题在端口转发
- **ping 不通** → 手机和电脑不在同一网段 / 路由器隔离了客户端

---

## 排查决策树

| 现象                                       | 原因                           | 处理                                                                                                   |
| ------------------------------------------ | ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 家里 WiFi 连不上（ssh 超时）               | portproxy 没监听 / IP 变了     | 看`netstat :2222` 有没 LISTENING；没有就重启 iphlpsvc                                                |
| portproxy 配了但端口不监听                 | iphlpsvc 服务卡死              | `Restart-Service iphlpsvc -Force`                                                                    |
| 之前能连，重启 WSL 后连不上                | WSL IP 变了                    | 重新拿`hostname -I`，更新 portproxy 的 `connectaddress`                                            |
| Termux ping 不通 Windows                   | 网络隔离                       | 检查手机和电脑是否同一 WiFi；路由器是否开了「客户端隔离」                                              |
| `Connection refused`                     | 端口没转发 / sshd 没跑         | 从第一步重新查 sshd 22 监听                                                                            |
| `ssh localhost` 报 Host key verification | 首次连接 host key 没加         | `ssh-keyscan -H localhost >> ~/.ssh/known_hosts` 或用 `StrictHostKeyChecking=accept-new`           |
| 外网（4G）连不上                           | 蒲公英客户端没在线 / 没组网    | 打开蒲公英 App 确认两端在线、同一组网网络                                                              |
| 蒲公英 IP ping 不通                        | 客户端掉线                     | 重开手机蒲公英 App，确认在线                                                                           |
| 切 WiFi/4G 后 ssh 断开                     | 网络切换断连                   | 重新打开 Termux（自动连接脚本会处理）                                                                  |
| 手机长按选不中文字                         | tmux 鼠标开着拦截触屏          | 先按`Ctrl+b m` 关鼠标再选                                                                            |
| 电脑端 tmux 右侧大片空白                   | 手机同时连同一 Window 拖累宽度 | 错峰使用，或两端看不同 Window                                                                          |
| 手机端 TUI 状态行显示不全（Codex 的 `Ready`/`Context` 等被截断，末尾出现 `…`） | Termux 字体过大 → 列数太窄（如 96 列） | 双指捏合缩小字体，列数变宽（120+），状态行完整显示；零配置，Termux 原生手势 |
| 自动连接脚本没触发                         | `.bashrc` 没配置或脚本路径错   | 检查 `grep connect ~/.bashrc` 是否有输出；确认 `~/bin/connect.sh` 存在且可执行                          |
| `source` 后只 echo 不进 tmux，或 `syntax error: unexpected end of file` | Termux 粘贴长行折行，ssh 行被断开、重定向 `>>` 漏到下一行 | `grep -c "ssh -tt" ~/bin/connect.sh` 应为 3；不是就按 7.1 重建（保留 `\` 续行，勿合并单行） |
| 连上后停在 WSL shell，没自动进项目         | 脚本是旧版（ssh 行无 `-tt` 和远程命令） | 按 7.1 重建脚本，确认三处 ssh 都带 `-tt ... "bash ~/scripts/new-project.sh $DEFAULT_PROJECT"` |

---

## 外网扩展方案：蒲公英异地组网

> **场景**：不在家时（4G/5G、咖啡店 WiFi、公司网络）也要连 WSL。
>
> **原理**：蒲公英（贝锐/Oray 出品，和向日葵同一家）把手机和电脑拉进一个虚拟局域网，两端分到固定的虚拟 IP，**任何网络下都能互通**。国内服务，不和 GFW 冲突，不和梯子打架。

### 为什么不用 Tailscale

Tailscale 在国内验证为**数据面不通**——控制面能登录，但设备间 P2P 打洞失败 + 境外 DERP 中继被阻断。要让它工作得自建国内 DERP 中继服务器（买 VPS + 域名 + 部署 derper），成本约 ¥100/年 + 几小时运维。对个人太重，已放弃。如果你装过 Tailscale，可以卸载（手机 + 电脑都卸）。

### 蒲公英免费版限制（官网查证）

| 项目       | 免费体验版         | 对你的影响                                     |
| ---------- | ------------------ | ---------------------------------------------- |
| 组网设备数 | 3 个               | ✅ 够（手机 + Windows = 2 台）                 |
| P2P 直连   | 不限流量、不限速   | ✅ 直连时 SSH 飞快                             |
| 转发流量   | 不限流量，共享带宽 | ⚠️ 走中转时速度无保障                        |
| 服务器线路 | 仅电信             | ⚠️ 移动宽带中转可能慢（但 SSH 流量小，够用） |

**关键**：P2P 直连成功时不限速，SSH 终端流量极小（几 KB/s），即使走中转也完全够用。

### 落地步骤

#### 第 1 步：注册 Oray 账号 🔧 [你操作]

浏览器打开 `https://console.oray.com`，注册 Oray 账号（手机号或邮箱）。

> 如果你用过向日葵，**直接用原账号登录**，不用重新注册——向日葵和蒲公英共用 Oray 账号体系。

#### 第 2 步：Windows 装蒲公英客户端 🔧 [你操作]

1. 下载：`https://pgy.oray.com/download`（选 Windows 版）
2. 安装，用 Oray 账号登录
3. 客户端会给 Windows 分一个虚拟 IP（如 `172.16.2.86`），记下来——这是手机要连的目标 IP

#### 第 3 步：手机装蒲公英 App 📱 [你操作]

1. 应用商店搜「蒲公英异地组网」（贝锐/Oray 出品）
2. 装好，**用同一个 Oray 账号登录**（必须同账号，否则不在一个网络）

#### 第 4 步：组网（把两台设备拉进一个虚拟网络）🔧 [你操作]

浏览器打开 `https://console.oray.com` → 进「异地组网」→「网络成员」：

1. 创建一个网络（免费版只能建 1 个对等网络）
2. 把 Windows 客户端和手机客户端都加进这个网络
3. 两台设备各分到一个虚拟 IP

#### 第 5 步：验证组网 📱 [你操作]

手机连蒲公英后，Termux 跑（IP 换成 Windows 的蒲公英虚拟 IP）：

```bash
ping -c 4 172.16.2.86
```

- **能 ping 通** → 组网成功
- **ping 不通** → 检查两设备是否在同一组网网络、客户端是否都在线

#### 第 6 步：SSH 连接 📱 [你操作]

```bash
ssh -p 2222 mleon@172.16.2.86
```

> 端口还是 2222——Windows 的 portproxy 监听 `0.0.0.0:2222`，蒲公英虚拟网卡也能收到。如果连不上但 ping 通，可能防火墙要放行蒲公英网段（`172.16.0.0/12`，看实际分到的网段）。

连上 → `entry <项目名>`（或 `tmux a -t <项目名>`）进工作区 → 复制文本。

### 蒲公英虚拟 IP 的稳定性

蒲公英虚拟 IP **绑账号，不绑物理网络**——不管电脑连家里 WiFi、换公司 WiFi、还是插网线，虚拟 IP 都不变（不像 WSL IP 每次重启变）。

但底层 portproxy 的 `connectaddress`（指向 WSL IP）还是会随 WSL 重启变。即：

- **手机到 Windows 这段**：蒲公英虚拟 IP 稳定 ✅
- **Windows 到 WSL 这段**：portproxy 目标 WSL IP 会变 ⚠️，WSL 重启后要更新

### 蒲公英和梯子冲突吗

基本不冲突——蒲公英走自己的 SD-WAN 通道，不像 Tailscale 那样和 VPN 抢路由。但梯子开全局模式可能干扰，测的时候先关梯子，确认能连再试共存。

---

## 网络切换断线重连

手机切 WiFi/4G、退后台、网络波动会导致 SSH 断开。**但 tmux 里的程序不会丢**——这是蒲公英 + SSH + tmux 组合的核心价值。

### 重连步骤

```bash
# 1. 手机 Termux 重新打开（自动连接脚本会处理）
# 或手动：
ssh -p 2222 mleon@172.16.2.86        # 外网
# 或
ssh -p 2222 mleon@192.168.0.100       # 家里 WiFi

# 2. 进工作区（按项目名）
entry llm-broker          # 推荐：自动 attach（脚本判断存在与否）
# 或
tmux a -t llm-broker      # 通用：直接 attach 已有 Session
```

看到断线前的界面 = 程序没丢。

### 为什么不用重启 tmux

```
网络切换 → SSH 断 → Termux 退出
              │
              ▼
      tmux Server 独立运行（不受 SSH 断开影响）
              │
              ▼
      OpenCode 在 tmux 里继续跑 ✅
```

tmux 是独立 Server，SSH 断了它不死。重连后 `tmux a` 接上。**重启 tmux 反而会杀掉里面的 OpenCode，千万别重启**。

### 唯一要重启 tmux 的情况

WSL 重启（`wsl --shutdown` 或重启 Windows）→ tmux Server 死了 → `tmux a` 报 `can't find session` → 这时才需要重建（`entry <项目名>` 或 `tmux new -s <项目名>`）。网络切换不会到这步。

---

## tmux 鼠标模式配置

手机 SSH 进 tmux 后，要滑动翻历史 + 复制文本，靠 tmux 鼠标模式。配置在 WSL 的 `~/.tmux.conf`（详见 [tmux-手册.md 第十章](tmux-手册.md)）：

```tmux
# 默认开鼠标：手指滑动 = 翻 tmux 历史
set -g mouse on

# Ctrl+b m 切换鼠标开关
bind m set -g mouse \; display-message "mouse: #{?mouse,ON,OFF}"

# vi Copy Mode：手机端跨屏复制用（Space 开始选择 / Enter 复制）
setw -g mode-keys vi
```

**日常用法**：

- 滚动看历史：手指上下滑（鼠标开，自动进 Copy Mode）
- 复制短内容（当前屏）：`Ctrl+b m` 关鼠标 → 长按选文字 → 复制 → `Ctrl+b m` 开回来
- 复制长内容（跨屏）：滑动 → `Space` → 滚动 → `Enter`（详见第五章「复制文本」）

> 向日葵方案遗留的 `F8`/`v`/`y` 复合绑定已删除。`mode-keys vi` 保留（手机端跨屏复制需要 Space/Enter 默认绑定）。

---

## 遗留优化（可选）

### 1. WSL 重启后 IP 自动更新 🤖 [AI 操作]

WSL2 重启后 IP 会变，portproxy 的 `connectaddress` 失效。让 AI 写个自动更新脚本：

**交付给 AI 的指令**：

> 写个脚本：拿到 WSL 当前 IP，更新 netsh portproxy 的 connectaddress，并在 Windows 开机时自动跑

参考实现（PowerShell 脚本 + 任务计划程序）：

```powershell
# update-wsl-ssh.ps1
$wslIp = (wsl hostname -I).Split(" ")[0]
netsh interface portproxy delete v4tov4 listenport=2222 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress=$wslIp
```

注册为开机任务（管理员 PowerShell）：

```powershell
# 用 schtasks 或 Task Scheduler GUI 注册
```

> 让 AI 帮你生成完整脚本和注册命令。

### 2. SSH 免密登录 ✅ 已完成

见「第七步：配置自动连接」的 7.2 节。配好后打开 Termux 自动连接，无需输密码。

### 3. Termux 连接别名（可选）

如果不用自动连接脚本，也可以配别名手动连：

Termux 里 `~/.ssh/config` 加：

```
host wsl
   HostName 192.168.0.100
	Port 2222
	User mleon

host wsl-out
   HostName 172.16.2.86
	Port 2222
	User mleon
```

之后 `ssh wsl`（家里）或 `ssh wsl-out`（外网）即可。

### 4. 向日葵方案的 tmux 配置清理 ✅ 已完成

向日葵方案用过的 `~/.tmux.conf` 配置（vi 模式、`v`/`y`/`clip.exe`、`F8` 复合绑定）在 SSH 方案下不需要，已全部删除。当前配置见 [tmux-手册.md 第十章](tmux-手册.md)。备份在 `~/.tmux.conf.bak.20260806`。

### 5. Tailscale 卸载 ✅ 可选

如果装过 Tailscale 验证外网方案，验证为国内数据面不通后可卸载（手机 + 电脑都卸）。外网改用蒲公英。

---

## 完整连接速查（配好后日常用）

### 自动模式（推荐）

**打开 Termux 即可**，脚本自动处理：

- 在家 → 自动连 `192.168.0.100`
- 外出 → 自动检测蒲公英，通了就连，不通提示你打开 App
- 连上后 → **自动进入默认项目 `openspec-dual-runtime-bridge` 的 tmux**（session 存在则 attach，不存在则建四窗口）

### 手动模式（调试用）

```bash
# 在家
ssh -p 2222 mleon@192.168.0.100

# 外出（蒲公英已开）
ssh -p 2222 mleon@172.16.2.86
```

> 手动模式连上停在 WSL shell，需自己敲 `entry <项目名>` 进工作区（和自动模式不同）。

### 进工作区 / 切换项目

```bash
# 自动模式：打开 Termux 直接进默认项目，无需手动命令
# 切换到其他已有项目（tmux 内）：Ctrl+b s → 方向键选 → 回车
# 手动进工作区（手动模式连上后）：
entry llm-broker          # 推荐（装了脚本）：自动创建/attach
# 或
tmux a -t llm-broker      # 通用：attach 已有 Session
```

### 复制

- 短内容：`Ctrl+b m` 关鼠标 → 长按选文字 → 复制 → `Ctrl+b m` 开回来
- 长内容（跨屏）：滑动 → 方向键微调 → `Space` → 滚动 → `Enter`

---

## 关键参数模板（换电脑时填）

部署到新电脑时，把这些值查出来填进去：

| 参数                            | 怎么查                                | 示例值             |
| ------------------------------- | ------------------------------------- | ------------------ |
| WSL 用户名                      | `whoami`                            | `mleon`          |
| WSL IP                          | `hostname -I` 第一个                | `172.20.196.127` |
| Windows 局域网 IP（家用）       | PowerShell`ipconfig \| findstr IPv4` | `192.168.0.100`  |
| Windows 蒲公英虚拟 IP（外网用） | 蒲公英客户端「本机虚拟 IP」           | `172.16.2.86`    |
| 对外端口                        | 固定                                  | `2222`           |
| WSL sshd 端口                   | 固定                                  | `22`             |
| 默认项目名                      | `~/workspace` 下的目录名              | `openspec-dual-runtime-bridge` |

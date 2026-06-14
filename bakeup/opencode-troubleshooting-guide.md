# OpenCode 报错排查指南

> 本文档提供 opencode 报错后的通用排查方案，帮助快速定位和解决问题。

## 目录

- [排查流程](#排查流程)
- [第一步：获取完整错误信息](#第一步获取完整错误信息)
- [第二步：定位日志文件](#第二步定位日志文件)
- [第三步：分析错误类型](#第三步分析错误类型)
- [第四步：针对性解决](#第四步针对性解决)
- [常见错误速查表](#常见错误速查表)
- [日志分析技巧](#日志分析技巧)
- [配置文件速查](#配置文件速查)

---

## 排查流程

```
报错发生
    ↓
获取完整错误信息（错误消息 + 上下文）
    ↓
定位日志文件
    ↓
搜索关键错误信息
    ↓
分析错误类型（见速查表）
    ↓
针对性解决
    ↓
验证修复
```

---

## 第一步：获取完整错误信息

### 1.1 控制台输出

注意记录：
- 错误消息全文
- 发生时间
- 当时使用的模型/Provider
- 当时执行的操作（edit/bash/query 等）

### 1.2 常见错误消息格式

```
# opencode 客户端错误
Error: xxx

# Provider/API 错误
AI_APICallError: xxx

# 流式响应错误
stream error: xxx

# 超时错误
Timeout on reading data from socket
```

---

## 第二步：定位日志文件

### 2.1 日志文件位置

| 位置 | 路径 | 说明 |
|------|------|------|
| **主日志** | `~/.local/share/opencode/log/opencode.log` | 当前会话日志 |
| **历史日志** | `~/.local/share/opencode/log/*.log` | 按时间戳命名的历史日志 |
| **数据库** | `~/.local/share/opencode/opencode.db` | 会话和消息存储 |

### 2.2 查看日志命令

```bash
# 查看最近的错误
tail -100 ~/.local/share/opencode/log/opencode.log | grep -i "error\|ERROR"

# 搜索特定错误
grep -i "timeout" ~/.local/share/opencode/log/opencode.log
grep -i "socket" ~/.local/share/opencode/log/opencode.log
grep -i "stream error" ~/.local/share/opencode/log/opencode.log

# 搜索特定 Provider
grep "providerID=litellm" ~/.local/share/opencode/log/opencode.log

# 搜索特定模型
grep "modelID=claude-opus-4-8" ~/.local/share/opencode/log/opencode.log

# 搜索特定会话
grep "session.id=ses_xxx" ~/.local/share/opencode/log/opencode.log
```

### 2.3 日志文件格式

```json
{
  "timestamp": "2026-06-14T17:34:29.102Z",
  "level": "ERROR",
  "message": "stream error",
  "providerID": "litellm",
  "modelID": "claude-opus-4-8",
  "session.id": "ses_xxx",
  "agent": "Prometheus - Plan Builder",
  "error.error": "Timeout on reading data from socket"
}
```

---

## 第三步：分析错误类型

### 3.1 按错误消息分类

| 错误消息 | 类型 | 常见原因 |
|----------|------|----------|
| `Timeout on reading data from socket` | 超时 | LiteLLM/Provider 响应慢 |
| `The socket connection was closed unexpectedly` | 连接断开 | 上游提供商断开连接 |
| `ECONNREFUSED` | 连接被拒 | 服务未启动或端口错误 |
| `429 Too Many Requests` | 限流 | API 调用频率超限 |
| `401 Unauthorized` | 认证失败 | API Key 错误或过期 |
| `500 Internal Server Error` | 服务器错误 | 上游提供商内部错误 |
| `fetch failed` | 网络错误 | 网络连接问题 |
| `Headers Timeout Error` | 头部超时 | Node.js Undici 默认超时 |

### 3.2 按发生位置分类

| 位置 | 表现 | 排查方向 |
|------|------|----------|
| **opencode 客户端** | 工具执行失败 | 检查 opencode 配置 |
| **LiteLLM 代理** | stream error | 检查 litellm-config.yaml |
| **上游提供商** | API 错误 | 检查 API Key 和网络 |
| **本地文件系统** | 读写失败 | 检查权限和磁盘空间 |

---

## 第四步：针对性解决

### 4.1 超时类错误

#### 问题：`Timeout on reading data from socket`

**原因**：LiteLLM streaming 响应超时

**解决方案**：

编辑 `~/.claude/litellm-config.yaml`：

```yaml
litellm_settings:
  request_timeout: 300      # 总请求超时（秒）
  stream_timeout: 300       # streaming chunk 间超时（秒）
  num_retries: 2            # 重试次数

router_settings:
  timeout: 300              # 路由器超时（秒）
```

#### 问题：`Headers Timeout Error`

**原因**：Node.js Undici 默认 5 分钟 headersTimeout

**解决方案**：

```bash
# 环境变量
export NODE_OPTIONS="--max-http-header-size=16384"
```

---

### 4.2 连接类错误

#### 问题：`The socket connection was closed unexpectedly`

**原因**：上游提供商主动断开连接

**排查步骤**：

```bash
# 1. 检查网络连通性
ping api.openai.com
curl -I https://api.openai.com

# 2. 检查 API 状态
curl https://status.openai.com

# 3. 检查 LiteLLM 日志
tail -f ~/.local/share/opencode/log/opencode.log | grep "socket"
```

**解决方案**：
- 增加重试次数
- 使用其他 Provider
- 检查网络代理配置

#### 问题：`ECONNREFUSED`

**原因**：服务未启动或端口错误

**排查步骤**：

```bash
# 检查 LiteLLM 是否运行
curl http://localhost:4000/health

# 检查端口占用
lsof -i :4000
netstat -tlnp | grep 4000
```

---

### 4.3 认证类错误

#### 问题：`401 Unauthorized`

**排查步骤**：

```bash
# 1. 检查 API Key 环境变量
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# 2. 测试 API Key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 3. 检查 LiteLLM 配置
cat ~/.claude/litellm-config.yaml | grep api_key
```

---

### 4.4 限流类错误

#### 问题：`429 Too Many Requests`

**解决方案**：

```yaml
# litellm-config.yaml
litellm_settings:
  num_retries: 3
  cooldown_time: 60          # 冷却时间（秒）

router_settings:
  routing_strategy: least-busy  # 使用负载均衡
  cooldown_time: 120

model_list:
  - model_name: gpt-5.5
    litellm_params:
      max_parallel_requests: 2   # 限制并发
      rpm: 10                    # 限制每分钟请求数
```

---

### 4.5 文件操作类错误

#### 问题：edit/patch 超时

**排查步骤**：

```bash
# 检查磁盘空间
df -h

# 检查文件权限
ls -la <目标文件>

# 检查文件大小
du -sh <目标文件>
```

**解决方案**：
- 拆分大文件操作
- 使用 write 替代 edit
- 检查磁盘空间

---

## 常见错误速查表

| 错误消息 | 快速定位 | 解决方案 |
|----------|----------|----------|
| `Timeout on reading data from socket` | LiteLLM streaming 超时 | 增加 `stream_timeout` |
| `socket connection closed unexpectedly` | 上游提供商断开 | 增加重试，检查网络 |
| `ECONNREFUSED` | 服务未启动 | 启动 LiteLLM 服务 |
| `429 Too Many Requests` | API 限流 | 增加冷却时间，负载均衡 |
| `401 Unauthorized` | 认证失败 | 检查 API Key |
| `500 Internal Server Error` | 上游服务器错误 | 等待恢复或切换 Provider |
| `fetch failed` | 网络连接失败 | 检查网络和代理 |
| `Headers Timeout Error` | Node.js 超时 | 设置环境变量 |

---

## 日志分析技巧

### 1. 快速定位最近错误

```bash
# 最近 50 条错误
grep "level=ERROR" ~/.local/share/opencode/log/opencode.log | tail -50
```

### 2. 按时间范围筛选

```bash
# 查找特定时间的错误
grep "2026-06-14T17:34" ~/.local/share/opencode/log/opencode.log
```

### 3. 按 Provider 筛选

```bash
# LiteLLM 相关错误
grep "providerID=litellm.*ERROR" ~/.local/share/opencode/log/opencode.log
```

### 4. 按模型筛选

```bash
# 特定模型的错误
grep "modelID=claude-opus-4-8.*ERROR" ~/.local/share/opencode/log/opencode.log
```

### 5. 统计错误频率

```bash
# 统计各类错误数量
grep "level=ERROR" ~/.local/share/opencode/log/opencode.log | \
  grep -oP 'error.error="[^"]*"' | sort | uniq -c | sort -rn
```

### 6. 实时监控

```bash
# 实时查看错误
tail -f ~/.local/share/opencode/log/opencode.log | grep --line-buffered "ERROR"
```

---

## 配置文件速查

### opencode 配置

| 文件 | 路径 | 用途 |
|------|------|------|
| 全局配置 | `~/.config/opencode/opencode.json` | Provider、模型配置 |
| 插件配置 | `~/.config/opencode/oh-my-openagent.json` | Agent 配置 |
| 本地配置 | `./opencode/opencode.json` | 项目级配置 |

### LiteLLM 配置

| 文件 | 路径 | 用途 |
|------|------|------|
| 主配置 | `~/.claude/litellm-config.yaml` | 模型列表、超时、重试 |

### 关键配置项

```yaml
# ~/.claude/litellm-config.yaml
litellm_settings:
  request_timeout: 300      # 总请求超时
  stream_timeout: 300       # 流式响应超时
  num_retries: 2            # 重试次数
  cooldown_time: 60         # 冷却时间

router_settings:
  timeout: 300              # 路由器超时
  routing_strategy: least-busy  # 负载均衡
```

```json
// ~/.config/opencode/opencode.json
{
  "provider": {
    "your-provider": {
      "options": {
        "timeout": 600000,
        "chunkTimeout": 600000
      }
    }
  }
}
```

---

## 排查检查清单

当遇到错误时，按顺序检查：

- [ ] 1. 记录完整错误消息
- [ ] 2. 记录发生时间和上下文
- [ ] 3. 查看日志文件
- [ ] 4. 确定错误类型（超时/连接/认证/限流）
- [ ] 5. 确定错误位置（客户端/LiteLLM/上游）
- [ ] 6. 根据错误类型采取对应措施
- [ ] 7. 验证修复

---

## 快速命令参考

```bash
# 查看日志
tail -f ~/.local/share/opencode/log/opencode.log

# 搜索错误
grep "ERROR" ~/.local/share/opencode/log/opencode.log | tail -20

# 检查 LiteLLM 状态
curl http://localhost:4000/health

# 检查环境变量
env | grep -i "api_key\|base_url"

# 检查配置
cat ~/.claude/litellm-config.yaml
cat ~/.config/opencode/opencode.json
```

---

*文档创建时间：2026-06-15*
*基于 opencode v1.17.7*

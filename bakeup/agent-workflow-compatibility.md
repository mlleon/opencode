# Claude Code / OpenCode / OpenSpec / Superpowers 兼容性方案

> 目的：记录当前项目在 Claude Code、OpenCode、OpenSpec、Superpowers、Oh-My-OpenAgent 之间的推荐组合、兼容性风险和隔离策略，避免后续 agent 会话把不同 harness 的命令、skills、plugins 混用。

---

## 1. 当前推荐结论

### 1.1 主推荐

如果目标是稳定推进当前 `llm-broker` 的架构蓝图到正式规格，优先使用：

```text
Claude Code + OpenSpec + Superpowers
```

原因：当前仓库仍是架构/产品蓝图仓库，主要任务是把需求、约束、未决问题和验收门禁固化为 OpenSpec 规格；这个阶段更需要稳定的规格治理和执行纪律，而不是复杂的多模型编排。

### 1.2 辅助推荐

如果需要多模型、并行分析、低成本探索和更强的 OpenCode agent orchestration，则使用：

```text
OpenCode + Oh-My-OpenAgent
```

但 OpenCode 侧应默认只作为执行器/研究器，不应读取 Claude Code 侧安装的 Superpowers、OpenSpec 命令或 Claude-specific runtime 配置。

### 1.3 最稳分工

```text
Claude Code + OpenSpec + Superpowers
  负责：规格治理、proposal/design/tasks、评审、验证、归档。

OpenCode + Oh-My-OpenAgent
  负责：多代理分析、文档/源码查证、架构咨询、后续代码实现执行。

共享事实源
  AGENTS.md
  openspec/
```

---

## 2. 各工具职责边界

| 工具 | 角色 | 应负责 | 不应负责 |
|---|---|---|---|
| OpenSpec | 规格生命周期 | proposal、design、tasks、spec delta、sync、archive | 替代 agent runtime |
| Superpowers | 工程方法论 skills | brainstorming、writing-plans、TDD、review、verification | 覆盖 OpenSpec 事实源 |
| Claude Code | 稳定主 harness | 执行 OpenSpec + Superpowers 主流程 | 读取 OpenCode 专用配置 |
| OpenCode | 可选执行 harness | 运行 Oh-My-OpenAgent、多模型、多代理 | 自动继承 Claude Code runtime 状态 |
| Oh-My-OpenAgent | OpenCode 增强运行时 | Sisyphus/Hephaestus/Oracle/Librarian/Explore、skills、MCP、commands | 替代 OpenSpec 或 Superpowers |

---

## 3. 兼容性判断

| 组合 | 兼容性 | 风险 | 判断 |
|---|---:|---:|---|
| Claude Code + OpenSpec | 高 | 低 | 推荐作为规格治理基础 |
| Claude Code + OpenSpec + Superpowers | 高 | 低 | 当前阶段主推荐 |
| OpenCode + OpenSpec | 高 | 低 | OpenSpec 有 OpenCode command adapter |
| OpenCode + Oh-My-OpenAgent + OpenSpec | 中高 | 中 | 可用，但需约束命令/skills 来源 |
| OpenCode + Oh-My-OpenAgent + Superpowers | 中 | 中高 | 两个插件都可能注入 prompt/skills |
| Claude Code + OpenCode 共用同一项目 | 可行 | 中 | 必须隔离 `.claude/` 与 `.opencode/` |

---

## 4. 核心风险：跨 harness 污染

### 4.1 风险描述

如果在 Claude Code 安装了 Superpowers 和 OpenSpec，再用 OpenCode + Oh-My-OpenAgent 打开同一个项目，可能发生：

```text
OpenCode / Oh-My-OpenAgent 兼容层读取 .claude/commands、.claude/skills、Claude Code plugins
```

这会导致：

- OpenCode 侧看到 Claude Code 的 OpenSpec 命令。
- OpenCode 侧看到 Claude Code 的 Superpowers skills。
- Superpowers 方法论在 OpenCode 里被重复触发。
- Oh-My-OpenAgent 自己的 category/skill 流程与 Superpowers 流程叠加。
- agent 收到过多流程指令，简单任务也可能被强制走 planning/TDD/review。

### 4.2 关键事实

Oh-My-OpenAgent 的 Claude Code 兼容配置包含：

```ts
claude_code: {
  mcp?: boolean
  commands?: boolean
  skills?: boolean
  agents?: boolean
  hooks?: boolean
  plugins?: boolean
}
```

并且其技能加载默认逻辑等价于：

```ts
includeClaudeSkills = pluginConfig.claude_code?.skills !== false
```

因此，默认情况下它可能读取 Claude Code skills；要隔离必须显式关闭。

### 4.3 源码依据

下面只列和本兼容性判断直接相关的源码片段。路径和 URL 均来自对应公开仓库，后续若上游变更，应以最新源码为准。

#### 4.3.1 Oh-My-OpenAgent 有 Claude Code 兼容开关

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/config/schema/claude-code.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/config/schema/claude-code.ts`

```ts
import { z } from "zod"

export const ClaudeCodeConfigSchema = z.object({
  mcp: z.boolean().optional(),
  commands: z.boolean().optional(),
  skills: z.boolean().optional(),
  agents: z.boolean().optional(),
  hooks: z.boolean().optional(),
  plugins: z.boolean().optional(),
  plugins_override: z.record(z.string(), z.boolean()).optional(),
})
```

结论：Oh-My-OpenAgent 不是只能“全量兼容 Claude Code”，而是可以按来源关闭 `skills`、`commands`、`plugins`、`agents`、`hooks`、`mcp`。

#### 4.3.2 Oh-My-OpenAgent 默认会包含 Claude Code skills

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/plugin/skill-context.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/plugin/skill-context.ts`

```ts
const includeClaudeSkills = pluginConfig.claude_code?.skills !== false
const [configSourceSkills, userSkills, globalSkills, projectSkills, opencodeProjectSkills, agentsProjectSkills, agentsGlobalSkills] =
  await Promise.all([
    discoverConfigSourceSkills({
      config: pluginConfig.skills,
      configDir: directory,
    }),
    includeClaudeSkills ? discoverUserClaudeSkills() : Promise.resolve([]),
    discoverOpencodeGlobalSkills(),
    includeClaudeSkills ? discoverProjectClaudeSkills(directory) : Promise.resolve([]),
    discoverOpencodeProjectSkills(directory),
    discoverProjectAgentsSkills(directory),
    discoverGlobalAgentsSkills(),
  ])
```

结论：只要没有显式设置 `claude_code.skills = false`，Oh-My-OpenAgent 就可能读取用户级或项目级 Claude Code skills。这正是 Claude Code 安装 Superpowers 后可能影响 OpenCode 会话的原因。

#### 4.3.3 `disabled_skills` 绑定的是内置技能枚举

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/config/schema/oh-my-opencode-config.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/config/schema/oh-my-opencode-config.ts`

```ts
disabled_mcps: z.array(AnyMcpNameSchema).optional(),
disabled_agents: z.array(z.string()).optional(),
disabled_skills: z.array(BuiltinSkillNameSchema).optional(),
disabled_hooks: z.array(z.string()).optional(),
disabled_commands: z.array(BuiltinCommandNameSchema).optional(),
```

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/config/schema/agent-names.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/config/schema/agent-names.ts`

```ts
export const BuiltinSkillNameSchema = z.enum([
  "playwright",
  "agent-browser",
  "dev-browser",
  "frontend-ui-ux",
  "git-master",
  // ...review-work / security-research / team-mode 等内置技能
])
```

结论：`disabled_skills` 的语义是禁 Oh-My-OpenAgent 内置技能，不适合作为“禁用外部 Superpowers skill”的首选方式。

#### 4.3.4 外部 skill 应用 `skills.disable` 删除

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/features/opencode-skill-loader/merger/skills-config-normalizer.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/features/opencode-skill-loader/merger/skills-config-normalizer.ts`

```ts
const { sources = [], enable = [], disable = [], ...entries } = config
return { sources, enable, disable, entries }
```

来源：`code-yeongyu/oh-my-openagent`  
文件：`src/features/opencode-skill-loader/merger.ts`  
URL：`https://github.com/code-yeongyu/oh-my-openagent/blob/dev/src/features/opencode-skill-loader/merger.ts`

```ts
for (const name of normalizedConfig.disable) {
  skillMap.delete(name)
}
```

结论：如果确实只想在 Oh-My-OpenAgent 的 skill 合并结果中删掉某些外部技能，应使用：

```jsonc
{
  "skills": {
    "disable": ["skill-name"]
  }
}
```

但这仍不等同于禁用另一个独立 OpenCode plugin 的 prompt 注入。

#### 4.3.5 Superpowers 的 OpenCode plugin 会注册 skills 路径并注入 bootstrap

来源：`obra/superpowers`  
文件：`.opencode/INSTALL.md`  
URL：`https://github.com/obra/superpowers/blob/main/.opencode/INSTALL.md`

```json
{
  "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"]
}
```

来源：`obra/superpowers`  
文件：`.opencode/plugins/superpowers.js`  
URL：`https://github.com/obra/superpowers/blob/main/.opencode/plugins/superpowers.js`

```js
config: async (config) => {
  config.skills = config.skills || {};
  config.skills.paths = config.skills.paths || [];
  if (!config.skills.paths.includes(superpowersSkillsDir)) {
    config.skills.paths.push(superpowersSkillsDir);
  }
},
```

同一文件还通过 OpenCode message transform 注入 bootstrap：

```js
'experimental.chat.messages.transform': async (_input, output) => {
  const bootstrap = getBootstrapContent();
  if (!bootstrap || !output.messages.length) return;
  const firstUser = output.messages.find(m => m.info.role === 'user');
  if (!firstUser || !firstUser.parts.length) return;
  // ...注入 Superpowers bootstrap 内容
}
```

结论：如果 OpenCode 自己安装了 Superpowers plugin，仅在 Oh-My-OpenAgent 的 `skills.disable` 删除 skill 名称并不能完全阻止 Superpowers 影响会话，因为 Superpowers plugin 仍可能通过自己的 hook 注入 bootstrap prompt。

#### 4.3.6 OpenSpec 对 Claude Code 与 OpenCode 生成不同命令路径

来源：`Fission-AI/OpenSpec`  
文件：`src/core/command-generation/adapters/claude.ts`  
URL：`https://github.com/Fission-AI/OpenSpec/blob/main/src/core/command-generation/adapters/claude.ts`

```ts
/**
 * Claude Code adapter for command generation.
 * File path: .claude/commands/opsx/<id>.md
 * Frontmatter: name, description, category, tags
 */
export const claudeAdapter: ToolCommandAdapter = {
  toolId: 'claude',

  getFilePath(commandId: string): string {
    return path.join('.claude', 'commands', 'opsx', `${commandId}.md`);
  },
}
```

来源：`Fission-AI/OpenSpec`  
文件：`src/core/command-generation/adapters/opencode.ts`  
URL：`https://github.com/Fission-AI/OpenSpec/blob/main/src/core/command-generation/adapters/opencode.ts`

```ts
/**
 * OpenCode adapter for command generation.
 * File path: .opencode/commands/opsx-<id>.md
 * Frontmatter: description
 */
export const opencodeAdapter: ToolCommandAdapter = {
  toolId: 'opencode',

  getFilePath(commandId: string): string {
    return path.join('.opencode', 'commands', `opsx-${commandId}.md`);
  },
}
```

结论：OpenSpec 本身已经把 Claude Code 与 OpenCode 的命令入口分开；因此推荐让两个 harness 各自使用自己的命令目录，而不是让 OpenCode 读取 `.claude/commands`。

---

## 5. 推荐隔离策略

### 5.1 最稳策略

在 OpenCode / Oh-My-OpenAgent 项目配置里关闭 Claude Code 兼容来源。

建议创建或更新：

```text
.opencode/oh-my-openagent.jsonc
```

推荐内容：

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/dev/assets/oh-my-openagent.schema.json",

  "claude_code": {
    "skills": false,
    "commands": false,
    "plugins": false,
    "agents": false,
    "hooks": false,
    "mcp": false
  }
}
```

效果：OpenCode 使用 Oh-My-OpenAgent 时，不主动读取 Claude Code 的 skills、commands、plugins、agents、hooks、MCP。

### 5.2 如果仍想复用 Claude Code MCP

可以只保留 MCP：

```jsonc
{
  "claude_code": {
    "skills": false,
    "commands": false,
    "plugins": false,
    "agents": false,
    "hooks": false,
    "mcp": true
  }
}
```

但当前项目为降低变量，建议先全部关闭。

---

## 6. 不推荐只用 `disabled_skills` 禁 Superpowers

### 6.1 原因

在 Oh-My-OpenAgent 中：

```jsonc
{
  "disabled_skills": ["..."]
}
```

主要用于禁用 Oh-My-OpenAgent 内置技能，例如：

```text
playwright
git-master
review-work
security-research
security-review
team-mode
```

Superpowers 是外部 plugin / skills 来源，不应优先用 `disabled_skills` 处理。

### 6.2 如果只想禁个别外部 Superpowers skill

Oh-My-OpenAgent 的 `skills.disable` 可以在技能合并后按名称删除技能。示例：

```jsonc
{
  "skills": {
    "disable": [
      "using-superpowers",
      "brainstorming",
      "writing-plans",
      "executing-plans",
      "dispatching-parallel-agents",
      "requesting-code-review",
      "receiving-code-review",
      "systematic-debugging",
      "verification-before-completion",
      "using-git-worktrees",
      "subagent-driven-development",
      "test-driven-development",
      "finishing-a-development-branch"
    ]
  }
}
```

但这不是首选，因为：

1. Superpowers 将来可能新增 skill。
2. 需要长期维护一串 skill 名称。
3. 如果 OpenCode 自己安装了 Superpowers 插件，该插件仍可能通过自己的 hook 注入 bootstrap prompt。

### 6.3 如果 OpenCode 自己安装了 Superpowers plugin

如果 `opencode.json` 里存在：

```json
{
  "plugin": [
    "oh-my-openagent",
    "superpowers@git+https://github.com/obra/superpowers.git"
  ]
}
```

那么 Superpowers 是 OpenCode 的独立插件，不是 Claude Code 污染。若希望 OpenCode 完全不受 Superpowers 影响，应从 `plugin` 数组移除它：

```json
{
  "plugin": [
    "oh-my-openagent"
  ]
}
```

---

## 7. OpenSpec 双 harness 使用方式

### 7.1 Claude Code 侧

OpenSpec 为 Claude Code 生成命令路径：

```text
.claude/commands/opsx/<id>.md
```

典型命令：

```text
/opsx:propose
/opsx:explore
/opsx:apply
/opsx:sync
/opsx:archive
```

### 7.2 OpenCode 侧

OpenSpec 为 OpenCode 生成命令路径：

```text
.opencode/commands/opsx-<id>.md
```

典型命令：

```text
/opsx-propose
/opsx-explore
/opsx-apply
/opsx-sync
/opsx-archive
```

### 7.3 共享事实源

无论使用 Claude Code 还是 OpenCode，唯一共享事实源是：

```text
AGENTS.md
openspec/
```

不是：

```text
.claude/commands/*
.opencode/commands/*
```

命令文件只是不同 harness 的入口适配层。

---

## 8. 推荐目录结构

```text
llm-broker/
├── AGENTS.md                         # 所有 harness 共享红线
├── LLM_Broker_Architecture_v13.md
├── agent-workflow-compatibility.md   # 本文档
├── openspec/                         # 共享规格事实源
│   ├── project.md
│   ├── specs/
│   └── changes/
├── .claude/                          # Claude Code 专用
│   └── commands/
│       └── opsx/
├── .opencode/                        # OpenCode / Oh-My-OpenAgent 专用
│   ├── commands/
│   │   └── opsx-*.md
│   └── oh-my-openagent.jsonc
└── .omo/
    └── drafts/
```

规则：

```text
.claude/ 只给 Claude Code 用。
.opencode/ 只给 OpenCode / Oh-My-OpenAgent 用。
openspec/ 和 AGENTS.md 两边共享。
```

---

## 9. 建议写入 AGENTS.md 的规则

后续可把以下内容加入 `AGENTS.md`：

```markdown
## Harness isolation

- `openspec/` and `AGENTS.md` are shared truth across Claude Code and OpenCode.
- `.claude/` is Claude Code-only runtime configuration.
- `.opencode/` is OpenCode/Oh-My-OpenAgent-only runtime configuration.
- OpenCode agents must not load or rely on `.claude/commands`, `.claude/skills`, or Claude Code plugins.
- Claude Code agents must not rely on `.opencode/commands` or Oh-My-OpenAgent-specific behavior.
- If a workflow exists in both harnesses, files under `openspec/` are authoritative, not either harness command file.
```

---

## 10. 实际使用流程

### 10.1 当前阶段：蓝图转规格

推荐主链路：

```text
Claude Code + OpenSpec + Superpowers
```

目标：

```text
把 .omo/drafts/llm-broker-complete-blueprint.md
和 .omo/drafts/llm-broker-v13-communication.md
整理为 openspec/specs 与 openspec/changes。
```

推荐第一条 OpenSpec 任务：

```text
/opsx:propose 将 LLM Broker 完整蓝图整理为 OpenSpec baseline specs。范围仅限文档和规格治理：从 AGENTS.md、LLM_Broker_Architecture_v13.md、.omo/drafts/llm-broker-complete-blueprint.md、.omo/drafts/llm-broker-v13-communication.md 提取已确认 requirements、non-negotiable invariants、open decisions 和 verification gates；不实现代码、不引入技术栈、不假设测试命令。
```

### 10.2 后续阶段：多代理研究或实现

推荐辅助链路：

```text
OpenCode + Oh-My-OpenAgent
```

使用前提：

```text
OpenCode 侧关闭 claude_code.skills / commands / plugins。
OpenCode 只读 AGENTS.md 和 openspec/ 作为事实源。
```

OpenCode 执行任务时应提示：

```text
读取 openspec/changes/<change-id>/proposal.md、design.md、tasks.md 和相关 specs。
严格执行 OpenSpec change，不要扩大范围。
Superpowers 只作为 Claude Code 侧执行纪律，不得覆盖 OpenSpec/AGENTS.md。
```

---

## 11. 安装和配置注意事项

### 11.1 Claude Code 侧

可以安装：

```text
OpenSpec
Superpowers
```

但它们的产物应留在 Claude Code 专用路径：

```text
.claude/
```

### 11.2 OpenCode 侧

推荐只安装：

```text
Oh-My-OpenAgent
OpenSpec 的 OpenCode 命令
```

不推荐同时安装 OpenCode 版 Superpowers，除非明确接受两个插件同时注入 prompt/skills 的复杂度。

### 11.3 OpenCode plugin 数组

低风险配置：

```json
{
  "plugin": [
    "oh-my-openagent"
  ]
}
```

较复杂配置，不作为当前默认推荐：

```json
{
  "plugin": [
    "oh-my-openagent",
    "superpowers@git+https://github.com/obra/superpowers.git"
  ]
}
```

如果使用后者，必须在 `AGENTS.md` 明确优先级：

```text
AGENTS.md 红线 > OpenSpec active change/specs > Superpowers 执行纪律 > Oh-My-OpenAgent 默认行为
```

---

## 12. 验证清单

### 12.1 Claude Code 验证

- 能看到 Superpowers。
- 能调用 OpenSpec 的 `/opsx:propose` / `/opsx:apply`。
- 生成或读取的是 `.claude/commands/opsx/`。
- 规格文件写入 `openspec/`。

### 12.2 OpenCode 验证

- Oh-My-OpenAgent 正常加载。
- 能读取 `AGENTS.md`。
- 能看到 `.opencode/commands/opsx-*.md`。
- 不读取 `.claude/commands`。
- 不读取 `.claude/skills`。
- 不加载 Claude Code Superpowers plugin。

### 12.3 最小自检提示

在 OpenCode 中可以让 agent 只做自检：

```text
请只做兼容性自检，不修改文件：
1. 说明你是否读取到了 AGENTS.md。
2. 说明是否能看到 OpenSpec 的 OpenCode opsx 命令。
3. 说明是否关闭了 Claude Code skills/commands/plugins 兼容来源。
4. 说明 Oh-My-OpenAgent 的 task/skill/oracle/librarian 等能力是否可用。
```

---

## 13. 最终决策记录

当前项目采用以下策略：

```text
1. Claude Code + OpenSpec + Superpowers 作为规格治理主链路。
2. OpenCode + Oh-My-OpenAgent 作为可选多代理执行链路。
3. 两边共享 AGENTS.md 和 openspec/。
4. OpenCode 侧默认关闭 Claude Code compatibility sources，避免读取 .claude/skills、commands、plugins。
5. 不在 OpenCode 侧默认安装 Superpowers plugin。
6. 不用 disabled_skills 作为禁用 Superpowers 的首选方案。
7. 如需禁外部 Superpowers skill，使用 skills.disable；如需完全隔离，使用 claude_code.skills/plugins/commands=false。
```

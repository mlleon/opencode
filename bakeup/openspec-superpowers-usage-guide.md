# OpenSpec + Superpowers 在 Claude Code 中的完整使用指南

> 本文档以一个「任务管理系统」项目为例，模拟从零开始的完整开发过程，
> 展示 OpenSpec 和 Superpowers 如何配合工作。
>
> - OpenSpec = 你主动执行的规格工作流
> - Superpowers = AI 执行过程中自动触发的工程方法论

---

## 第一阶段：项目初始化

### 1.1 创建项目

```bash
mkdir task-manager && cd task-manager
git init
npm init -y
```

### 1.2 安装工具

```bash
# 全局安装 OpenSpec
npm install -g @fission-ai/openspec@latest
```

然后打开 Claude Code：

```bash
claude
```

在 Claude Code 中安装 Superpowers 插件：

```
> /plugin install superpowers
```

### 1.3 初始化 OpenSpec

```bash
openspec init
```

交互式提示：

```
? Select the AI tools to configure: (Use arrow keys)
❯ ◉ Claude Code
  ○ Cursor
  ○ Windsurf
  ○ OpenCode
  ...
```

选择 `Claude Code`，回车确认。

**生成的目录结构：**

```
task-manager/
├── openspec/
│   ├── specs/                          # 规格目录（初始为空）
│   ├── changes/                        # 变更目录（初始为空）
│   └── config.yaml                     # 项目配置
├── .claude/
│   ├── commands/
│   │   └── opsx/                       # OpenSpec slash commands
│   │       ├── explore.md
│   │       ├── propose.md
│   │       ├── apply.md
│   │       ├── sync.md
│   │       └── archive.md
│   └── skills/                         # OpenSpec skills
│       ├── openspec-explore/
│       │   └── SKILL.md
│       ├── openspec-propose/
│       │   └── SKILL.md
│       ├── openspec-apply/
│       │   └── SKILL.md
│       └── ...
├── .opencode/                          # （如果有 OpenCode 配置也会生成）
└── package.json
```

### 1.4 编写 CLAUDE.md（项目级规则）

```markdown
# Task Manager

一个基于 Node.js + Express 的任务管理 REST API 项目。

## 技术栈
- Runtime: Node.js 20 LTS
- Framework: Express.js
- Database: PostgreSQL + Drizzle ORM
- Testing: Vitest

## 约束
- 所有 API 返回 JSON 格式
- 使用 TypeScript 严格模式
- 不引入外部状态管理库

## Priority Rules
- CLAUDE.md 红线 > OpenSpec active specs > Superpowers 方法论 > 默认行为
- OpenSpec 负责：需求规格、变更生命周期
- Superpowers 负责：工程执行纪律（TDD、验证、调试）
- 两者有歧义时，以 OpenSpec 为准
```

---

## 第二阶段：建立 Baseline 规格

此时 `openspec/specs/` 是空的。需要先为项目建立基础规格。

### 2.1 会话启动（Superpowers 静默注入）

打开 Claude Code，Superpowers 的 `SessionStart` hook 自动运行：

```
[内部发生 - 用户不可见]

1. hooks.json 解析 → 检测到 SessionStart 事件
2. 执行 hooks/session-start 脚本
3. 读取 skills/using-superpowers/SKILL.md
4. 以 additionalContext 注入到 Claude 的上下文中
   → TDD 方法论已就绪
   → systematic-debugging 已就绪
   → verification-before-completion 已就绪
   → brainstorming 已就绪
   → ... 共 13 个方法论技能
```

用户只看到普通启动画面，完全无感知。

### 2.2 创建 Baseline Specs

```
> /opsx:propose baseline-initial-specs

  范围：为任务管理系统建立初始规格 baseline。
  包含以下核心领域：
  - 任务 CRUD
  - 用户认证
  - 任务状态流转
  
  从 CLAUDE.md 中的技术约束和定位出发，
  不实现代码，只建立 openspec/specs/ 下的基础规格。
```

**Claude 响应：**

```
好的，我来为项目建立初始规格。

首先分析一下 CLAUDE.md 中的约束...

[内部发生 - Superpowers 叠加]
→ brainstorming skill 自动匹配
  （因为涉及"创造性工作 - 设计系统规格"）
→ Claude 开始主动提问和探讨

我需要确认几个问题：

1. 任务状态流转是否包含有限状态机？
   - 推荐：TODO → IN_PROGRESS → DONE（简单三态）
   
2. 用户认证方案选择：
   - A) JWT Bearer Token（推荐，REST API 标准方案）
   - B) Session + Cookie
   - C) API Key

3. 任务是否支持子任务嵌套？
   - 推荐：V1 不支持，保持简单

请确认或调整。
```

用户回答后，Claude 生成 baseline：

```
已创建 baseline 规格：

openspec/specs/
├── task-crud/
│   └── spec.md          ← 任务增删改查的核心规格
├── user-auth/
│   └── spec.md          ← 用户认证规格（JWT）
└── task-status/
    └── spec.md          ← 任务状态流转规格

每个 spec.md 包含：
- Requirements（GIVEN/WHEN/THEN 格式）
- Scenarios（验收场景）
- Constraints（约束条件）

Baseline 建立完成。后续所有 /opsx:propose 将基于这些规格做 delta。
```

---

## 第三阶段：第一个功能开发（完整循环）

以「任务标签功能」为例，展示完整的 explore → propose → apply → archive 循环。

### 3.1 探索阶段 `/opsx:explore`

```
> /opsx:explore 给任务加上标签功能，支持按标签筛选

[内部发生]
→ .claude/commands/opsx/explore.md 被加载执行
→ Claude 进入探索模式

Claude 响应：
```

```
进入探索模式 🧭

让我先了解一下现有的任务和标签相关代码...

[内部发生 - Superpowers 叠加]
→ systematic-debugging skill 未匹配（没有调试场景）
→ brainstorming skill 匹配（创建新功能）
→ Claude 开始结构化探索

探索完成，以下是我的分析：

## 现状分析
- openspec/specs/task-crud/spec.md 定义了 Tasks 表结构
- 当前有 3 个现有模型：User、Task、TaskEvent
- 使用 Drizzle ORM，schema 定义在 src/db/schema.ts

## 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A) 独立 Tag 表 + 多对多** | 灵活、可复用、可全局管理 | 多一张表、JOIN 查询 |
| B) Task 表内 JSON 数组 | 简单、无 JOIN | 无法全局查询标签、数据冗余 |
| C) 硬编码枚举 | 最快 | 无法扩展 |

**推荐方案 A**：独立 Tag 表 + TaskTag 多对多关联表。
这是标准的关系型建模方式，符合项目当前 Drizzle ORM 的使用模式。

是否需要我基于方案 A 进入 propose？
```

```
> 可以，基于方案 A
```

### 3.2 立项阶段 `/opsx:propose`

```
> /opsx:propose add-task-tags

  基于刚才的探讨，使用方案 A（独立 Tag 表 + 多对多），
  为任务系统添加标签功能。
```

```
[内部发生]
→ .claude/commands/opsx/propose.md 被加载执行
→ OpenSpec 读取 openspec/specs/ 下的现有规格
→ 分析哪些 specs 需要变更（task-crud）
→ 哪些是新增（tag-management）

Claude 响应：
```

```
已创建变更提案：

openspec/changes/add-task-tags/
├── proposal.md          ← 为什么做、做什么
├── specs/
│   ├── tag-management/
│   │   └── spec.md      ← 新增：标签管理规格
│   └── task-crud/
│       └── spec.md      ← 修改：任务 CRUD 增加标签关联
├── design.md            ← 技术方案
└── tasks.md             ← 实现任务清单

--- proposal.md 摘要 ---

## Why
用户需要按标签组织任务，支持筛选和分类。

## What Changes
- 新增 Tag 表和 TaskTag 多对多关联表
- 新增标签 CRUD API（/api/tags）
- 任务 API 支持标签字段（创建/更新/列表筛选）

## Capabilities
- New: tag-management（标签的完整生命周期）
- Modified: task-crud（任务关联标签）

## Impact
- 数据库：2 张新表 + migration
- API：新增 /api/tags 端点，修改 /api/tasks 端点
- 测试：对应单元测试 + 集成测试

--- tasks.md 摘要 ---

## 1. 数据库层
- [ ] 1.1 创建 Task 和 Tag 的 schema migration
- [ ] 1.2 在 Drizzle schema 中定义 Tag 和 TaskTag 表
- [ ] 1.3 添加数据库索引（tag_id, task_id）
- [ ] 1.4 运行 migration 验证

## 2. 标签管理 API
- [ ] 2.1 创建 POST /api/tags（新建标签）
- [ ] 2.2 创建 GET /api/tags（列出所有标签）
- [ ] 2.3 创建 PUT /api/tags/:id（更新标签）
- [ ] 2.4 创建 DELETE /api/tags/:id（删除标签）

## 3. 任务关联标签
- [ ] 3.1 修改 POST /api/tasks 支持 tags 字段
- [ ] 3.2 修改 PUT /api/tasks/:id 支持标签更新
- [ ] 3.3 修改 GET /api/tasks 支持 ?tags= 筛选

## 4. 集成测试
- [ ] 4.1 编写标签 CRUD 测试
- [ ] 4.2 编写任务关联标签测试
- [ ] 4.3 编写筛选测试

请审阅以上提案，确认无误后执行 /opsx:apply。
```

### 3.3 审阅提案（可选步骤）

用户可以直接编辑生成的文件：

```
> design.md 里面 Tag 表的 name 字段应该加 unique 约束，
> 不允许重复标签名
```

```
[内部发生]
→ Claude 读取 design.md，找到 Tag schema 部分
→ 添加 UNIQUE 约束
→ 写回文件

Claude 响应：
```

```
已更新 openspec/changes/add-task-tags/design.md：

  name text NOT NULL UNIQUE    ← 添加 UNIQUE 约束
  
同时在 specs/tag-management/spec.md 中增加：

## ADDED
### Requirement: Tag Name Uniqueness
The system MUST reject tag creation if a tag with the same name already exists.

#### Scenario: Duplicate tag name
- GIVEN a tag "urgent" already exists
- WHEN POST /api/tags with name "urgent"
- THEN respond with 409 Conflict and error message
```

### 3.4 执行阶段 `/opsx:apply`（核心演示）

```
> /opsx:apply
```

```
[内部发生 - 完整流程]

1. .claude/commands/opsx/apply.md 被加载执行
2. Claude 读取 openspec/changes/add-task-tags/tasks.md
3. [Superpowers 叠加] test-driven-development skill 匹配
   → Claude 对每个任务应用 TDD 方法论

Claude 响应：
```

```
开始执行 add-task-tags 变更。
读取 tasks.md，共 14 个任务，分 4 个阶段。

══════════════════════════════════════════
 阶段 1: 数据库层（任务 1.1 - 1.4）
══════════════════════════════════════════

--- 任务 1.1: 创建 migration ---

[内部发生 - Superpowers 叠加]
→ test-driven-development 自动触发
→ 要求先写测试再写 migration（此处不适用，跳过）

[直接执行 - 因为 migration 不是业务逻辑，TDD 不适用]

✓ 已生成 migration：
  20240120_add_tags_and_task_tags.sql

[内部发生 - Superpowers 叠加]
→ verification-before-completion 触发
→ Claude 验证 migration SQL 语法正确性

✓ Migration SQL 语法验证通过
✓ 外键约束方向正确（task_id → tasks, tag_id → tags）


--- 任务 1.2: Drizzle schema 定义 ---

[内部发生 - Superpowers 叠加]
→ test-driven-development 自动触发

[先写 schema，因为这是定义层不需要测试]

✓ 已在 src/db/schema.ts 添加：
  - Tag table (id, name, createdAt)
  - TaskTag table (taskId, tagId) + composite PK
  - 关系定义：Task ↔ Tag 多对多


--- 任务 1.3: 添加索引 ---

✓ 已添加：
  - idx_task_tags_task_id ON task_tags(task_id)
  - idx_task_tags_tag_id ON task_tags(tag_id)


--- 任务 1.4: 运行 migration ---

$ npm run db:migrate
✓ Migration 执行成功

[Superpowers 叠加: verification-before-completion]
✓ 验证 tasks 表和 tags 表外键关系正常

════════════════════════════════════
 阶段 2: 标签管理 API（任务 2.1 - 2.4）
════════════════════════════════════

--- 任务 2.1: POST /api/tags ---

[内部发生 - Superpowers 叠加]
→ test-driven-development 自动触发（此处适用）
→ 先写测试，再写实现

[Step 1: 写测试]

✓ 已创建 tests/api/tags.test.ts：

  describe('POST /api/tags', () => {
    it('创建成功，返回 201 和标签对象', async () => { ... })
    it('名称为空时返回 400', async () => { ... })
    it('名称重复时返回 409', async () => { ... })
  })

[运行测试 - 预期失败（功能未实现）]
$ npm test -- tests/api/tags.test.ts
✗ 404 Not Found（路由未注册，符合预期）

[Step 2: 写实现]

✓ 已创建 src/routes/tags.ts
✓ 已在 src/app.ts 注册路由

[Step 3: 再次测试 - 预期通过]
$ npm test -- tests/api/tags.test.ts
✓✓✓ 3 tests passed

[Superpowers 叠加: systematic-debugging 触发]
→ 检查边界情况
→ 补充了 name 字段的 trim() 和长度校验


--- 任务 2.2: GET /api/tags ---

[内部发生 - 同上流程：测试 → 失败 → 实现 → 通过]

[Superpowers 叠加: verification-before-completion 触发]
→ 验证返回的标签数组按 createdAt DESC 排序

✓ tests passed: 2/2


--- 任务 2.3: PUT /api/tags/:id ---
--- 任务 2.4: DELETE /api/tags/:id ---

[同上流程...]

✓ 阶段 2 全部完成（6/6 tests passed）

════════════════════════════════════
 阶段 3: 任务关联标签（任务 3.1 - 3.3）
════════════════════════════════════

--- 任务 3.1: 修改 POST /api/tasks 支持 tags 字段 ---

[Superpowers 叠加: test-driven-development]

[Step 1: 写测试]

✓ tests/api/tasks-with-tags.test.ts：

  describe('POST /api/tasks with tags', () => {
    it('创建任务同时关联标签', async () => { ... })
    it('标签不存在时返回 404 并报错', async () => { ... })
  })

[运行测试 - 当前失败]
✗ tags 字段返回 400（未支持，符合预期）

[Step 2: 实现]

✓ 修改 src/routes/tasks.ts createTask 函数
✓ 添加 tags 字段解析和多对多写入

[Step 3: 重新测试]

✓✓✓ 3 tests passed


--- 任务 3.2: 修改 PUT /api/tasks/:id ---
--- 任务 3.3: 修改 GET /api/tasks 支持标签筛选 ---

[同上流程，逐步完成...]

✓ 阶段 3 全部完成（5/5 tests passed）

══════════════════════════════════
 阶段 4: 集成测试（任务 4.1 - 4.3）
══════════════════════════════════

--- 任务 4.1: 标签 CRUD 集成测试 ---

[Superpowers 叠加: verification-before-completion 触发]
→ Claude 回顾 tasks.md，检查 4.1-4.3 是否覆盖了核心场景

✓ 集成测试编写完成

--- 任务 4.2: 任务关联标签集成测试 ---
--- 任务 4.3: 筛选集成测试 ---

[全部完成]

════════════════════════
 执行完成 - 验证汇总
════════════════════════

tasks.md 进度：14/14 完成 ✓

测试汇总：
  ✓ Unit tests:     22 passed
  ✓ Integration:     8 passed
  ✓ All:            30 passed

变更摘要：
  - 新增文件：4（schema migration, routes, tests, types）
  - 修改文件：3（schema.ts, app.ts, existing tasks route）

[Superpowers 叠加: verification-before-completion 最后一次触发]
→ 验证 tasks.md 中所有 14 个任务均已标记 [x] ✓
→ 验证 openspec/changes/add-task-tags/ 下所有 artifacts 一致 ✓

可以执行 /opsx:archive 归档此变更。
```

### 3.5 归档阶段 `/opsx:archive`

```
> /opsx:archive add-task-tags
```

```
[内部发生]
→ .claude/commands/opsx/archive.md 被加载执行
→ OpenSpec 读取 changes/add-task-tags/specs/ 下的 Delta Specs
→ 将 ADDED / MODIFIED / REMOVED 合并进 openspec/specs/

[步骤 1: 同步 Delta Specs]
→ openspec/specs/tag-management/spec.md   ← 新建（来自 delta ADDED）
→ openspec/specs/task-crud/spec.md        ← 追加标签相关内容

[步骤 2: 移动变更到 archive]
→ openspec/changes/archive/2025-06-20-add-task-tags/

Claude 响应：
```

```
归档完成 ✓

规格合并结果：
  ✓ tag-management/spec.md    已创建（新规格）
  ✓ task-crud/spec.md         已追加标签关联章节

变更已移至：
  openspec/changes/archive/2025-06-20-add-task-tags/

当前 openspec/specs/ 状态：
  ├── task-crud/spec.md           ← 含标签相关规格
  ├── task-status/spec.md         ← 未变动
  ├── tag-management/spec.md      ← 新增
  └── user-auth/spec.md           ← 未变动

下一个功能可以开始了。
```

---

## 第四阶段：后续功能迭代（简化展示）

### 4.1 第二个功能：添加任务优先级

```
> /opsx:explore 给任务加优先级（P0/P1/P2/P3）

Claude: （探索模式，分析现有规格和代码...）

> /opsx:propose add-task-priority

Claude: 生成变更提案...
  - Modified: task-crud（增加 priority 字段）

> /opsx:apply

Claude: 逐任务实现，TDD 方法论自动触发...

> /opsx:archive add-task-priority

openspec/specs/ 新增/更新：
  task-crud/spec.md 追加优先级相关内容
```

### 4.2 第三个功能：任务到期提醒

```
> /opsx:propose add-due-date-reminder

Claude: 生成变更提案...
  - Modified: task-crud（增加 dueDate 字段）
  - New: notification（提醒机制）

> /opsx:apply
> /opsx:archive add-due-date-reminder

openspec/specs/ 更新：
  task-crud/spec.md 追加到期日相关
  notification/spec.md 新增
```

---

## 项目最终形态

```
task-manager/
├── openspec/
│   ├── specs/                              ← 系统规格（随项目演进积累）
│   │   ├── task-crud/spec.md               ← 含标签、优先级、到期日
│   │   ├── task-status/spec.md             ← 状态流转
│   │   ├── tag-management/spec.md          ← 标签管理
│   │   ├── notification/spec.md            ← 通知提醒
│   │   └── user-auth/spec.md               ← 用户认证
│   │
│   ├── changes/                            ← 当前进行中的变更（可能为空）
│   │
│   └── changes/archive/                    ← 历史变更归档
│       ├── 2025-06-20-add-task-tags/
│       ├── 2025-06-22-add-task-priority/
│       └── 2025-06-25-add-due-date-reminder/
│
├── .claude/
│   ├── commands/opsx/                      ← OpenSpec slash commands
│   │   ├── explore.md
│   │   ├── propose.md
│   │   ├── apply.md
│   │   ├── sync.md
│   │   └── archive.md
│   └── skills/openspec-*/                  ← OpenSpec auxiliary skills
│
├── src/                                    ← 源代码
├── tests/                                  ← 测试代码
├── CLAUDE.md                               ← 项目规则 + 优先级定义
└── package.json
```

---

## 总结：两个工具的分工

```
┌─────────────────────────────────────────────────────────┐
│                    你（开发者）                           │
│                                                          │
│  决定"做什么"：                                          │
│  /opsx:explore  /opsx:propose  /opsx:apply  /opsx:archive│
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│               OpenSpec（规格管理层）                      │
│                                                          │
│  主动管理：                                               │
│  - 创建/读取 specs/、changes/ 下的文件                    │
│  - 维护 Delta Specs 的生命周期                            │
│  - 归档时合并规格                                         │
│  - 任务追踪（tasks.md checkbox）                          │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│              Superpowers（方法论层）                       │
│                                                          │
│  被动叠加：                                               │
│  - SessionStart hook 始终注入基础方法论                   │
│  - TDD：在写代码时自动要求先写测试                         │
│  - 验证：完成前自动要求验证实现                            │
│  - 调试：出现问题时自动应用系统化方法                      │
│  - 计划：做创造性工作时自动引导头脑风暴                    │
└─────────────────────────────────────────────────────────┘
```

**一句话总结：**
你只管用 OpenSpec 的流程推进开发，Superpowers 在背后约束 AI 不越界、不偷懒、不跳过测试。

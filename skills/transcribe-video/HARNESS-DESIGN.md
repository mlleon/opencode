# transcribe-video harness 优化设计备忘

## 1. 背景

`transcribe-video` 的初始改造目标，是把本地视频/音频转录结果整理成可追溯、可校验、可入库的原始资料，并写入项目级 `memory-source`：

```text
memory-source/raw/03-transcripts/<finalStem>.md
memory-source/assets/raw/transcripts/<finalStem>/
```

第一版已经围绕东方文化与生活美学做了 taxonomy 和结构化设计，重点覆盖：

- 古诗词
- 茶文化
- 器物之美
- 书写之美
- 茶室与空间
- 绿植与空间
- 生活美学
- 品牌表达
- 东方文化

但实际使用场景更宽：除东方生活美学外，也会处理 AI、Agent、品牌营销、数据分析、IT 技术、知识工作流等视频转录内容。

因此，后续优化方向不应继续无限增加细分 taxonomy，而应转向 **harness 驱动**。

---

## 2. 已确认的基础原则

### 2.1 raw 层定位

`memory-source/raw/03-transcripts/` 是原始资料层，不是二次创作层。

允许进入 raw 的内容：

- 原文转录
- 时间戳
- 分类结果
- 候选主题
- 候选观点
- 候选概念
- 待人工确认项

不应进入 raw 的内容：

- 无证据总结
- 自动文学化改写
- 自动品牌文案
- 无出处诗词解释
- 没有原文依据的文化判断

### 2.2 LLM 不能直接写最终 Markdown

大模型只能输出受控 JSON 候选，最终 Markdown 由脚本渲染。

脚本必须负责：

- 校验 JSON schema
- 校验证据来自原文
- 校验时间戳合法
- 校验 category/domain 合法
- 渲染最终 Markdown

### 2.3 所有结构化结果必须可追溯

任何主题、观点、概念、摘录、行动项，都必须能追溯到原文证据：

```json
{
  "text": "原文片段",
  "start": 0.0,
  "end": 12.5
}
```

---

## 3. 当前第一版实现状态

第一版已经实现了以下 pipeline：

```text
transcribe
  ↓
normalize
  ↓
segment
  ↓
classify
  ↓
assist
  ↓
structure
  ↓
postprocess
  ↓
validate
```

统一入口：

```bash
uv run --project "$HOME/.config/opencode/skills" --group transcribe-video -- \
  python -m scripts.transcribe_video run \
  --project-root "<project-root>" \
  --input "<video-or-audio-path>" \
  --language zh-CN \
  --structure-mode assisted
```

当前模型配置：

- assisted：`nvidia / moonshotai/kimi-k2.6`
- premiumReview：`pqapi / gpt-5.5`
- fallback：`litellm / glm-5.1-xhigh`

当前 taxonomy：

```text
culture_life_aesthetics   东方文化与生活美学
general_reflection        人生思考
ai_technology             AI / IT / 技术
business_marketing        商业 / 品牌 / 营销
data_analysis             数据分析
knowledge_workflow        知识管理 / 方法论 / 工作流
content_creation          内容创作
generic                   通用素材
```

其中 `object_aesthetics`、`tea_culture`、`ru_porcelain` 等已降级为 `culture_life_aesthetics.secondaryHints`，不再作为独立一级 domain。

已新增 `analyze` 阶段：当已转录文本出现高置信新二级方向时，系统会在 staging/review 中生成候选，不直接修改正式 taxonomy 或测试。

---

## 4. 为什么需要 harness 化

如果每新增一个方向都维护一套完整配置：

```text
keywords
sections
templates
tests
```

长期会不可维护。

用户未来可能继续涉猎：

- 心理学
- 商业模式
- 教育
- 历史人物
- 内容创作
- 产品设计
- 空间设计
- 香道
- 园林
- 宋式生活
- 消费趋势
- AI Agent
- 数据分析
- 营销增长
- IT 技术

如果每个方向都变成硬编码 domain，taxonomy 会越来越重，模板会越来越碎。

所以应从：

```text
taxonomy 决定模板
```

升级为：

```text
harness 决定结构
taxonomy 只提供一级分类与提示
LLM 在 schema 内生成细分主题候选
脚本校验并渲染 Markdown
```

---

## 5. harness 的含义

这里的 harness 可以理解为：

```text
固定流程
+ 固定 schema
+ 固定证据规则
+ 固定输出边界
+ 可变领域理解
```

也就是：

```text
脚本控制“形状”
大模型理解“内容”
```

大模型可以判断主题和细分方向，但不能突破字段结构，也不能绕过证据校验。

---

## 6. 推荐的一级 category

不要维护几十个细分 domain。建议保留 8–10 个稳定一级类：

```text
culture_life_aesthetics   东方文化与生活美学
general_reflection        人生思考
ai_technology             AI / IT / 技术
business_marketing        商业 / 品牌 / 营销
data_analysis             数据分析
knowledge_workflow        知识管理 / 方法论 / 工作流
content_creation          内容创作
generic                   通用素材
```

当前已有细分方向可以降级为 hints：

```json
{
  "primaryCategories": {
    "culture_life_aesthetics": {
      "name": "东方文化与生活美学",
      "hints": [
        "poetry",
        "tea_culture",
        "object_aesthetics",
        "calligraphy",
        "tea_room",
        "green_plant_space",
        "life_aesthetics",
        "culture"
      ]
    },
    "ai_technology": {
      "name": "AI / IT / 技术",
      "hints": [
        "ai_agents",
        "it_technology",
        "software_engineering",
        "agent_skill_design"
      ]
    }
  }
}
```

脚本只强校验一级 category 合法。细分主题由 LLM 生成，但必须带 evidence。

---

## 7. 推荐的通用 harness schema

当前 `llm_schema.json` 比较窄，偏向生活美学候选字段：

```json
{
  "blocks": [
    {
      "title": "",
      "domains": [],
      "aestheticExpressionCandidates": [],
      "cultureReferenceCandidates": [],
      "brandExpressionCandidates": []
    }
  ]
}
```

建议升级为通用 schema：

```json
{
  "primaryCategory": "string",
  "secondaryCategories": ["string"],
  "contentType": "string",
  "topics": [
    {
      "name": "string",
      "type": "string",
      "evidence": []
    }
  ],
  "keyPoints": [
    {
      "point": "string",
      "evidence": []
    }
  ],
  "concepts": [
    {
      "name": "string",
      "definitionCandidate": "string",
      "evidence": []
    }
  ],
  "quotes": [
    {
      "text": "string",
      "whyImportant": "string",
      "evidence": []
    }
  ],
  "actionableInsights": [
    {
      "action": "string",
      "evidence": [],
      "reviewRequired": true
    }
  ],
  "openQuestions": [
    {
      "question": "string",
      "reason": "string"
    }
  ],
  "reviewRequired": true
}
```

这个 schema 可以同时承接：

- 苏东坡人生哲思
- 茶文化
- AI Agent Skill
- 品牌营销
- 数据分析
- IT 技术

---

## 8. 推荐统一 Markdown 模板

不必每个领域一套模板。建议统一为：

```markdown
# 视频转录：标题

## 资料说明

## 分类结果

## 主题结构

## 关键观点

## 概念 / 术语

## 重要原文摘录

## 可行动洞察候选

## 待确认问题

## 原文转录
```

空章节可以隐藏，或写“无”。

### 示例：苏东坡样本

```markdown
## 主题结构
- 苏东坡的超然心境
- 外部困境与心境选择
- 重新出发

## 重要原文摘录
...
```

### 示例：Perplexity Skill 样本

```markdown
## 主题结构
- Skill 是上下文税
- Description 是路由触发器
- Eval 先行
- Negative examples 的价值

## 概念 / 术语
- context tax
- routing boundary
- skill hierarchy
```

同一模板即可承接不同领域。

---

## 9. 三个历史样本分析

### 9.1 苏东坡 / 超然台 / 人生态度

文件：

```text
生活不一定时时如我们所愿，但以什么心境来体验人生百态，却是我们可以选择的。#苏东坡 #知识追光 @微信派 _xWT111.txt
```

内容核心：

- 苏东坡
- 密州
- 超然台
- 诗词
- 外部处境不如意
- 心境调整
- 重新出发

当前 taxonomy 可命中：

```text
poetry
culture
life_aesthetics
```

更适合 harness category：

```text
general_reflection
culture_life_aesthetics
```

### 9.2 苏东坡 / 庐山 / 人生视角

文件：

```text
十年前的你会想到十年后的人生剧本么？#苏东坡 #庐山_xWT111.txt
```

内容核心：

- 苏东坡
- 庐山
- 题西林壁
- 人生困局
- 跳脱视角
- 命运的长远视角

更适合 harness category：

```text
general_reflection
culture_life_aesthetics
```

### 9.3 Perplexity / Skill / Agent 技术方法论

文件：

```text
Perplexity：你这样写 Skill，就是造垃圾——精读perplexity《Designing, Refining, and Maintaining Agent Skills at Perplexity》...
```

内容核心：

- Skill 是上下文税
- description 是路由触发器
- 先写 eval
- negative examples
- scripts / references / assets / config 分层
- Agent skill 设计方法论

当前 taxonomy 明显不足。

更适合 harness category：

```text
knowledge_workflow
ai_technology
content_creation
```

---

## 10. 代码库审查与 Oracle 共识

分析结果一致：当前架构可保留，但以下部分需要优化：

1. `content_taxonomy.json` 过窄，偏东方生活美学。
2. `classify.py` 只做关键词 exact match。
3. `structure.py` 旧 `extract_keywords()` 会过滤纯英文技术词。
4. `assist.py` prompt 写着“东方生活美学视频转录资料”，对 AI/技术内容有偏置。
5. `generic` 太弱，无法高质量承接 AI/技术/营销/数据类内容。
6. 测试目前偏生活美学，没有覆盖 Perplexity / AI / 技术 / 数据样本。

共同建议：

```text
固定 harness schema
少量一级 category
细分主题由 LLM 生成
脚本校验证据和渲染
```

---

## 11. 两个可选后续方案

### 方案 A：轻量扩展现有 taxonomy

直接新增：

```text
general_reflection
ai_agents
it_technology
data_analysis
brand_marketing
knowledge_workflow
```

优点：

- 改动小
- 兼容当前代码
- 很快能提升结果

缺点：

- 长期还是会越来越重

### 方案 B：harness 化重构

改为：

```text
固定通用 schema
少量一级 category
LLM 生成细分 topics / concepts / keyPoints
脚本统一渲染 Markdown
```

优点：

- 长期可扩展
- 适合多领域内容
- 不需要每新增方向就重写 taxonomy/template

缺点：

- 需要改 `llm_schema.json`
- 需要改 `assist.py`
- 需要改 `schema.py`
- 需要改 `structure.py`
- 需要补测试

推荐方向：**方案 B**，但可以分阶段实施。

---

## 12. 推荐后续实施顺序

如果后续执行 harness 化重构，建议顺序：

1. 先写测试：苏东坡样本、Perplexity Skill 样本、AI/技术/营销混合样本。
2. 修改 `content_taxonomy.json` 为一级 category + hints。
3. 修改 `llm_schema.json` 为通用 harness schema。
4. 修改 `assist.py` prompt：从“东方生活美学”改成“多领域 transcript 结构化助手”。
5. 修改 `schema.py`：校验 topics/keyPoints/concepts/quotes/actionableInsights 的 evidence。
6. 修改 `structure.py`：用统一 Markdown 模板渲染 harness JSON。
7. 保留 deterministic fallback。
8. 跑完整测试：`transcribe-video` 和 `document-parser`。

---

## 13. 当前建议结论

不建议继续靠无限新增细分 domain 扩展。

更合理的方向是：

> 用脚本构建稳定 harness，用大模型在字段和证据约束内做主题理解；字段结构不变，内容随视频变化。

这样既保留 raw 入库的可靠性，又避免每来一个新方向就重新设计 taxonomy。

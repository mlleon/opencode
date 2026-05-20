---
name: document-parser
description: |
  通用文档解析服务（多后端）。当用户需要解析 PDF/Word/PPT/图片文件，并希望提取文字、结构化内容、Markdown/JSON 输出时使用。

  默认使用 MinerU v4 精准解析；仅当 MinerU 明确命中“额度/限流”类错误时，才会对 PDF/图片自动回退 PaddleOCR Jobs API（降级 OCR-only 输出，会在输出中标注 warnings）。

  触发场景：
  - “帮我解析这个 PDF/Word/PPT/图片”
  - “把这份扫描件 OCR 出文字”
  - “把文档转成 Markdown/JSON”
  - 用户上传文档并要求提取/识别/转换
---

# Document Parser Skill

## 能力边界

- 支持输入：本地文件路径或 URL
- 支持格式：
  - MinerU：PDF/Word/PPT/图片（以 MinerU 支持为准）
  - PaddleOCR 回退：仅 PDF/图片
- 回退策略：仅 MinerU 明确配额/限频错误触发（v1 保守）

## 输出规则（强约束）

- 默认输出根目录：当前工作目录（CWD）
- 可选参数：`--output-dir` 指定输出根目录（控制所有产物）
- 统一输出子目录：`document_parser_output/<stem>/`
  - `normalized/document.md`（离线可复现：图片本地化 + 相对路径）
  - `normalized/document.json`（规范化 envelope + artifacts + warnings）
  - `normalized/images/`（Markdown 引用图片必须在此目录）
  - `raw/mineru/`、`raw/paddleocr/`（后端原始工件）

## 负例（不应加载）

- “解释这段代码/报错是什么意思”（不是文档解析）
- “帮我写一份简历/合同模板”（不是解析现有文档）

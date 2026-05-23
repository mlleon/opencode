#!/usr/bin/env python3
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
  from taxonomy import Taxonomy, load_taxonomy
except ImportError:
  from .taxonomy import Taxonomy, load_taxonomy


@dataclass(frozen=True)
class Segment:
  start: float
  end: float
  text: str


def format_timestamp(seconds: float) -> str:
  total_seconds = int(seconds)
  minutes = total_seconds // 60
  remaining_seconds = total_seconds % 60
  return f"{minutes:02d}:{remaining_seconds:02d}"


def load_segments_from_json(json_path: Path) -> list[Segment]:
  data = json.loads(json_path.read_text(encoding="utf-8"))
  raw_segments = data.get("segments")
  if not isinstance(raw_segments, list):
    raise ValueError("Invalid transcript json: missing segments")

  segments: list[Segment] = []
  for item in raw_segments:
    if not isinstance(item, dict):
      continue
    start = float(item.get("start", 0.0))
    end = float(item.get("end", start))
    text = str(item.get("text", "")).strip()
    if not text:
      continue
    segments.append(Segment(start=start, end=end, text=text))
  return segments


def _collect_text(segments: list[Segment]) -> str:
  return "\n".join(seg.text for seg in segments)


def extract_keywords(text: str, limit: int = 8) -> list[str]:
  # 只做基于原文的轻量关键词抽取，不引入外部模型，避免“编造”。
  # 原策略对中文会生成大量“切块式伪词”，这里改为：
  # 1) 先按常见标点切成短语
  # 2) 过滤太短/太长/高噪声短语
  # 3) 按出现频次排序
  phrases = re.split(r"[\n\r\t\s，。！？；：、,.!?;:（）()\[\]【】<>《》\"\']+", text)
  phrases = [p.strip() for p in phrases if p and p.strip()]
  if not phrases:
    return []

  stopwords = {
    "这个", "那个", "我们", "你们", "他们", "就是", "然后", "所以", "因为", "但是",
    "如果", "一个", "一些", "这样", "那样", "没有", "不是", "可能", "觉得",
    "今天", "现在", "时候", "问题", "东西", "进行", "这种", "那种",
    "的话", "其实", "然后呢", "可以说", "基本上",
  }

  counter: Counter[str] = Counter()
  for phrase in phrases:
    if phrase in stopwords:
      continue
    if len(phrase) < 2:
      continue
    if len(phrase) > 20:
      continue
    if not re.search(r"[\u4e00-\u9fff]", phrase):
      continue
    counter[phrase] += 1

  return [token for token, _count in counter.most_common(limit)]


def build_timeline_lines(segments: list[Segment], group_sec: int = 60) -> list[str]:
  if not segments:
    return []

  groups: dict[int, list[Segment]] = {}
  for seg in segments:
    bucket = int(seg.start) // group_sec
    groups.setdefault(bucket, []).append(seg)

  lines: list[str] = []
  for bucket in sorted(groups.keys()):
    group = groups[bucket]
    start = min(s.start for s in group)
    end = max(s.end for s in group)
    snippet = " ".join(s.text for s in group).strip()
    if len(snippet) > 160:
      snippet = snippet[:160].rstrip() + "…"
    lines.append(f"- {format_timestamp(start)}-{format_timestamp(end)} {snippet}")
  return lines


def build_key_quotes(segments: list[Segment], limit: int = 6) -> list[str]:
  # 关键引用严格从原文 segment 中抽取，避免后处理“润色导致失真”。
  ranked = sorted(
    (seg for seg in segments if seg.text.strip()),
    key=lambda s: len(s.text),
    reverse=True,
  )
  quotes: list[str] = []
  for seg in ranked[:limit]:
    ts = format_timestamp(seg.start)
    quotes.append(f"> {seg.text}\n- {ts}")
  return quotes


def build_markdown_note(
  source: str,
  language: str,
  segments: list[Segment],
) -> str:
  text = _collect_text(segments)
  keywords = extract_keywords(text)
  timeline_lines = build_timeline_lines(segments)
  key_quotes = build_key_quotes(segments)

  frontmatter_lines = [
    "---",
    f"source: \"{source}\"",
    f"language: \"{language}\"",
    f"created: {date.today().isoformat()}",
    "tags: [transcript, video]",
    "---",
    "",
  ]

  summary_lines = [
    "# Summary",
    "- 本笔记为自动生成，仅基于转录文本抽取与整理；如需引用请人工校对。",
  ]
  if keywords:
    summary_lines.append("- 关键词：" + "、".join(keywords[:8]))
  else:
    summary_lines.append("- 关键词：无（转录内容过短或无法提取）")
  summary_lines.append("")

  topics_lines = ["# Topics"]
  if keywords:
    topics_lines.extend([f"- {kw}" for kw in keywords[:8]])
  else:
    topics_lines.append("- （空）")
  topics_lines.append("")

  timeline_section = ["# Timeline"]
  if timeline_lines:
    timeline_section.extend(timeline_lines)
  else:
    timeline_section.append("- （空）")
  timeline_section.append("")

  quotes_section = ["# Key Quotes"]
  if key_quotes:
    quotes_section.extend(key_quotes)
  else:
    quotes_section.append("> （空）")
  quotes_section.append("")

  action_items = [
    "# Action Items",
    "- [ ] 无明确行动项（自动生成）",
    "",
  ]

  tags_section = ["# Tags"]
  if keywords:
    tags_section.append("- " + " ".join(f"#{kw}" for kw in keywords[:6]))
  else:
    tags_section.append("- #transcript")
  tags_section.append("")

  links_section = ["# Obsidian Links"]
  if keywords:
    links_section.extend([f"- [[{kw}]]" for kw in keywords[:10]])
  else:
    links_section.append("- （空）")
  links_section.append("")

  return "\n".join(
    frontmatter_lines
    + summary_lines
    + topics_lines
    + timeline_section
    + quotes_section
    + action_items
    + tags_section
    + links_section
  )


def structure_transcript_json(transcript_json_path: Path, output_md_path: Path) -> None:
  data = json.loads(transcript_json_path.read_text(encoding="utf-8"))
  source = str(data.get("source", transcript_json_path.stem))
  language = str(data.get("language", "zh-CN"))
  segments = load_segments_from_json(transcript_json_path)
  markdown = build_markdown_note(source=source, language=language, segments=segments)
  output_md_path.write_text(markdown, encoding="utf-8")


def _format_frontmatter_list(values: list[str]) -> list[str]:
  if not values:
    return ["[]"]
  return [""] + [f"  - {value}" for value in values]


def _load_json(path: Path) -> dict[str, object]:
  data = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError(f"JSON 必须是对象: {path}")
  return data


def build_memory_source_markdown(
  normalized_payload: dict[str, object],
  segments_payload: dict[str, object],
  classification_payload: dict[str, object],
  assist_payload: dict[str, object] | None = None,
  taxonomy: Taxonomy | None = None,
  structure_mode: str = "deterministic",
  llm_error: str = "",
) -> str:
  actual_taxonomy = taxonomy or load_taxonomy()
  primary = str(classification_payload.get("primaryCategory") or classification_payload.get("primaryDomain", "generic"))
  raw_secondary = classification_payload.get("secondaryCategories") or classification_payload.get("secondaryDomains")
  secondary = [str(value) for value in raw_secondary if isinstance(value, str)] if isinstance(raw_secondary, list) else []
  source = str(normalized_payload.get("source", ""))
  language = str(normalized_payload.get("language", "zh-CN"))
  source_type = str(normalized_payload.get("sourceType", "unknown"))
  llm_used = bool(assist_payload)

  frontmatter = [
    "---",
    "source_type: transcript",
    "media_type: video",
    f"source_file: \"{source}\"",
    f"language: {language}",
    f"transcript_source: \"{source_type}\"",
    f"structure_mode: {structure_mode}",
    f"llm_used: {str(llm_used).lower()}",
    f"primary_category: {primary}",
    f"primary_domain: {primary}",
    "secondary_categories:" + ("" if secondary else " []"),
  ]
  if secondary:
    frontmatter.extend([f"  - {domain_id}" for domain_id in secondary])
  frontmatter.append("secondary_domains:" + ("" if secondary else " []"))
  if secondary:
    frontmatter.extend([f"  - {domain_id}" for domain_id in secondary])
  frontmatter.extend([
    f"taxonomy_version: {classification_payload.get('taxonomyVersion', actual_taxonomy.version)}",
    "review_status: pending",
    f"created: {date.today().isoformat()}",
  ])
  if llm_error:
    frontmatter.append(f"llm_error: \"{llm_error.replace(chr(34), '')}\"")
  frontmatter.extend(["---", ""])

  title = Path(source).stem if source else "未命名转录"
  lines = frontmatter + [
    f"# 视频转录：{title}",
    "",
    "## 资料说明",
    "",
    "- 本文档为视频/音频转录资料入库稿，所有结构化内容均为候选，默认需要人工复核。",
    "- 最终 Markdown 应归档到 `memory-source/raw/03-transcripts/`。",
    "- 原始 TXT/JSON/SRT 等支撑材料应保存在 `memory-source/assets/raw/transcripts/` 下。",
    "",
    "## 分类结果",
    "",
    f"- 一级分类：{actual_taxonomy.domains.get(primary, actual_taxonomy.domains['generic']).name} (`{primary}`)",
  ]
  if secondary:
    lines.append("- 二级标签：" + "、".join(f"`{value}`" for value in secondary))
  lines.extend([
    f"- 置信度：{classification_payload.get('confidence', 'low')}",
    "- 状态：待人工确认",
    "",
    "## 主题结构",
    "",
  ])

  blocks = segments_payload.get("blocks", [])
  rendered_topics = False
  topics = assist_payload.get("topics") if assist_payload else []
  if isinstance(topics, list):
    for item in topics:
      if isinstance(item, dict):
        lines.append(f"- {item.get('name', '未命名主题')}")
        rendered_topics = True
  if not rendered_topics:
    lines.append("- [ ] 候选主题待人工确认")
  lines.extend(["", "## 关键观点", ""])
  rendered_points = False
  key_points = assist_payload.get("keyPoints") if assist_payload else []
  if isinstance(key_points, list):
    for item in key_points:
      if isinstance(item, dict):
        lines.append(f"- {item.get('point', '未命名观点')}")
        rendered_points = True
  if not rendered_points:
    lines.append("- [ ] 候选观点待人工确认")
  lines.extend(["", "## 概念 / 术语", ""])
  rendered_concepts = False
  concepts = assist_payload.get("concepts") if assist_payload else []
  if isinstance(concepts, list):
    for item in concepts:
      if isinstance(item, dict):
        lines.append(f"- {item.get('name', '未命名概念')}：{item.get('definitionCandidate', '')}")
        rendered_concepts = True
  if not rendered_concepts:
    lines.append("- [ ] 候选概念待人工确认")
  lines.extend(["", "## 重要原文摘录", ""])
  if isinstance(blocks, list):
    for block in blocks:
      if isinstance(block, dict):
        lines.append(f"- {format_timestamp(float(block.get('start', 0.0)))}-{format_timestamp(float(block.get('end', 0.0)))} {str(block.get('text', '')).splitlines()[0][:80]}")
  lines.extend(["", "## 可行动洞察候选", ""])
  rendered_actions = False
  actionable_insights = assist_payload.get("actionableInsights") if assist_payload else []
  if isinstance(actionable_insights, list):
    for item in actionable_insights:
      if isinstance(item, dict):
        lines.append(f"- [ ] {item.get('action', '未命名行动候选')}")
        rendered_actions = True
  if not rendered_actions:
    lines.append("- [ ] 无明确行动候选")
  lines.extend(["", "## 待确认问题", ""])
  rendered_questions = False
  open_questions = assist_payload.get("openQuestions") if assist_payload else []
  if isinstance(open_questions, list):
    for item in open_questions:
      if isinstance(item, dict):
        lines.append(f"- {item.get('question', '未命名问题')}")
        rendered_questions = True
  if not rendered_questions:
    lines.append("- [ ] 核对转录准确性")

  if assist_payload:
    lines.extend(["## 大模型辅助候选", ""])
    assist_blocks = assist_payload.get("blocks", [])
    if isinstance(assist_blocks, list):
      for block in assist_blocks:
        if not isinstance(block, dict):
          continue
        lines.extend([f"### {block.get('title', block.get('blockId', '未命名片段'))}", ""])
        evidence = block.get("evidence", [])
        if isinstance(evidence, list):
          for item in evidence:
            if isinstance(item, dict):
              lines.append(f"- {format_timestamp(float(item.get('start', 0.0)))}-{format_timestamp(float(item.get('end', 0.0)))}：{item.get('text', '')}")
        lines.append("")

  lines.extend(["", "## 原文转录", ""])
  raw_segments = normalized_payload.get("segments", [])
  if isinstance(raw_segments, list):
    for item in raw_segments:
      if isinstance(item, dict):
        lines.append(f"### {format_timestamp(float(item.get('start', 0.0)))}")
        lines.append(str(item.get("text", "")))
        lines.append("")

  lines.extend(["## 处理警告", "", "- [ ] 如有 LLM 或分类警告，请结合支撑材料人工复核。", ""])
  return "\n".join(lines)


def structure_pipeline_outputs(
  normalized_json_path: Path,
  segments_json_path: Path,
  classification_json_path: Path,
  output_md_path: Path,
  assist_json_path: Path | None = None,
  structure_mode: str = "deterministic",
  llm_error: str = "",
) -> str:
  normalized_payload = _load_json(normalized_json_path)
  segments_payload = _load_json(segments_json_path)
  classification_payload = _load_json(classification_json_path)
  assist_payload = _load_json(assist_json_path) if assist_json_path and assist_json_path.exists() else None
  markdown = build_memory_source_markdown(
    normalized_payload=normalized_payload,
    segments_payload=segments_payload,
    classification_payload=classification_payload,
    assist_payload=assist_payload,
    structure_mode=structure_mode,
    llm_error=llm_error,
  )
  output_md_path.parent.mkdir(parents=True, exist_ok=True)
  output_md_path.write_text(markdown, encoding="utf-8")
  return markdown


def main() -> None:
  if len(sys.argv) < 2:
    print("Usage: structure.py <transcript.json> [output.md]", file=sys.stderr)
    raise SystemExit(1)

  transcript_json_path = Path(sys.argv[1]).resolve()
  if len(sys.argv) >= 3:
    output_md_path = Path(sys.argv[2]).resolve()
  else:
    output_md_path = transcript_json_path.with_suffix(".md")

  structure_transcript_json(transcript_json_path, output_md_path)
  print(f"Saved to {output_md_path}")


if __name__ == "__main__":
  main()

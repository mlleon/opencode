#!/usr/bin/env python3
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


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

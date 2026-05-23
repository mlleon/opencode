#!/usr/bin/env python3
import json
from pathlib import Path


def load_transcript_payload(transcript_json_path: Path) -> dict[str, object]:
  data = json.loads(transcript_json_path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError("transcript json 必须是对象")
  return data


def normalize_transcript_payload(payload: dict[str, object]) -> dict[str, object]:
  raw_segments = payload.get("segments")
  if not isinstance(raw_segments, list):
    raise ValueError("transcript json 缺少 segments")

  segments: list[dict[str, object]] = []
  for index, item in enumerate(raw_segments):
    if not isinstance(item, dict):
      continue
    text = str(item.get("text", "")).strip()
    if not text:
      continue
    start = _to_float(item.get("start"), 0.0)
    end = _to_float(item.get("end"), start)
    segments.append({
      "id": f"s{index + 1:04d}",
      "start": start,
      "end": max(start, end),
      "text": text,
    })

  duration = 0.0
  if segments:
    duration = max(_to_float(seg.get("end"), 0.0) for seg in segments)

  return {
    "source": str(payload.get("source", "")),
    "outputDir": str(payload.get("output_dir", "")),
    "language": str(payload.get("language", "zh-CN")),
    "sourceType": str(payload.get("source_type", "unknown")),
    "durationSec": duration,
    "segments": segments,
  }


def write_normalized_outputs(payload: dict[str, object], output_json_path: Path, output_md_path: Path) -> None:
  output_json_path.parent.mkdir(parents=True, exist_ok=True)
  output_md_path.parent.mkdir(parents=True, exist_ok=True)
  output_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
  lines = [
    "# 规范化转录",
    "",
    f"- 来源：{payload.get('source', '')}",
    f"- 语言：{payload.get('language', 'zh-CN')}",
    f"- 转录来源：{payload.get('sourceType', 'unknown')}",
    "",
    "## 原文转录",
  ]
  segments = payload.get("segments")
  if not isinstance(segments, list):
    segments = []
  for item in segments:
    if isinstance(item, dict):
      lines.append(f"- {format_timestamp(float(item.get('start', 0.0)))} {item.get('text', '')}")
  output_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _to_float(value: object, default: float) -> float:
  if isinstance(value, (int, float, str)):
    try:
      return float(value)
    except ValueError:
      return default
  return default


def format_timestamp(seconds: float) -> str:
  total = int(seconds)
  minutes = total // 60
  remaining = total % 60
  return f"{minutes:02d}:{remaining:02d}"


def normalize_transcript_file(transcript_json_path: Path, output_json_path: Path, output_md_path: Path) -> dict[str, object]:
  normalized = normalize_transcript_payload(load_transcript_payload(transcript_json_path))
  write_normalized_outputs(normalized, output_json_path, output_md_path)
  return normalized

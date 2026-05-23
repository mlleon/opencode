#!/usr/bin/env python3
import json
from pathlib import Path


def build_blocks(normalized_payload: dict[str, object], max_duration_sec: float = 180.0, max_chars: int = 1800) -> dict[str, object]:
  raw_segments = normalized_payload.get("segments")
  if not isinstance(raw_segments, list):
    raise ValueError("normalized payload 缺少 segments")

  blocks: list[dict[str, object]] = []
  current: list[dict[str, object]] = []
  block_start = 0.0
  current_chars = 0

  def flush() -> None:
    nonlocal current, block_start, current_chars
    if not current:
      return
    block_id = f"b{len(blocks) + 1:03d}"
    block_end = max(_to_float(item.get("end"), 0.0) for item in current)
    text = "\n".join(str(item.get("text", "")).strip() for item in current if str(item.get("text", "")).strip())
    blocks.append({
      "blockId": block_id,
      "start": block_start,
      "end": block_end,
      "segmentIds": [str(item.get("id", "")) for item in current],
      "text": text,
    })
    current = []
    current_chars = 0

  for item in raw_segments:
    if not isinstance(item, dict):
      continue
    text = str(item.get("text", "")).strip()
    if not text:
      continue
    start = _to_float(item.get("start"), 0.0)
    end = _to_float(item.get("end"), start)
    if not current:
      block_start = start
    should_flush = bool(current) and (
      end - block_start > max_duration_sec or current_chars + len(text) > max_chars
    )
    if should_flush:
      flush()
      block_start = start
    current.append(item)
    current_chars += len(text)
  flush()

  return {
    "source": normalized_payload.get("source", ""),
    "language": normalized_payload.get("language", "zh-CN"),
    "blocks": blocks,
  }


def _to_float(value: object, default: float) -> float:
  if isinstance(value, (int, float, str)):
    try:
      return float(value)
    except ValueError:
      return default
  return default


def write_blocks(blocks_payload: dict[str, object], output_path: Path) -> None:
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(blocks_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def segment_normalized_file(normalized_json_path: Path, output_path: Path) -> dict[str, object]:
  data = json.loads(normalized_json_path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError("normalized json 必须是对象")
  blocks_payload = build_blocks(data)
  write_blocks(blocks_payload, output_path)
  return blocks_payload

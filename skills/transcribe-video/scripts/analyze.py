#!/usr/bin/env python3
import json
from pathlib import Path

try:
  from taxonomy import load_taxonomy
except ImportError:
  from .taxonomy import load_taxonomy


def _make_evidence(block: dict[str, object], text: str) -> dict[str, object]:
  start = block.get("start", 0.0)
  end = block.get("end", start)
  return {
    "text": text,
    "start": float(start) if isinstance(start, (int, float, str)) else 0.0,
    "end": float(end) if isinstance(end, (int, float, str)) else 0.0,
    "blockId": str(block.get("blockId", "")),
  }


def analyze_transcript_payload(segments_payload: dict[str, object]) -> dict[str, object]:
  taxonomy = load_taxonomy()
  blocks = segments_payload.get("blocks")
  if not isinstance(blocks, list):
    raise ValueError("analyze 输入缺少 blocks")

  text = "\n".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
  primary_candidates: list[dict[str, object]] = []
  secondary_candidates: list[dict[str, object]] = []
  suggested_hints: list[dict[str, object]] = []

  for category_id, category in taxonomy.primaryCategories.items():
    if category_id == "generic":
      continue
    matched = [keyword for keyword in category.keywords if keyword and keyword in text]
    if matched:
      evidence_block = next((block for block in blocks if isinstance(block, dict) and matched[0] in str(block.get("text", ""))), None)
      evidence = [_make_evidence(evidence_block, matched[0])] if isinstance(evidence_block, dict) else []
      primary_candidates.append({"category": category_id, "confidence": min(1.0, 0.5 + len(matched) / 10), "evidence": evidence})
    for hint in category.secondaryHints or []:
      hint_text = hint.replace("_", " ")
      if hint in text or hint_text in text:
        evidence_block = next((block for block in blocks if isinstance(block, dict) and (hint in str(block.get("text", "")) or hint_text in str(block.get("text", "")))), None)
        evidence = [_make_evidence(evidence_block, hint if hint in text else hint_text)] if isinstance(evidence_block, dict) else []
        secondary_candidates.append({"name": hint, "matchedExistingHint": True, "confidence": 0.9, "evidence": evidence})

  known_hints = {
    hint
    for category in taxonomy.primaryCategories.values()
    for hint in (category.secondaryHints or [])
  }
  if "context engineering" in text and "context_engineering" not in known_hints:
    evidence_block = next((block for block in blocks if isinstance(block, dict) and "context engineering" in str(block.get("text", ""))), None)
    evidence = [_make_evidence(evidence_block, "context engineering")] if isinstance(evidence_block, dict) else []
    suggested_hints.append({
      "name": "context_engineering",
      "primaryCategory": "ai_technology",
      "aliases": ["context_tax", "context_management"],
      "reason": "转录内容明确讨论 context engineering、上下文税或触发边界。",
      "evidence": evidence,
      "risk": "medium",
    })

  decision = "stage_and_pause" if suggested_hints else "auto_continue"
  return {
    "primaryCategoryCandidates": primary_candidates or [{"category": "generic", "confidence": 0.1, "evidence": []}],
    "secondaryCategoryCandidates": secondary_candidates,
    "suggestedNewHints": suggested_hints,
    "suggestedGoldenTests": [],
    "observedTopics": [],
    "decision": decision,
    "warnings": [],
  }


def analyze_segments_file(segments_json_path: Path, output_path: Path) -> dict[str, object]:
  payload = json.loads(segments_json_path.read_text(encoding="utf-8"))
  if not isinstance(payload, dict):
    raise ValueError("segments json 必须是对象")
  result = analyze_transcript_payload(payload)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  return result

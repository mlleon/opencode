#!/usr/bin/env python3
import json
from pathlib import Path

try:
  from llm_client import call_openai_compatible, extract_json_object, get_model_config, load_llm_config
  from schema import validate_assist_payload
  from taxonomy import load_taxonomy
except ImportError:
  from .llm_client import call_openai_compatible, extract_json_object, get_model_config, load_llm_config
  from .schema import validate_assist_payload
  from .taxonomy import load_taxonomy


def build_assist_prompts(segments_payload: dict[str, object], classification_payload: dict[str, object]) -> tuple[str, str]:
  taxonomy = load_taxonomy()
  system_prompt = (
    "你是多领域 transcript 结构化助手。"
    "你只能基于给定原文输出 JSON 候选，不能编造事实、不能写 Markdown、不能扩写成文案。"
    "每个判断必须有 evidence，evidence.text 必须逐字来自原文。"
    "东方文化与生活美学是用户重点方向，相关内容要优先识别，但不能无证据拔高。"
  )
  user_payload = {
    "task": "为转录内容生成通用 harness JSON。只返回 JSON 对象。",
    "schema": {
      "titleCandidate": "标题候选",
      "primaryCategory": "culture_life_aesthetics",
      "secondaryCategories": ["poetry", "su_dongpo"],
      "contentType": "commentary",
      "confidence": 0.8,
      "topics": [{"name": "主题", "type": "类型", "evidence": [{"text": "原文片段", "start": 0.0, "end": 1.0, "blockId": "b001"}]}],
      "keyPoints": [{"point": "关键观点", "evidence": [{"text": "原文片段", "start": 0.0, "end": 1.0, "blockId": "b001"}]}],
      "concepts": [],
      "quotes": [],
      "actionableInsights": [],
      "openQuestions": [],
      "warnings": [],
      "reviewRequired": True,
    },
    "creatorProfile": taxonomy.creatorProfile,
    "primaryCategories": {
      category_id: {
        "name": category.name,
        "description": category.description,
        "secondaryHints": category.secondaryHints or [],
      }
      for category_id, category in taxonomy.primaryCategories.items()
    },
    "classification": classification_payload,
    "segments": segments_payload,
  }
  return system_prompt, json.dumps(user_payload, ensure_ascii=False)


def run_assist(
  segments_json_path: Path,
  classification_json_path: Path,
  output_path: Path,
  model_name: str = "assisted",
) -> dict[str, object]:
  segments_payload = json.loads(segments_json_path.read_text(encoding="utf-8"))
  classification_payload = json.loads(classification_json_path.read_text(encoding="utf-8"))
  if not isinstance(segments_payload, dict) or not isinstance(classification_payload, dict):
    raise ValueError("assist 输入 JSON 必须是对象")
  config = get_model_config(load_llm_config(), model_name)
  system_prompt, user_prompt = build_assist_prompts(segments_payload, classification_payload)
  content = call_openai_compatible(config, system_prompt, user_prompt)
  payload = extract_json_object(content)
  source_text = "\n".join(
    str(block.get("text", ""))
    for block in segments_payload.get("blocks", [])
    if isinstance(block, dict)
  )
  taxonomy = load_taxonomy()
  valid_block_ids = {
    str(block.get("blockId", ""))
    for block in segments_payload.get("blocks", [])
    if isinstance(block, dict)
  }
  validate_assist_payload(payload, set(taxonomy.domains.keys()), source_text, valid_block_ids)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
  return payload


def write_deterministic_assist_placeholder(output_path: Path, reason: str) -> None:
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
    json.dumps({
      "titleCandidate": "",
      "primaryCategory": "generic",
      "secondaryCategories": [],
      "contentType": "unknown",
      "confidence": 0.0,
      "topics": [],
      "keyPoints": [],
      "concepts": [],
      "quotes": [],
      "actionableInsights": [],
      "openQuestions": [],
      "warnings": [reason],
      "reviewRequired": True,
      "skipped": True,
      "reason": reason,
    }, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )

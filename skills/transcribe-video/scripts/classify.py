#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

try:
  from taxonomy import Taxonomy, load_taxonomy
except ImportError:
  from .taxonomy import Taxonomy, load_taxonomy


HINT_KEYWORDS: dict[str, list[str]] = {
  "poetry": ["诗", "词", "诗词", "题西林壁"],
  "su_dongpo": ["苏轼", "苏东坡"],
  "tea_culture": ["茶", "茶席", "茶器", "茶汤", "泡茶"],
  "object_aesthetics": ["器物", "汝瓷", "杯盏", "釉色", "温润", "瓷器"],
  "ru_porcelain": ["汝瓷", "开片", "釉色"],
  "calligraphy": ["毛笔", "书法", "临帖", "书写"],
  "tea_room": ["茶室", "空间", "留白", "光线"],
  "green_plant_space": ["绿植", "植物", "枝叶", "生命力"],
  "life_aesthetics": ["美学", "审美", "松弛", "优雅", "呼吸感"],
  "spiritual_space": ["精神空间", "心境", "呼吸感"],
  "ai_agents": ["Agent", "智能体"],
  "agent_skill_design": ["Skill", "技能", "触发器", "description"],
  "prompt_engineering": ["prompt", "提示词"],
  "rag": ["RAG", "检索增强"],
  "software_engineering": ["软件工程", "代码", "API"],
  "llm_evaluation": ["eval", "评测", "模型评估"],
}


def classify_text(text: str, taxonomy: Taxonomy) -> dict[str, object]:
  scores: Counter[str] = Counter()
  matched_terms: dict[str, list[str]] = {}
  matched_hints: dict[str, list[str]] = {}
  for domain_id, domain in taxonomy.domains.items():
    if domain_id == "generic":
      continue
    for keyword in domain.keywords:
      if keyword and keyword in text:
        scores[domain_id] += text.count(keyword)
        matched_terms.setdefault(domain_id, []).append(keyword)
    for hint in domain.secondaryHints or []:
      hint_text = hint.replace("_", " ")
      hint_words = [part for part in hint.split("_") if part]
      hint_keywords = HINT_KEYWORDS.get(hint, [])
      keyword_hit = any(keyword and keyword in text for keyword in domain.keywords)
      explicit_hit = hint in text or hint_text in text
      partial_hit = keyword_hit and any(part in text for part in hint_words)
      hint_keyword_hit = any(keyword and keyword in text for keyword in hint_keywords)
      if hint and (explicit_hit or partial_hit or hint_keyword_hit):
        scores[domain_id] += 1
        matched_terms.setdefault(domain_id, []).append(hint)
        matched_hints.setdefault(domain_id, []).append(hint)

  ranked = [domain_id for domain_id, _count in scores.most_common()]
  primary = ranked[0] if ranked else "generic"
  secondary = matched_hints.get(primary, [])[:6]
  if not secondary:
    secondary = ranked[1:4]
  confidence = "low"
  if scores[primary] >= 4:
    confidence = "high"
  elif scores[primary] >= 2:
    confidence = "medium"

  return {
    "primaryCategory": primary,
    "secondaryCategories": secondary,
    "primaryDomain": primary,
    "secondaryDomains": secondary,
    "confidence": confidence,
    "matchedTerms": matched_terms,
    "taxonomyVersion": taxonomy.version,
    "reviewStatus": "pending",
  }


def classify_blocks_payload(blocks_payload: dict[str, object], taxonomy: Taxonomy | None = None) -> dict[str, object]:
  actual_taxonomy = taxonomy or load_taxonomy()
  blocks = blocks_payload.get("blocks")
  if not isinstance(blocks, list):
    raise ValueError("segments json 缺少 blocks")
  text = "\n".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
  result = classify_text(text, actual_taxonomy)
  result["blocks"] = []
  for block in blocks:
    if not isinstance(block, dict):
      continue
    block_result = classify_text(str(block.get("text", "")), actual_taxonomy)
    result["blocks"].append({
      "blockId": block.get("blockId", ""),
      "primaryDomain": block_result["primaryDomain"],
      "secondaryDomains": block_result["secondaryDomains"],
      "confidence": block_result["confidence"],
    })
  return result


def classify_segments_file(segments_json_path: Path, output_path: Path) -> dict[str, object]:
  data = json.loads(segments_json_path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError("segments json 必须是对象")
  result = classify_blocks_payload(data)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
  return result

import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def load_module(name: str):
  if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
  path = SCRIPTS_DIR / f"{name}.py"
  spec = importlib.util.spec_from_file_location(name, path)
  assert spec is not None
  assert spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class PipelineTests(TestCase):
  def test_taxonomy_contains_object_aesthetics(self):
    module = load_module("taxonomy")
    taxonomy = module.load_taxonomy()

    self.assertIn("culture_life_aesthetics", taxonomy.primaryCategories)
    category = taxonomy.primaryCategories["culture_life_aesthetics"]
    self.assertIn("object_aesthetics", category.secondaryHints)
    self.assertIn("ru_porcelain", category.secondaryHints)
    self.assertEqual(taxonomy.creatorProfile["focus"], "中国传统文化与生活美学结合")

  def test_classify_matches_culture_domains(self):
    taxonomy_module = load_module("taxonomy")
    classify_module = load_module("classify")
    taxonomy = taxonomy_module.load_taxonomy()

    result = classify_module.classify_text("汝瓷杯盏放在茶席里，釉色温润，让空间更松弛。", taxonomy)

    self.assertEqual(result["primaryCategory"], "culture_life_aesthetics")
    self.assertIn("object_aesthetics", result["secondaryCategories"])
    self.assertIn("tea_culture", result["secondaryCategories"])

  def test_segment_builds_stable_block_ids(self):
    module = load_module("segment")

    result = module.build_blocks({
      "source": "sample.mp4",
      "language": "zh-CN",
      "segments": [
        {"id": "s0001", "start": 0.0, "end": 10.0, "text": "第一段"},
        {"id": "s0002", "start": 10.0, "end": 20.0, "text": "第二段"},
      ],
    })

    self.assertEqual(result["blocks"][0]["blockId"], "b001")
    self.assertEqual(result["blocks"][0]["segmentIds"], ["s0001", "s0002"])

  def test_structure_pipeline_generates_memory_source_markdown(self):
    normalize_module = load_module("normalize")
    segment_module = load_module("segment")
    classify_module = load_module("classify")
    structure_module = load_module("structure")

    with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
      tmp_dir = Path(tmp_dir_name)
      transcript_json = tmp_dir / "transcript.json"
      normalized_json = tmp_dir / "normalized.json"
      normalized_md = tmp_dir / "normalized.md"
      segments_json = tmp_dir / "segments.json"
      classification_json = tmp_dir / "classification.json"
      output_md = tmp_dir / "document.md"

      transcript_json.write_text(json.dumps({
        "source": "sample.mp4",
        "language": "zh-CN",
        "source_type": "subtitles:srt",
        "segments": [
          {"start": 0.0, "end": 8.0, "text": "汝瓷杯盏放在茶席里，釉色温润。"},
          {"start": 8.0, "end": 18.0, "text": "这样的器物让空间有松弛的呼吸感。"},
        ],
      }, ensure_ascii=False), encoding="utf-8")

      normalized = normalize_module.normalize_transcript_file(transcript_json, normalized_json, normalized_md)
      blocks = segment_module.build_blocks(normalized)
      segment_module.write_blocks(blocks, segments_json)
      classification = classify_module.classify_blocks_payload(blocks)
      classification_json.write_text(json.dumps(classification, ensure_ascii=False), encoding="utf-8")
      structure_module.structure_pipeline_outputs(normalized_json, segments_json, classification_json, output_md)
      content = output_md.read_text(encoding="utf-8")

    self.assertIn("raw/03-transcripts", content)
    self.assertIn("primary_category: culture_life_aesthetics", content)
    self.assertIn("## 主题结构", content)
    self.assertIn("## 关键观点", content)
    self.assertIn("## 原文转录", content)

  def test_assist_schema_rejects_evidence_not_in_source(self):
    module = load_module("schema")

    with self.assertRaises(ValueError):
      module.validate_assist_payload({
        "titleCandidate": "标题",
        "primaryCategory": "culture_life_aesthetics",
        "secondaryCategories": ["object_aesthetics"],
        "contentType": "commentary",
        "confidence": 0.8,
        "topics": [{"name": "主题", "type": "culture", "evidence": [{"text": "不存在的原文", "start": 0.0, "end": 1.0, "blockId": "b001"}]}],
        "keyPoints": [],
        "concepts": [],
        "quotes": [],
        "actionableInsights": [],
        "openQuestions": [],
        "warnings": [],
        "reviewRequired": True,
      }, {"culture_life_aesthetics"}, "真实原文", {"b001"})

  def test_analyze_stages_new_hint_candidate_with_evidence(self):
    module = load_module("analyze")

    result = module.analyze_transcript_payload({
      "blocks": [
        {
          "blockId": "b001",
          "start": 0.0,
          "end": 12.0,
          "text": "这个 Agent Skill 的核心是 context engineering，要控制上下文税和触发边界。",
        }
      ]
    })

    self.assertEqual(result["decision"], "stage_and_pause")
    suggested_names = [item["name"] for item in result["suggestedNewHints"]]
    self.assertIn("context_engineering", suggested_names)

  def test_schema_accepts_open_secondary_category_with_evidence(self):
    module = load_module("schema")

    module.validate_assist_payload({
      "titleCandidate": "Agent Skill 设计",
      "primaryCategory": "ai_technology",
      "secondaryCategories": ["context_engineering"],
      "contentType": "tutorial",
      "confidence": 0.9,
      "topics": [{"name": "上下文工程", "type": "methodology", "evidence": [{"text": "context engineering", "start": 0.0, "end": 1.0, "blockId": "b001"}]}],
      "keyPoints": [{"point": "要控制上下文税", "evidence": [{"text": "上下文税", "start": 1.0, "end": 2.0, "blockId": "b001"}]}],
      "concepts": [],
      "quotes": [],
      "actionableInsights": [],
      "openQuestions": [],
      "warnings": [],
      "reviewRequired": True,
    }, {"ai_technology"}, "context engineering\n上下文税", {"b001"})

  def test_validate_rejects_process_files_in_raw(self):
    module = load_module("validate")

    with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
      root = Path(tmp_dir_name)
      (root / "AGENTS.md").write_text("rules", encoding="utf-8")
      memory = root / "memory-source"
      (memory / "raw" / "03-transcripts").mkdir(parents=True)
      (memory / "assets").mkdir(parents=True)
      (memory / "AGENTS.md").write_text("rules", encoding="utf-8")
      (memory / "raw" / "03-transcripts" / "bad.json").write_text("{}", encoding="utf-8")

      errors = module.validate_transcript_outputs(root)

    self.assertTrue(any("只能包含 Markdown" in error for error in errors))

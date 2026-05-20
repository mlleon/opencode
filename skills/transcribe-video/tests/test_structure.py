import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "structure.py"


def load_structure_module():
  spec = importlib.util.spec_from_file_location("structure", SCRIPT_PATH)
  assert spec is not None
  assert spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class StructureTests(TestCase):
  def test_structure_transcript_json_generates_markdown_sections(self):
    module = load_structure_module()

    with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
      tmp_dir = Path(tmp_dir_name)
      transcript_path = tmp_dir / "sample.json"
      output_md = tmp_dir / "sample.md"

      payload = {
        "source": "sample.mp4",
        "language": "zh-CN",
        "segments": [
          {"start": 0.0, "end": 10.0, "text": "今天我们讨论视频转录和笔记整理"},
          {"start": 8.0, "end": 18.0, "text": "重点是不要编造，引用要可追溯"},
          {"start": 16.0, "end": 26.0, "text": "最后输出到 Obsidian 的 Markdown"},
        ],
      }
      transcript_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

      module.structure_transcript_json(transcript_path, output_md)
      content = output_md.read_text(encoding="utf-8")

    self.assertIn("# Summary", content)
    self.assertIn("# Topics", content)
    self.assertIn("# Timeline", content)
    self.assertIn("# Key Quotes", content)
    self.assertIn("# Action Items", content)
    self.assertIn("# Tags", content)
    self.assertIn("# Obsidian Links", content)

    # 关键引用必须来自原始 segment 文本
    self.assertIn("今天我们讨论视频转录和笔记整理", content)

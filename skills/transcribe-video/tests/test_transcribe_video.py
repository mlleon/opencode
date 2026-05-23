import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def load_module(name: str):
  package_name = f"scripts.{name}"
  if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
  path = SCRIPTS_DIR / f"{name}.py"
  spec = importlib.util.spec_from_file_location(package_name, path)
  assert spec is not None
  assert spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def make_project(root: Path) -> Path:
  project_root = root / "project"
  (project_root / "memory-source" / "raw" / "03-transcripts").mkdir(parents=True)
  (project_root / "memory-source" / "assets").mkdir(parents=True)
  (project_root / "AGENTS.md").write_text("rules", encoding="utf-8")
  (project_root / "memory-source" / "AGENTS.md").write_text("rules", encoding="utf-8")
  return project_root


class TranscribeVideoCliTests(TestCase):
  def test_analyze_command_writes_analysis_json(self):
    module = load_module("transcribe_video")

    with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
      tmp_dir = Path(tmp_dir_name)
      project_root = make_project(tmp_dir)
      segments_json = tmp_dir / "segments.json"
      output_json = tmp_dir / "analysis.json"
      segments_json.write_text(json.dumps({
        "blocks": [
          {
            "blockId": "b001",
            "start": 0.0,
            "end": 10.0,
            "text": "这个 Agent Skill 的核心是 context engineering，要控制上下文税。",
          }
        ]
      }, ensure_ascii=False), encoding="utf-8")

      with mock.patch.object(sys, "argv", [
        "transcribe_video.py",
        "analyze",
        "--project-root",
        str(project_root),
        "--input-transcript",
        str(segments_json),
        "--output",
        str(output_json),
      ]):
        module.main()

      result = json.loads(output_json.read_text(encoding="utf-8"))

    self.assertEqual(result["decision"], "stage_and_pause")
    self.assertTrue(any(item["name"] == "context_engineering" for item in result["suggestedNewHints"]))

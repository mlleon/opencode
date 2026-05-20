import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run.py"


def load_run_module():
  spec = importlib.util.spec_from_file_location("run", SCRIPT_PATH)
  assert spec is not None
  assert spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class RunTests(TestCase):
  def test_run_glues_transcribe_and_structure(self):
    module = load_run_module()

    calls = {
      "transcribe": 0,
      "structure": 0,
    }

    def fake_transcribe_to_files(video_path: Path, language: str):
      calls["transcribe"] += 1
      self.assertEqual(language, "zh-CN")
      txt_path = video_path.with_suffix(".txt")
      json_path = video_path.with_suffix(".json")
      md_path = video_path.with_suffix(".md")

      # 模拟真实 transcribe_to_files 会落盘 json
      json_path.write_text("{\"segments\": [{\"start\": 0, \"end\": 1, \"text\": \"hi\"}]}", encoding="utf-8")

      return {
        "txt": txt_path,
        "json": json_path,
        "md": md_path,
        "lines": 1,
      }

    def fake_structure_transcript_json(transcript_json_path: Path, output_md_path: Path):
      calls["structure"] += 1
      self.assertTrue(str(transcript_json_path).endswith(".json"))
      self.assertTrue(str(output_md_path).endswith(".md"))

    fake_transcribe_module = ModuleType("transcribe")
    setattr(fake_transcribe_module, "transcribe_to_files", fake_transcribe_to_files)

    fake_structure_module = ModuleType("structure")
    setattr(fake_structure_module, "structure_transcript_json", fake_structure_transcript_json)

    old_argv = list(sys.argv)
    try:
      with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        video_path = tmp_dir / "sample.mp4"
        video_path.write_bytes(b"video")

        sys.modules["transcribe"] = fake_transcribe_module
        sys.modules["structure"] = fake_structure_module
        sys.argv = ["run.py", str(video_path), "zh-CN"]
        module.main()
    finally:
      sys.argv = old_argv
      sys.modules.pop("transcribe", None)
      sys.modules.pop("structure", None)

    self.assertEqual(calls["transcribe"], 1)
    self.assertEqual(calls["structure"], 1)

  def test_run_retries_transcribe_if_json_missing(self):
    module = load_run_module()

    calls = {
      "transcribe": 0,
      "structure": 0,
    }

    def fake_structure_transcript_json(transcript_json_path: Path, output_md_path: Path):
      calls["structure"] += 1
      self.assertTrue(transcript_json_path.exists())
      self.assertTrue(str(transcript_json_path).endswith(".json"))
      self.assertTrue(str(output_md_path).endswith(".md"))

    fake_structure_module = ModuleType("structure")
    setattr(fake_structure_module, "structure_transcript_json", fake_structure_transcript_json)

    old_argv = list(sys.argv)
    try:
      with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        video_path = tmp_dir / "sample.mp4"
        video_path.write_bytes(b"video")

        transcript_json = tmp_dir / "sample.json"

        def fake_transcribe_to_files(video_path_arg: Path, language: str):
          calls["transcribe"] += 1
          self.assertEqual(language, "zh-CN")

          # 第一次调用不生成 json，模拟“转录没落盘/被中断”。第二次再生成。
          if calls["transcribe"] >= 2:
            transcript_json.write_text("{\"segments\": [{\"start\": 0, \"end\": 1, \"text\": \"hi\"}]}", encoding="utf-8")

          return {
            "txt": tmp_dir / "sample.txt",
            "json": transcript_json,
            "md": tmp_dir / "sample.md",
            "lines": 1,
          }

        fake_transcribe_module = ModuleType("transcribe")
        setattr(fake_transcribe_module, "transcribe_to_files", fake_transcribe_to_files)

        sys.modules["transcribe"] = fake_transcribe_module
        sys.modules["structure"] = fake_structure_module

        # 让等待逻辑在单测中瞬间完成
        setattr(module, "_wait_for_file", lambda _path, timeout_sec: False)

        sys.argv = ["run.py", str(video_path), "zh-CN"]
        module.main()
    finally:
      sys.argv = old_argv
      sys.modules.pop("transcribe", None)
      sys.modules.pop("structure", None)

    self.assertEqual(calls["transcribe"], 2)
    self.assertEqual(calls["structure"], 1)

  def test_run_raises_helpful_error_if_partial_exists_but_final_json_missing(self):
    module = load_run_module()

    def fake_structure_transcript_json(_transcript_json_path: Path, _output_md_path: Path):
      raise AssertionError("structure_transcript_json should not be called when final json is missing")

    fake_structure_module = ModuleType("structure")
    setattr(fake_structure_module, "structure_transcript_json", fake_structure_transcript_json)

    def fake_transcribe_to_files(video_path: Path, language: str):
      self.assertEqual(language, "zh-CN")
      out_dir = video_path.parent / video_path.stem
      out_dir.mkdir(exist_ok=True)
      final_json = out_dir / f"{video_path.stem}.json"
      # 模拟：最终 json 没写出来，但 partial 存在（常见于超时中断）
      partial_json = out_dir / f"{video_path.stem}.json.partial"
      partial_json.write_text("{}", encoding="utf-8")
      return {
        "txt": out_dir / f"{video_path.stem}.txt",
        "json": final_json,
        "md": out_dir / f"{video_path.stem}.md",
        "lines": 0,
      }

    fake_transcribe_module = ModuleType("transcribe")
    setattr(fake_transcribe_module, "transcribe_to_files", fake_transcribe_to_files)

    old_argv = list(sys.argv)
    try:
      with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        video_path = tmp_dir / "sample.mp4"
        video_path.write_bytes(b"video")

        sys.modules["transcribe"] = fake_transcribe_module
        sys.modules["structure"] = fake_structure_module
        setattr(module, "_wait_for_file", lambda _path, timeout_sec: False)

        sys.argv = ["run.py", str(video_path), "zh-CN"]
        with self.assertRaises(RuntimeError) as ctx:
          module.main()

        self.assertIn("partial output exists", str(ctx.exception))
    finally:
      sys.argv = old_argv
      sys.modules.pop("transcribe", None)
      sys.modules.pop("structure", None)

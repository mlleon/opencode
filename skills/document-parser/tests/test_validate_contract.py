import os
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent


def _makeTmpProject(tmpDir: str) -> Path:
  projectRoot = Path(tmpDir) / "project"
  projectRoot.mkdir(parents=True, exist_ok=True)
  (projectRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
  vaultRoot = projectRoot / "memory-source"
  (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
  return projectRoot


def _runCli(*args: str) -> subprocess.CompletedProcess:
  env = os.environ.copy()
  env["PYTHONPATH"] = str(_SKILL_ROOT)
  return subprocess.run(
    [sys.executable, "-m", "scripts.document_parser", *args],
    cwd=str(_SKILL_ROOT),
    env=env,
    text=True,
    capture_output=True,
  )


class ValidateContractNegativeCasesTests(unittest.TestCase):
  def test_validate_requires_project_level_agent_instruction_v003(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      vaultRoot = projectRoot / "memory-source"
      (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

      result = _runCli("validate", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 3)
      self.assertEqual(result.stdout, "")
      self.assertIn("ERROR_CODE:V003", result.stderr)
      self.assertIn("projectRoot 下缺少 CLAUDE.md 或 AGENTS.md", result.stderr)

  def test_validate_requires_memory_source_agent_instruction_v003(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      projectRoot.mkdir(parents=True, exist_ok=True)
      (projectRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
      vaultRoot = projectRoot / "memory-source"
      (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)

      result = _runCli("validate", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 3)
      self.assertEqual(result.stdout, "")
      self.assertIn("ERROR_CODE:V003", result.stderr)
      self.assertIn("memory-source 下缺少 CLAUDE.md 或 AGENTS.md", result.stderr)

  def test_validate_catches_forbidden_binaries_v004(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      badPath = vaultRoot / "raw" / "04-books" / "NEG__h000000000000" / "bad.png"
      badPath.parent.mkdir(parents=True, exist_ok=True)
      badPath.write_bytes(b"\x89PNG\r\n\x1a\n")

      result = _runCli("validate", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 4, msg=f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}\n")
      self.assertEqual(result.stdout, "", msg="validate stdout 必须为空")
      self.assertIn("ERROR_CODE:V004", result.stderr)
      self.assertIn(str(badPath), result.stderr)

  def test_validate_rejects_markdown_image_v005(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      mdPath = vaultRoot / "raw" / "04-books" / "DOC__h000000000000" / "ch-01.md"
      mdPath.parent.mkdir(parents=True, exist_ok=True)
      mdPath.write_text("# t\n\n![](images/x.jpg)\n", encoding="utf-8")

      result = _runCli("validate", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 5, msg=f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}\n")
      self.assertEqual(result.stdout, "", msg="validate stdout 必须为空")
      self.assertIn("ERROR_CODE:V005", result.stderr)
      self.assertIn("![](images/x.jpg)", result.stderr)


if __name__ == "__main__":
  unittest.main()

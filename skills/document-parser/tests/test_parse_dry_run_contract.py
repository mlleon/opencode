import json
import os
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent


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


def _assertOneLineJson(test: unittest.TestCase, stdout: str, *, context: str) -> dict:
  lines = stdout.splitlines()
  test.assertEqual(
    len(lines),
    1,
    msg=(
      f"{context} stdout 必须只输出一行 JSON（末尾允许 1 个换行）。\n"
      f"stdout=\n{stdout}\n"
    ),
  )
  try:
    data = json.loads(lines[0])
  except Exception as e:
    test.fail(f"{context} stdout 必须是合法 JSON：{e}\nstdout=\n{stdout}\n")
  test.assertIsInstance(data, dict, msg=f"{context} stdout JSON 顶层必须是 object")
  return data


class ParseDryRunContractTests(unittest.TestCase):
  def test_dry_run_success_stdout_schema(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      (projectRoot / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
      (projectRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
      vaultRoot = projectRoot / "memory-source"
      (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

      result = _runCli("dry-run", "--project-root", str(projectRoot))

      self.assertEqual(
        result.returncode,
        0,
        msg=f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}\n",
      )
      self.assertEqual(result.stderr, "", msg="dry-run 成功时 stderr 必须为空")

      data = _assertOneLineJson(self, result.stdout, context="dry-run")

      required = [
        "projectRoot",
        "vaultRoot",
        "stagingRoot",
        "rawRoot",
        "assetsRoot",
        "manifestRoot",
        "policy",
      ]
      for key in required:
        self.assertIn(key, data, msg=f"dry-run stdout JSON 必须包含字段：{key}")

      self.assertEqual(Path(data["projectRoot"]).resolve(), projectRoot.resolve())
      self.assertEqual(Path(data["vaultRoot"]).resolve(), vaultRoot.resolve())
      self.assertEqual(Path(data["stagingRoot"]).resolve(), (projectRoot / ".cache" / "document-parser").resolve())
      self.assertEqual(Path(data["rawRoot"]).resolve(), (vaultRoot / "raw").resolve())
      self.assertEqual(Path(data["assetsRoot"]).resolve(), (vaultRoot / "assets").resolve())
      self.assertEqual(Path(data["manifestRoot"]).resolve(), (vaultRoot / "raw" / "05-images").resolve())

      policy = data["policy"]
      self.assertIsInstance(policy, dict)
      self.assertEqual(
        policy,
        {
          "projectRootRequired": True,
          "stagingOutsideVault": True,
          "rawNoBinaries": True,
          "imageLinkStyle": "obsidian-embed",
        },
        msg="dry-run policy 字段必须严格一致（字段名不可更改）",
      )

  def test_dry_run_missing_project_root_exit_2_and_error_prefix(self):
    result = _runCli("dry-run")

    self.assertEqual(result.returncode, 2)
    self.assertEqual(result.stdout, "", msg="dry-run 参数错误时 stdout 必须为空")
    self.assertTrue(
      result.stderr.startswith("ERROR:"),
      msg=f"dry-run 参数错误时 stderr 必须以 ERROR: 开头\nstderr=\n{result.stderr}\n",
    )

  def test_dry_run_missing_required_dirs_exit_3(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      projectRoot.mkdir(parents=True, exist_ok=True)
      (projectRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
      # 仅创建 memory-source/ 但不创建 raw/assets/，触发路径校验失败。
      vaultRoot = projectRoot / "memory-source"
      vaultRoot.mkdir(parents=True, exist_ok=True)
      (vaultRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")

      result = _runCli("dry-run", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 3)
      self.assertEqual(result.stdout, "", msg="dry-run 路径校验失败时 stdout 必须为空")
      self.assertTrue(
        result.stderr.startswith("ERROR:"),
        msg=f"dry-run 路径校验失败时 stderr 必须以 ERROR: 开头\nstderr=\n{result.stderr}\n",
      )

  def test_dry_run_requires_project_level_agent_instruction(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      vaultRoot = projectRoot / "memory-source"
      (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

      result = _runCli("dry-run", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 3)
      self.assertEqual(result.stdout, "")
      self.assertIn("projectRoot 下缺少 CLAUDE.md 或 AGENTS.md", result.stderr)

  def test_dry_run_requires_memory_source_agent_instruction(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      projectRoot.mkdir(parents=True, exist_ok=True)
      (projectRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
      vaultRoot = projectRoot / "memory-source"
      (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
      (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)

      result = _runCli("dry-run", "--project-root", str(projectRoot))

      self.assertEqual(result.returncode, 3)
      self.assertEqual(result.stdout, "")
      self.assertIn("memory-source 下缺少 CLAUDE.md 或 AGENTS.md", result.stderr)

  def test_parse_missing_project_root_hard_fail(self):
    # 只验证 project-root 必填（避免触发 orchestrator 网络请求）。
    result = _runCli("parse", "--input", "dummy.pdf")
    self.assertEqual(result.returncode, 2)
    self.assertEqual(result.stdout, "")
    self.assertTrue(result.stderr.startswith("ERROR:"), msg=f"stderr=\n{result.stderr}\n")


if __name__ == "__main__":
  unittest.main()

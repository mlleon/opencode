import json
import os
import subprocess
import tempfile
import unittest
import sys
from importlib import import_module
from pathlib import Path
from typing import Callable, Protocol, TypedDict, cast

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
if str(_SKILL_ROOT) not in sys.path:
  sys.path.insert(0, str(_SKILL_ROOT))



class _DryRunPolicy(TypedDict):
  projectRootRequired: bool
  stagingOutsideVault: bool
  rawNoBinaries: bool
  imageLinkStyle: str


class _DryRunData(TypedDict):
  projectRoot: str
  vaultRoot: str
  stagingRoot: str
  rawRoot: str
  assetsRoot: str
  manifestRoot: str
  policy: _DryRunPolicy


class _PageRangePreflightResult(Protocol):
  requestedPageRange: str | None
  normalizedPageRange: str | None
  intervals: tuple[tuple[int, int], ...]
  pdfPageCount: int | None
  rangeSource: str


class _ParseOptions(Protocol):
  pageRange: str | None
  modelVersion: str | None
  language: str | None
  isOcr: bool | None
  enableTable: bool | None
  enableFormula: bool | None
  pdfPageCount: int | None
  parseOnly: bool
  disableFallback: bool


class _ParseManyCall(TypedDict):
  sources: list[str]
  outputDir: Path
  options: _ParseOptions | None


class _OrchestratorModule(Protocol):
  ParseOptions: type[_ParseOptions]

  def parseMany(
    self,
    *,
    sources: list[str],
    outputDir: Path,
    options: _ParseOptions | None = None,
  ) -> list[object]: ...


class _DocumentParserModule(Protocol):
  _orchestrator: _OrchestratorModule
  _readPdfPageCount: Callable[[Path], int]

  def _parsePageRange(self, pageRangeRaw: str) -> tuple[tuple[int, int], ...]: ...

  def _formatPageRange(self, intervals: tuple[tuple[int, int], ...]) -> str: ...

  def _runParse(self, argv: list[str]) -> int: ...

  def _runPostprocess(self, argv: list[str]) -> int: ...

  def _preflightPageRange(
    self,
    *,
    inputValue: str,
    pageRangeRaw: str | None,
  ) -> _PageRangePreflightResult: ...


document_parser = cast(_DocumentParserModule, cast(object, import_module("scripts.document_parser")))


class _FakePaths:
  def __init__(self, *, normalizedMarkdownPath: Path):
    self.normalizedMarkdownPath = normalizedMarkdownPath


class _FakeResult:
  def __init__(self, *, normalizedMarkdownPath: Path):
    self.paths = _FakePaths(normalizedMarkdownPath=normalizedMarkdownPath)


def _runCli(*args: str) -> subprocess.CompletedProcess[str]:
  env = os.environ.copy()
  env["PYTHONPATH"] = str(_SKILL_ROOT)
  return subprocess.run(
    [sys.executable, "-m", "scripts.document_parser", *args],
    cwd=str(_SKILL_ROOT),
    env=env,
    text=True,
    capture_output=True,
  )


def _assertOneLineJson(test: unittest.TestCase, stdout: str, *, context: str) -> _DryRunData:
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
  return cast(_DryRunData, data)


def _writeTinyPdf(path: Path, *, pageCount: int) -> None:
  from pypdf import PdfWriter

  writer = PdfWriter()
  for _ in range(pageCount):
    writer.add_blank_page(width=72, height=72)
  with path.open("wb") as f:
    writer.write(f)


def _makeProjectRoot(tmp: str) -> Path:
  projectRoot = Path(tmp) / "project"
  projectRoot.mkdir(parents=True, exist_ok=True)
  (projectRoot / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
  return projectRoot


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

  def test_parse_help_lists_bounded_parse_only_and_no_fallback_options(self):
    result = _runCli("parse", "--help")

    self.assertEqual(result.returncode, 0, msg=f"stderr=\n{result.stderr}\n")
    self.assertEqual(result.stderr, "")
    for flag in [
      "--page-range",
      "--model-version",
      "--language",
      "--is-ocr",
      "--enable-table",
      "--enable-formula",
      "--parse-only",
      "--no-postprocess",
      "--no-fallback",
    ]:
      self.assertIn(flag, result.stdout)
    self.assertIn("fail-closed", result.stdout)

  def test_parse_threads_bounded_options_to_orchestrator(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      calls: list[_ParseManyCall] = []

      def fakeParseMany(
        *,
        sources: list[str],
        outputDir: Path,
        options: _ParseOptions | None = None,
      ) -> list[_FakeResult]:
        calls.append({"sources": sources, "outputDir": outputDir, "options": options})
        return [
          _FakeResult(
            normalizedMarkdownPath=outputDir
            / "document_parser_output"
            / "sample"
            / "normalized"
            / "document.md"
          )
        ]

      originalParseMany = document_parser._orchestrator.parseMany
      setattr(document_parser._orchestrator, "parseMany", fakeParseMany)
      try:
        code = document_parser._runParse(
          [
            "--project-root",
            str(projectRoot),
            "--input",
            "https://example.com/sample.pdf",
            "--page-range",
            "1-10",
            "--model-version",
            "vlm",
            "--language",
            "ch",
            "--is-ocr",
            "false",
            "--enable-table",
            "false",
            "--enable-formula",
            "false",
            "--parse-only",
          ]
        )
      finally:
        setattr(document_parser._orchestrator, "parseMany", originalParseMany)

    self.assertEqual(code, 0)
    self.assertEqual(len(calls), 1)
    call = calls[0]
    self.assertEqual(call["sources"], ["https://example.com/sample.pdf"])
    self.assertEqual(call["outputDir"], projectRoot / ".cache" / "document-parser")
    options = call["options"]
    if options is None:
      self.fail("parse 必须把 typed options object 传给 orchestrator")
    self.assertIsInstance(options, document_parser._orchestrator.ParseOptions)
    self.assertEqual(options.pageRange, "1-10")
    self.assertEqual(options.modelVersion, "vlm")
    self.assertEqual(options.language, "ch")
    self.assertIs(options.isOcr, False)
    self.assertIs(options.enableTable, False)
    self.assertIs(options.enableFormula, False)
    self.assertTrue(options.parseOnly)
    self.assertFalse(options.disableFallback)

  def test_parse_threads_no_fallback_to_orchestrator_options(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      calls: list[_ParseManyCall] = []

      def fakeParseMany(
        *,
        sources: list[str],
        outputDir: Path,
        options: _ParseOptions | None = None,
      ) -> list[_FakeResult]:
        calls.append({"sources": sources, "outputDir": outputDir, "options": options})
        return [
          _FakeResult(
            normalizedMarkdownPath=outputDir
            / "document_parser_output"
            / "sample"
            / "normalized"
            / "document.md"
          )
        ]

      originalParseMany = document_parser._orchestrator.parseMany
      setattr(document_parser._orchestrator, "parseMany", fakeParseMany)
      try:
        code = document_parser._runParse(
          [
            "--project-root",
            str(projectRoot),
            "--input",
            "https://example.com/sample.pdf",
            "--no-fallback",
          ]
        )
      finally:
        setattr(document_parser._orchestrator, "parseMany", originalParseMany)

    self.assertEqual(code, 0)
    self.assertEqual(len(calls), 1)
    options = calls[0]["options"]
    if options is None:
      self.fail("parse 必须把 typed options object 传给 orchestrator")
    self.assertFalse(options.parseOnly)
    self.assertTrue(options.disableFallback)

  def test_parse_only_accepts_no_fallback_without_semantic_drift(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      vaultRoot = projectRoot / "memory-source"
      vaultRoot.mkdir(parents=True, exist_ok=True)
      beforeVaultPaths = sorted(p.relative_to(vaultRoot).as_posix() for p in vaultRoot.rglob("*"))
      calls: list[_ParseManyCall] = []

      def fakeParseMany(
        *,
        sources: list[str],
        outputDir: Path,
        options: _ParseOptions | None = None,
      ) -> list[_FakeResult]:
        calls.append({"sources": sources, "outputDir": outputDir, "options": options})
        return [
          _FakeResult(
            normalizedMarkdownPath=outputDir
            / "document_parser_output"
            / "sample"
            / "normalized"
            / "document.md"
          )
        ]

      def failPostprocess(argv: list[str]) -> int:
        self.fail(f"parse-only 不应调用 postprocess：{argv}")

      originalParseMany = document_parser._orchestrator.parseMany
      originalRunPostprocess = document_parser._runPostprocess
      setattr(document_parser._orchestrator, "parseMany", fakeParseMany)
      setattr(document_parser, "_runPostprocess", failPostprocess)
      try:
        code = document_parser._runParse(
          [
            "--project-root",
            str(projectRoot),
            "--input",
            "https://example.com/sample.pdf",
            "--parse-only",
            "--no-fallback",
          ]
        )
      finally:
        setattr(document_parser._orchestrator, "parseMany", originalParseMany)
        setattr(document_parser, "_runPostprocess", originalRunPostprocess)

      afterVaultPaths = sorted(p.relative_to(vaultRoot).as_posix() for p in vaultRoot.rglob("*"))

    self.assertEqual(code, 0)
    self.assertEqual(beforeVaultPaths, afterVaultPaths)
    self.assertEqual(len(calls), 1)
    options = calls[0]["options"]
    if options is None:
      self.fail("--parse-only --no-fallback 必须以 typed options object 进入 orchestrator")
    self.assertTrue(options.parseOnly)
    self.assertTrue(options.disableFallback)

  def test_no_postprocess_alias_is_parse_only_and_staging_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      vaultRoot = projectRoot / "memory-source"
      vaultRoot.mkdir(parents=True, exist_ok=True)
      beforeVaultPaths = sorted(p.relative_to(vaultRoot).as_posix() for p in vaultRoot.rglob("*"))
      calls: list[_ParseManyCall] = []

      def fakeParseMany(
        *,
        sources: list[str],
        outputDir: Path,
        options: _ParseOptions | None = None,
      ) -> list[_FakeResult]:
        calls.append({"sources": sources, "outputDir": outputDir, "options": options})
        return [
          _FakeResult(
            normalizedMarkdownPath=outputDir
            / "document_parser_output"
            / "sample"
            / "normalized"
            / "document.md"
          )
        ]

      def failPostprocess(argv: list[str]) -> int:
        self.fail(f"parse 不应调用 postprocess：{argv}")

      originalParseMany = document_parser._orchestrator.parseMany
      originalRunPostprocess = document_parser._runPostprocess
      setattr(document_parser._orchestrator, "parseMany", fakeParseMany)
      setattr(document_parser, "_runPostprocess", failPostprocess)
      try:
        code = document_parser._runParse(
          [
            "--project-root",
            str(projectRoot),
            "--input",
            "https://example.com/sample.pdf",
            "--no-postprocess",
          ]
        )
      finally:
        setattr(document_parser._orchestrator, "parseMany", originalParseMany)
        setattr(document_parser, "_runPostprocess", originalRunPostprocess)

      afterVaultPaths = sorted(p.relative_to(vaultRoot).as_posix() for p in vaultRoot.rglob("*"))

    self.assertEqual(code, 0)
    self.assertEqual(beforeVaultPaths, afterVaultPaths)
    self.assertEqual(len(calls), 1)
    options = calls[0]["options"]
    if options is None:
      self.fail("--no-postprocess 必须以 parseOnly intent 进入 orchestrator")
    self.assertTrue(options.parseOnly)

  def test_parse_only_flags_are_mutually_exclusive(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)

      result = _runCli(
        "parse",
        "--project-root",
        str(projectRoot),
        "--input",
        "https://example.com/sample.pdf",
        "--parse-only",
        "--no-postprocess",
      )

    self.assertEqual(result.returncode, 2)
    self.assertEqual(result.stdout, "")
    self.assertIn("not allowed with argument", result.stderr)
    self.assertIn("--parse-only", result.stderr)
    self.assertIn("--no-postprocess", result.stderr)

  def test_postprocess_rejects_parse_only_flags(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = Path(tmp) / "project"
      for flag in ["--parse-only", "--no-postprocess"]:
        with self.subTest(flag=flag):
          result = _runCli(
            "postprocess",
            "--project-root",
            str(projectRoot),
            "--source-kind",
            "book",
            "--input",
            str(Path(tmp) / "sample.pdf"),
            flag,
          )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn(flag, result.stderr)
        self.assertIn("仅支持 parse 子命令", result.stderr)

  def test_page_range_grammar_normalizes_closed_intervals(self):
    cases = {
      "1": (((1, 1),), "1"),
      "1-10": (((1, 10),), "1-10"),
      "2,4-6": (((2, 2), (4, 6)), "2,4-6"),
      "4-6,2,5,4": (((2, 2), (4, 6)), "2,4-6"),
      "3,2,1": (((1, 3),), "1-3"),
    }

    for raw, (expectedIntervals, expectedNormalized) in cases.items():
      with self.subTest(raw=raw):
        intervals = document_parser._parsePageRange(raw)
        self.assertEqual(intervals, expectedIntervals)
        self.assertEqual(document_parser._formatPageRange(intervals), expectedNormalized)

  def test_page_range_grammar_rejects_invalid_values(self):
    invalidValues = ["0", "-1", "4-2", "1,,2", "abc", "1.5", ""]

    for raw in invalidValues:
      with self.subTest(raw=raw):
        with self.assertRaises(ValueError):
          document_parser._parsePageRange(raw)

  def test_local_pdf_page_range_preflight_counts_pages(self):
    with tempfile.TemporaryDirectory() as tmp:
      pdfPath = Path(tmp) / "sample.pdf"
      _writeTinyPdf(pdfPath, pageCount=2)

      preflight = document_parser._preflightPageRange(
        inputValue=str(pdfPath),
        pageRangeRaw="2",
      )

      self.assertEqual(preflight.requestedPageRange, "2")
      self.assertEqual(preflight.normalizedPageRange, "2")
      self.assertEqual(preflight.intervals, ((2, 2),))
      self.assertEqual(preflight.pdfPageCount, 2)
      self.assertEqual(preflight.rangeSource, "local-pdf")

  def test_local_pdf_without_page_range_records_page_count_without_blocking(self):
    with tempfile.TemporaryDirectory() as tmp:
      pdfPath = Path(tmp) / "large.pdf"
      _writeTinyPdf(pdfPath, pageCount=244)

      preflight = document_parser._preflightPageRange(
        inputValue=str(pdfPath),
        pageRangeRaw=None,
      )

      self.assertIsNone(preflight.requestedPageRange)
      self.assertIsNone(preflight.normalizedPageRange)
      self.assertEqual(preflight.intervals, ())
      self.assertEqual(preflight.pdfPageCount, 244)
      self.assertEqual(preflight.rangeSource, "local-pdf")

  def test_local_pdf_out_of_bounds_page_range_fails_before_provider_call(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      pdfPath = Path(tmp) / "sample.pdf"
      _writeTinyPdf(pdfPath, pageCount=2)

      result = _runCli(
        "parse",
        "--project-root",
        str(projectRoot),
        "--input",
        str(pdfPath),
        "--page-range",
        "3",
      )

      self.assertEqual(result.returncode, 2)
      self.assertEqual(result.stdout, "")
      self.assertTrue(result.stderr.startswith("ERROR:"), msg=f"stderr=\n{result.stderr}\n")
      self.assertIn("超出 PDF 页数", result.stderr)

  def test_local_non_pdf_with_page_range_fails_before_provider_call(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)
      textPath = Path(tmp) / "sample.txt"
      textPath.write_text("not a pdf\n", encoding="utf-8")

      result = _runCli(
        "parse",
        "--project-root",
        str(projectRoot),
        "--input",
        str(textPath),
        "--page-range",
        "1",
      )

      self.assertEqual(result.returncode, 2)
      self.assertEqual(result.stdout, "")
      self.assertTrue(result.stderr.startswith("ERROR:"), msg=f"stderr=\n{result.stderr}\n")
      self.assertIn("仅支持本地 PDF", result.stderr)

  def test_invalid_page_range_fails_before_provider_call(self):
    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeProjectRoot(tmp)

      result = _runCli(
        "parse",
        "--project-root",
        str(projectRoot),
        "--input",
        "https://example.com/sample.pdf",
        "--page-range",
        "0",
      )

      self.assertEqual(result.returncode, 2)
      self.assertEqual(result.stdout, "")
      self.assertTrue(result.stderr.startswith("ERROR:"), msg=f"stderr=\n{result.stderr}\n")
      self.assertIn("page-range", result.stderr)

  def test_url_page_range_skips_local_preflight_and_preserves_request(self):
    originalReadPdfPageCount = document_parser._readPdfPageCount

    def failIfCalled(path: Path) -> int:
      self.fail(f"URL page-range 不应读取本地 PDF 页数：{path}")

    document_parser._readPdfPageCount = failIfCalled
    try:
      preflight = document_parser._preflightPageRange(
        inputValue="https://example.com/sample.pdf",
        pageRangeRaw="2,4-6",
      )
    finally:
      document_parser._readPdfPageCount = originalReadPdfPageCount

    self.assertEqual(preflight.requestedPageRange, "2,4-6")
    self.assertEqual(preflight.normalizedPageRange, "2,4-6")
    self.assertEqual(preflight.intervals, ((2, 2), (4, 6)))
    self.assertIsNone(preflight.pdfPageCount)
    self.assertEqual(preflight.rangeSource, "url")


if __name__ == "__main__":
  unittest.main()

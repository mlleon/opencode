import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
import sys
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast


_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
_FIXTURES_ROOT = _HERE / "fixtures" / "staging-book" / "document_parser_output"
if str(_SKILL_ROOT) not in sys.path:
  sys.path.insert(0, str(_SKILL_ROOT))
_DOCUMENT_PARSER_PATH = _SKILL_ROOT / "scripts" / "document_parser.py"
_DOCUMENT_PARSER_SPEC = importlib.util.spec_from_file_location("document_parser_for_tests", _DOCUMENT_PARSER_PATH)
assert _DOCUMENT_PARSER_SPEC is not None
assert _DOCUMENT_PARSER_SPEC.loader is not None
_documentParser = importlib.util.module_from_spec(_DOCUMENT_PARSER_SPEC)
sys.modules[_DOCUMENT_PARSER_SPEC.name] = _documentParser
_DOCUMENT_PARSER_SPEC.loader.exec_module(_documentParser)
_sha12FromStagingInputs = cast(Callable[[Path], str], _documentParser._sha12FromStagingInputs)


def _makeTmpProject(tmpDir: str) -> Path:
  projectRoot = Path(tmpDir) / "project"
  projectRoot.mkdir(parents=True, exist_ok=True)
  (projectRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
  vaultRoot = projectRoot / "memory-source"
  (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
  return projectRoot


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


def _assertOneLineJson(test: unittest.TestCase, stdout: str, *, context: str) -> dict[str, object]:
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
  return cast(dict[str, object], data)


def _jsonStr(data: dict[str, object], key: str) -> str:
  value = data[key]
  assert isinstance(value, str)
  return value


def _jsonInt(data: dict[str, object], key: str) -> int:
  value = data[key]
  assert isinstance(value, int)
  return value


def _jsonObject(data: dict[str, object], key: str) -> dict[str, object]:
  value = data[key]
  assert isinstance(value, dict)
  return cast(dict[str, object], value)


def _jsonList(data: dict[str, object], key: str) -> list[object]:
  value = data[key]
  assert isinstance(value, list)
  return cast(list[object], value)


def _assertPostprocessStdoutSchema(test: unittest.TestCase, data: dict[str, object], *, projectRoot: Path):
  required = [
    "projectRoot",
    "sourceKind",
    "finalStem",
    "stagingDocRoot",
    "rawDir",
    "assetsDir",
    "metaPath",
    "manifestPath",
    "writtenFiles",
  ]
  for key in required:
    test.assertIn(key, data, msg=f"postprocess stdout JSON 必须包含 {key}")

  test.assertIsInstance(data["projectRoot"], str)
  test.assertEqual(Path(_jsonStr(data, "projectRoot")).resolve(), projectRoot.resolve(), msg="projectRoot 必须等于传入的 projectRoot(绝对路径)")

  test.assertIsInstance(data["sourceKind"], str)
  test.assertIn(data["sourceKind"], {"book", "article", "paper", "web"})

  finalStem = _jsonStr(data, "finalStem")
  test.assertIsInstance(finalStem, str)
  test.assertRegex(finalStem, r".+__h[0-9a-f]{12}$", msg="finalStem 必须形如 <humanStem>__h<sha12>")

  for pathKey in ["stagingDocRoot", "rawDir", "assetsDir", "metaPath", "manifestPath"]:
    value = _jsonStr(data, pathKey)
    test.assertIsInstance(value, str, msg=f"{pathKey} 必须是 string")
    test.assertTrue(Path(value).is_absolute(), msg=f"{pathKey} 必须是绝对路径")

  rawDir = Path(_jsonStr(data, "rawDir"))
  assetsDir = Path(_jsonStr(data, "assetsDir"))
  test.assertTrue(rawDir.exists(), msg="rawDir 指向的目录必须存在")
  test.assertTrue(assetsDir.exists(), msg="assetsDir 指向的目录必须存在")
  test.assertTrue(Path(_jsonStr(data, "metaPath")).exists(), msg="metaPath 指向的文件必须存在")
  test.assertTrue(Path(_jsonStr(data, "manifestPath")).exists(), msg="manifestPath 指向的文件必须存在")

  wf = _jsonObject(data, "writtenFiles")
  test.assertIsInstance(wf, dict, msg="writtenFiles 必须是 object")
  for key in ["rawMarkdownCount", "assetBinaryCount", "manifestCount", "metaCount"]:
    test.assertIn(key, wf, msg=f"writtenFiles 必须包含 {key}")
    _jsonInt(wf, key)
  test.assertGreaterEqual(_jsonInt(wf, "rawMarkdownCount"), 1)
  test.assertGreaterEqual(_jsonInt(wf, "manifestCount"), 1)
  test.assertGreaterEqual(_jsonInt(wf, "metaCount"), 1)


def _assertEvidenceLocalStdoutSchema(
  test: unittest.TestCase,
  data: dict[str, object],
  *,
  projectRoot: Path,
  outputRoot: Path,
):
  required = [
    "projectRoot",
    "sourceKind",
    "finalStem",
    "stagingDocRoot",
    "outputProfile",
    "outputRoot",
    "writtenFiles",
  ]
  for key in required:
    test.assertIn(key, data, msg=f"evidence-local stdout JSON 必须包含 {key}")

  for legacyKey in ["rawDir", "assetsDir", "metaPath", "manifestPath"]:
    test.assertNotIn(legacyKey, data, msg=f"evidence-local stdout 不应包含 legacy 字段 {legacyKey}")

  test.assertEqual(data["outputProfile"], "evidence-local")
  test.assertEqual(Path(_jsonStr(data, "projectRoot")).resolve(), projectRoot.resolve())
  test.assertEqual(Path(_jsonStr(data, "outputRoot")).resolve(), outputRoot.resolve())
  test.assertTrue(Path(_jsonStr(data, "outputRoot")).is_absolute(), msg="outputRoot 必须是绝对路径")
  test.assertEqual(data["sourceKind"], "book")
  test.assertRegex(_jsonStr(data, "finalStem"), r".+__h[0-9a-f]{12}$", msg="finalStem 必须形如 <humanStem>__h<sha12>")

  writtenFiles = _jsonList(data, "writtenFiles")
  test.assertIsInstance(writtenFiles, list, msg="evidence-local writtenFiles 必须是 deterministic list")
  test.assertEqual(
    writtenFiles,
    [
      "normalized/document.md",
      "normalized/document.json",
      "normalized/images.manifest.json",
    ],
  )


def _assertRawHasNoBinaries(test: unittest.TestCase, rawRoot: Path):
  forbiddenSuffixes = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".jsonl",
  }
  for path in rawRoot.rglob("*"):
    if path.is_file() and path.suffix.lower() in forbiddenSuffixes:
      test.fail(f"raw/ 不应包含二进制或过程工件：{path}")


def _assertBookMetaTraceability(
  test: unittest.TestCase,
  *,
  meta: dict[str, object],
  booksDir: Path,
  stagingDocRoot: Path,
):
  # plan 要求：meta.json 必须包含拆分与可追溯字段（Step 7）。
  requiredTopKeys = [
    "splitMode",
    "strongCount",
    "candidateCount",
    "chapterCount",
    "tocRanges",
    "offsetRef",
    "postprocessedDocumentPath",
    "postprocessedDocumentSha256",
    "chunks",
  ]
  for key in requiredTopKeys:
    test.assertIn(key, meta, msg=f"meta.json 必须包含字段：{key}")

  test.assertIn(meta["splitMode"], {"chapter", "chunk"}, msg="splitMode 必须为 chapter|chunk")
  for key in ["strongCount", "candidateCount", "chapterCount"]:
    test.assertIsInstance(meta[key], int, msg=f"{key} 必须是 int")
    test.assertGreaterEqual(_jsonInt(meta, key), 0, msg=f"{key} 必须 >= 0")

  test.assertIsInstance(meta["tocRanges"], list, msg="tocRanges 必须是 list（可为空）")
  for itemRaw in _jsonList(meta, "tocRanges"):
    item = cast(dict[str, object], itemRaw)
    test.assertIsInstance(item, dict, msg="tocRanges[] 必须是 object")
    test.assertIn("startLine", item)
    test.assertIn("endLine", item)
    _jsonInt(item, "startLine")
    _jsonInt(item, "endLine")

  test.assertEqual(meta["offsetRef"], "postprocessed_document", msg="offsetRef 必须固定为 postprocessed_document")

  postprocessedPath = Path(_jsonStr(meta, "postprocessedDocumentPath")).resolve()
  expectedPostprocessedPath = (stagingDocRoot / "postprocess" / "document.postprocessed.md").resolve()
  test.assertEqual(
    postprocessedPath,
    expectedPostprocessedPath,
    msg="postprocessedDocumentPath 必须指向 staging 内 postprocess/document.postprocessed.md",
  )
  test.assertTrue(postprocessedPath.exists(), msg="staging 必须生成并保留 document.postprocessed.md")
  test.assertIsInstance(meta["postprocessedDocumentSha256"], str)
  test.assertRegex(_jsonStr(meta, "postprocessedDocumentSha256"), r"^[0-9a-f]{64}$", msg="postprocessedDocumentSha256 必须是 64 位 hex")

  chunks = _jsonList(meta, "chunks")
  test.assertIsInstance(chunks, list, msg="chunks 必须是 list")
  test.assertGreaterEqual(len(chunks), 1, msg="chunks 至少包含 1 项")

  postprocessedText = postprocessedPath.read_text(encoding="utf-8")
  postLen = len(postprocessedText)

  for itemRaw in chunks:
    item = cast(dict[str, object], itemRaw)
    test.assertIsInstance(item, dict, msg="chunks[] 必须是 object")
    for key in ["fileName", "charStart", "charEnd", "preview"]:
      test.assertIn(key, item, msg=f"chunks[] 必须包含字段：{key}")
    fileName = _jsonStr(item, "fileName")
    charStart = _jsonInt(item, "charStart")
    charEnd = _jsonInt(item, "charEnd")
    test.assertIsInstance(item["preview"], str)
    test.assertGreaterEqual(charStart, 0)
    test.assertGreater(charEnd, charStart, msg="charEnd 必须 > charStart")
    test.assertLessEqual(charEnd, postLen, msg="charEnd 不得超过 postprocessed 文本长度")

    outPath = (booksDir / fileName).resolve()
    test.assertTrue(outPath.exists(), msg=f"chunks.fileName 指向的输出文件必须存在：{outPath}")


class PostprocessValidateContractTests(unittest.TestCase):
  def test_postprocess_book_happy_path_contract(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "book",
        "--staging-doc-root",
        str(stagingDocRoot),
      )

      self.assertEqual(
        result.returncode,
        0,
        msg=(
          "postprocess 必须支持并严格遵循："
          "postprocess --project-root <tmpProject> --source-kind book "
          "--staging-doc-root <STAGING_DOC_ROOT>。\n"
          f"stdout=\n{result.stdout}\n"
          f"stderr=\n{result.stderr}\n"
        ),
      )

      data = _assertOneLineJson(self, result.stdout, context="postprocess")
      _assertPostprocessStdoutSchema(self, data, projectRoot=projectRoot)
      finalStem = _jsonStr(data, "finalStem")

      booksDir = vaultRoot / "raw" / "04-books" / finalStem
      self.assertTrue(
        (booksDir / "ch-01.md").exists(),
        msg="书籍终态必须生成 raw/04-books/<finalStem>/ch-01.md",
      )
      self.assertTrue(
        (vaultRoot / "assets" / "raw" / "books" / finalStem).exists(),
        msg="书籍二进制资产必须进入 assets/raw/books/<finalStem>/",
      )
      self.assertTrue(
        (vaultRoot / "raw" / "05-images" / f"{finalStem}.md").exists(),
        msg="raw/05-images/ 必须生成 manifest-only：<finalStem>.md",
      )

      _assertRawHasNoBinaries(self, vaultRoot / "raw")

      # 书籍 meta.json 的拆分与可追溯字段合同
      metaPath = Path(_jsonStr(data, "metaPath")).resolve()
      metaRaw = json.loads(metaPath.read_text(encoding="utf-8"))
      self.assertIsInstance(metaRaw, dict)
      meta = cast(dict[str, object], metaRaw)
      _assertBookMetaTraceability(self, meta=meta, booksDir=booksDir, stagingDocRoot=stagingDocRoot)

  def test_postprocess_chunk_mode_when_candidate_headings_over_300(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-too-many-headings"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "book",
        "--staging-doc-root",
        str(stagingDocRoot),
      )

      self.assertEqual(
        result.returncode,
        0,
        msg=(
          "candidateCount > 300 时，postprocess 必须仍能完成并进入 chunk 模式。\n"
          f"stdout=\n{result.stdout}\n"
          f"stderr=\n{result.stderr}\n"
        ),
      )

      data = _assertOneLineJson(self, result.stdout, context="postprocess")

      _assertPostprocessStdoutSchema(self, data, projectRoot=projectRoot)

      finalStem = _jsonStr(data, "finalStem")
      metaFile = Path(_jsonStr(data, "metaPath"))
      self.assertTrue(metaFile.exists(), msg="postprocess 必须落盘 meta.json（metaPath 指向的文件必须存在）")

      try:
        metaRaw = json.loads(metaFile.read_text(encoding="utf-8"))
      except Exception as e:
        self.fail(f"meta.json 必须是合法 JSON：{e}\nmetaPath={metaFile}")
      self.assertIsInstance(metaRaw, dict)
      meta = cast(dict[str, object], metaRaw)

      self.assertEqual(
        meta.get("splitMode"),
        "chunk",
        msg="candidateCount > 300 时，meta.json 必须记录 splitMode=chunk",
      )

      booksDir = vaultRoot / "raw" / "04-books" / finalStem
      _assertBookMetaTraceability(self, meta=meta, booksDir=booksDir, stagingDocRoot=stagingDocRoot)

      chunkFiles = sorted(p.name for p in booksDir.glob("ch-*.md"))
      self.assertGreater(len(chunkFiles), 0, msg="chunk 模式必须生成至少 1 个 ch-xx.md")
      self.assertLessEqual(
        len(chunkFiles),
        100,
        msg="chunk 模式下生成的 ch-xx.md 数量必须有上限（≤100）",
      )

      _assertRawHasNoBinaries(self, vaultRoot / "raw")

  def test_validate_invocation_contract(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)

      postprocess = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "book",
        "--staging-doc-root",
        str(stagingDocRoot),
      )
      self.assertEqual(
        postprocess.returncode,
        0,
        msg=(
          "validate 合同测试需要先用 fixture 跑通 postprocess（book-demo）。\n"
          f"stdout=\n{postprocess.stdout}\n"
          f"stderr=\n{postprocess.stderr}\n"
        ),
      )

      result = _runCli(
        "validate",
        "--project-root",
        str(projectRoot),
      )

      self.assertEqual(
        result.returncode,
        0,
        msg=(
          "validate 必须支持并严格遵循：validate --project-root <tmpProject>。\n"
          f"stdout=\n{result.stdout}\n"
          f"stderr=\n{result.stderr}\n"
        ),
      )

  def test_postprocess_article_bucket_mapping(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "article",
        "--staging-doc-root",
        str(stagingDocRoot),
      )

      self.assertEqual(result.returncode, 0, msg=f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}\n")

      data = _assertOneLineJson(self, result.stdout, context="postprocess")
      _assertPostprocessStdoutSchema(self, data, projectRoot=projectRoot)
      self.assertEqual(data["sourceKind"], "article")

      finalStem = _jsonStr(data, "finalStem")
      rawDir = Path(_jsonStr(data, "rawDir")).resolve()
      assetsDir = Path(_jsonStr(data, "assetsDir")).resolve()

      self.assertEqual(rawDir, (vaultRoot / "raw" / "01-articles" / finalStem).resolve())
      self.assertEqual(assetsDir, (vaultRoot / "assets" / "raw" / "articles" / finalStem).resolve())

      self.assertTrue((rawDir / "document.md").exists(), msg="article 必须生成 document.md")
      self.assertTrue((rawDir / "meta.json").exists(), msg="article 必须生成 meta.json")
      self.assertTrue((vaultRoot / "raw" / "05-images" / f"{finalStem}.md").exists(), msg="必须生成 manifest")

      _assertRawHasNoBinaries(self, vaultRoot / "raw")

  def test_postprocess_article_reuses_existing_final_stem_in_article_bucket(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"
    sha12 = _sha12FromStagingInputs(stagingDocRoot)
    existingFinalStem = f"EXIST__h{sha12}"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      vaultRoot = projectRoot / "memory-source"

      # 预先在 article bucket 下创建可复用目录：*__h<sha12>
      (vaultRoot / "raw" / "01-articles" / existingFinalStem).mkdir(parents=True, exist_ok=True)

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "article",
        "--staging-doc-root",
        str(stagingDocRoot),
        "--sha12",
        sha12,
      )

      # 终态目录存在时必须 hard-fail（exit code=6）。同时，finalStem 复用必须来自 article bucket。
      self.assertEqual(
        result.returncode,
        6,
        msg=(
          "当 raw/01-articles 下已存在 *__h<sha12> 目录时，postprocess(article) 必须复用该 finalStem，"
          "并因终态冲突按契约返回退出码 6。\n"
          f"stdout=\n{result.stdout}\n"
          f"stderr=\n{result.stderr}\n"
        ),
      )
      self.assertEqual(result.stdout, "", msg="冲突失败时 stdout 必须为空")
      self.assertTrue(result.stderr.startswith("ERROR:"), msg="冲突失败时 stderr 必须以 ERROR: 开头")

  def test_postprocess_evidence_local_writes_only_normalized_outputs(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      outputRoot = projectRoot / ".omo" / "evidence" / "document-parser-test"

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "book",
        "--staging-doc-root",
        str(stagingDocRoot),
        "--output-profile",
        "evidence-local",
        "--output-root",
        ".omo/evidence/document-parser-test",
      )

      self.assertEqual(result.returncode, 0, msg=f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}\n")
      data = _assertOneLineJson(self, result.stdout, context="postprocess evidence-local")
      _assertEvidenceLocalStdoutSchema(self, data, projectRoot=projectRoot, outputRoot=outputRoot)

      expectedFiles = [
        outputRoot / "normalized" / "document.md",
        outputRoot / "normalized" / "document.json",
        outputRoot / "normalized" / "images.manifest.json",
      ]
      for path in expectedFiles:
        self.assertTrue(path.exists(), msg=f"evidence-local 必须写入 {path}")

      actualFiles = sorted(path.relative_to(outputRoot).as_posix() for path in outputRoot.rglob("*") if path.is_file())
      self.assertEqual(
        actualFiles,
        [
          "normalized/document.json",
          "normalized/document.md",
          "normalized/images.manifest.json",
        ],
        msg="evidence-local 只能写 deterministic text/json/manifest 输出",
      )

      forbiddenSuffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}
      for path in outputRoot.rglob("*"):
        self.assertFalse(
          path.is_file() and path.suffix.lower() in forbiddenSuffixes,
          msg=f"evidence-local 不得复制图片/PDF 二进制：{path}",
        )

      manifestRaw = json.loads((outputRoot / "normalized" / "images.manifest.json").read_text(encoding="utf-8"))
      self.assertIsInstance(manifestRaw, dict)
      manifest = cast(dict[str, object], manifestRaw)
      self.assertEqual(manifest["sourceKind"], "book")
      self.assertEqual(manifest["stagingDocRoot"], str(stagingDocRoot.resolve()))
      images = _jsonList(manifest, "images")
      self.assertEqual(len(images), 1)
      imageRaw = images[0]
      self.assertIsInstance(imageRaw, dict)
      image = cast(dict[str, object], imageRaw)
      self.assertEqual(_jsonStr(image, "relativePath"), "normalized/images/xxx.jpg")
      self.assertRegex(_jsonStr(image, "sha256"), r"^[0-9a-f]{64}$")
      self.assertEqual(_jsonInt(image, "byteCount"), (stagingDocRoot / "normalized" / "images" / "xxx.jpg").stat().st_size)
      self.assertEqual(image["sourceKind"], "book")

      self.assertFalse((projectRoot / "memory-source" / "raw" / "04-books").exists())
      self.assertFalse((projectRoot / "memory-source" / "assets" / "raw" / "books").exists())

  def test_postprocess_evidence_local_rejects_uncontained_output_roots(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)
      outsideTarget = Path(tmp) / "outside-target"
      outsideTarget.mkdir()
      symlinkRoot = projectRoot / ".omo" / "evidence" / "symlink-out"
      symlinkRoot.parent.mkdir(parents=True, exist_ok=True)
      symlinkRoot.symlink_to(outsideTarget, target_is_directory=True)

      rejectedRoots = [
        str(Path(tmp) / "absolute-output"),
        "../outside",
        "outputs/document-parser-test",
        ".omo/evidence/symlink-out/nested",
      ]

      for outputRoot in rejectedRoots:
        with self.subTest(outputRoot=outputRoot):
          result = _runCli(
            "postprocess",
            "--project-root",
            str(projectRoot),
            "--source-kind",
            "book",
            "--staging-doc-root",
            str(stagingDocRoot),
            "--output-profile",
            "evidence-local",
            "--output-root",
            outputRoot,
          )

          self.assertNotEqual(result.returncode, 0, msg=f"outputRoot 应 fail closed: {outputRoot}")
          self.assertEqual(result.stdout, "", msg="containment 失败时 stdout 必须为空")
          self.assertIn("ERROR:", result.stderr)

      self.assertFalse((projectRoot / "outputs").exists(), msg="非 evidence project-local root 不应被创建")
      self.assertEqual(list(outsideTarget.iterdir()), [], msg="symlink escape 目标不应被写入")

  def test_postprocess_evidence_local_requires_output_root(self):
    stagingDocRoot = _FIXTURES_ROOT / "book-demo"

    with tempfile.TemporaryDirectory() as tmp:
      projectRoot = _makeTmpProject(tmp)

      result = _runCli(
        "postprocess",
        "--project-root",
        str(projectRoot),
        "--source-kind",
        "book",
        "--staging-doc-root",
        str(stagingDocRoot),
        "--output-profile",
        "evidence-local",
      )

      self.assertNotEqual(result.returncode, 0)
      self.assertEqual(result.stdout, "")
      self.assertIn("ERROR:", result.stderr)


if __name__ == "__main__":
  unittest.main()

import json
import os
import subprocess
import tempfile
import unittest
import sys
import re
from pathlib import Path


from scripts.document_parser import _sha12FromStagingInputs


_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
_FIXTURES_ROOT = _HERE / "fixtures" / "staging-book" / "document_parser_output"


def _makeTmpProject(tmpDir: str) -> Path:
  projectRoot = Path(tmpDir) / "project"
  vaultRoot = projectRoot / "memory-source"
  (vaultRoot / "raw").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "assets").mkdir(parents=True, exist_ok=True)
  (vaultRoot / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
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


def _assertPostprocessStdoutSchema(test: unittest.TestCase, data: dict, *, projectRoot: Path):
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
  test.assertEqual(Path(data["projectRoot"]).resolve(), projectRoot.resolve(), msg="projectRoot 必须等于传入的 projectRoot(绝对路径)")

  test.assertIsInstance(data["sourceKind"], str)
  test.assertIn(data["sourceKind"], {"book", "article", "paper", "web"})

  finalStem = data["finalStem"]
  test.assertIsInstance(finalStem, str)
  test.assertRegex(finalStem, r".+__h[0-9a-f]{12}$", msg="finalStem 必须形如 <humanStem>__h<sha12>")

  for pathKey in ["stagingDocRoot", "rawDir", "assetsDir", "metaPath", "manifestPath"]:
    value = data[pathKey]
    test.assertIsInstance(value, str, msg=f"{pathKey} 必须是 string")
    test.assertTrue(Path(value).is_absolute(), msg=f"{pathKey} 必须是绝对路径")

  rawDir = Path(data["rawDir"])
  assetsDir = Path(data["assetsDir"])
  test.assertTrue(rawDir.exists(), msg="rawDir 指向的目录必须存在")
  test.assertTrue(assetsDir.exists(), msg="assetsDir 指向的目录必须存在")
  test.assertTrue(Path(data["metaPath"]).exists(), msg="metaPath 指向的文件必须存在")
  test.assertTrue(Path(data["manifestPath"]).exists(), msg="manifestPath 指向的文件必须存在")

  wf = data["writtenFiles"]
  test.assertIsInstance(wf, dict, msg="writtenFiles 必须是 object")
  for key in ["rawMarkdownCount", "assetBinaryCount", "manifestCount", "metaCount"]:
    test.assertIn(key, wf, msg=f"writtenFiles 必须包含 {key}")
    test.assertIsInstance(wf[key], int, msg=f"writtenFiles.{key} 必须是 int")
  test.assertGreaterEqual(wf["rawMarkdownCount"], 1)
  test.assertGreaterEqual(wf["manifestCount"], 1)
  test.assertGreaterEqual(wf["metaCount"], 1)


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


def _assertBookMetaTraceability(test: unittest.TestCase, *, meta: dict, booksDir: Path, stagingDocRoot: Path):
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
    test.assertGreaterEqual(meta[key], 0, msg=f"{key} 必须 >= 0")

  test.assertIsInstance(meta["tocRanges"], list, msg="tocRanges 必须是 list（可为空）")
  for item in meta["tocRanges"]:
    test.assertIsInstance(item, dict, msg="tocRanges[] 必须是 object")
    test.assertIn("startLine", item)
    test.assertIn("endLine", item)
    test.assertIsInstance(item["startLine"], int)
    test.assertIsInstance(item["endLine"], int)

  test.assertEqual(meta["offsetRef"], "postprocessed_document", msg="offsetRef 必须固定为 postprocessed_document")

  postprocessedPath = Path(meta["postprocessedDocumentPath"]).resolve()
  expectedPostprocessedPath = (stagingDocRoot / "postprocess" / "document.postprocessed.md").resolve()
  test.assertEqual(
    postprocessedPath,
    expectedPostprocessedPath,
    msg="postprocessedDocumentPath 必须指向 staging 内 postprocess/document.postprocessed.md",
  )
  test.assertTrue(postprocessedPath.exists(), msg="staging 必须生成并保留 document.postprocessed.md")
  test.assertIsInstance(meta["postprocessedDocumentSha256"], str)
  test.assertRegex(meta["postprocessedDocumentSha256"], r"^[0-9a-f]{64}$", msg="postprocessedDocumentSha256 必须是 64 位 hex")

  chunks = meta["chunks"]
  test.assertIsInstance(chunks, list, msg="chunks 必须是 list")
  test.assertGreaterEqual(len(chunks), 1, msg="chunks 至少包含 1 项")

  postprocessedText = postprocessedPath.read_text(encoding="utf-8")
  postLen = len(postprocessedText)

  for item in chunks:
    test.assertIsInstance(item, dict, msg="chunks[] 必须是 object")
    for key in ["fileName", "charStart", "charEnd", "preview"]:
      test.assertIn(key, item, msg=f"chunks[] 必须包含字段：{key}")
    test.assertIsInstance(item["fileName"], str)
    test.assertIsInstance(item["charStart"], int)
    test.assertIsInstance(item["charEnd"], int)
    test.assertIsInstance(item["preview"], str)
    test.assertGreaterEqual(item["charStart"], 0)
    test.assertGreater(item["charEnd"], item["charStart"], msg="charEnd 必须 > charStart")
    test.assertLessEqual(item["charEnd"], postLen, msg="charEnd 不得超过 postprocessed 文本长度")

    outPath = (booksDir / item["fileName"]).resolve()
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
      finalStem = data["finalStem"]

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
      metaPath = Path(data["metaPath"]).resolve()
      meta = json.loads(metaPath.read_text(encoding="utf-8"))
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

      finalStem = data["finalStem"]
      metaFile = Path(data["metaPath"])
      self.assertTrue(metaFile.exists(), msg="postprocess 必须落盘 meta.json（metaPath 指向的文件必须存在）")

      try:
        meta = json.loads(metaFile.read_text(encoding="utf-8"))
      except Exception as e:
        self.fail(f"meta.json 必须是合法 JSON：{e}\nmetaPath={metaFile}")

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

      finalStem = data["finalStem"]
      rawDir = Path(data["rawDir"]).resolve()
      assetsDir = Path(data["assetsDir"]).resolve()

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


if __name__ == "__main__":
  unittest.main()

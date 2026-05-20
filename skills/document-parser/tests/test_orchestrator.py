import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


from importlib import import_module


_orchestrator = import_module("scripts.orchestrator")

DocumentParserOrchestratorError = _orchestrator.DocumentParserOrchestratorError
parseOne = _orchestrator.parseOne


@dataclass
class _Paths:
  rawMineruDir: Path
  rawPaddleocrDir: Path
  normalizedDir: Path
  normalizedImagesDir: Path
  normalizedMarkdownPath: Path
  normalizedJsonPath: Path
  documentRoot: Path


class _FakeMineru:
  def __init__(self, *, behavior: str):
    self.behavior = behavior
    self.calledUrl = 0
    self.calledLocal = 0

  def extractFromUrl(self, *, url: str, outputDir: Path):
    self.calledUrl += 1
    if self.behavior == "ok":
      return _makePaths(outputDir=outputDir, stem="a")
    if self.behavior == "quota":
      raise Exception("HTTP 200, code=-60018, msg=Daily extract task limit reached")
    raise Exception("HTTP 500, msg=internal")

  def extractFromLocalFiles(self, *, filePaths, outputDir: Path):
    self.calledLocal += 1
    if self.behavior == "ok":
      return [_makePaths(outputDir=outputDir, stem="a")]
    if self.behavior == "quota":
      raise Exception("HTTP 200, code=-60018, msg=Daily extract task limit reached")
    raise Exception("HTTP 500, msg=internal")


class _FakePaddle:
  def __init__(self, *, behavior: str):
    self.behavior = behavior
    self.calledUrl = 0
    self.calledFile = 0

  def extractFromUrl(self, *, url: str, outputDir: Path):
    self.calledUrl += 1
    if self.behavior == "ok":
      return _makePaths(outputDir=outputDir, stem="a")
    raise Exception("HTTP 429, code=12002, msg=request too fast")

  def extractFromFile(self, *, filePath: Path, outputDir: Path):
    self.calledFile += 1
    if self.behavior == "ok":
      return _makePaths(outputDir=outputDir, stem="a")
    raise Exception("HTTP 429, code=12002, msg=request too fast")


def _makePaths(*, outputDir: Path, stem: str):
  root = outputDir / "document_parser_output" / stem
  normalized = root / "normalized"
  return _Paths(
    rawMineruDir=root / "raw" / "mineru",
    rawPaddleocrDir=root / "raw" / "paddleocr",
    normalizedDir=normalized,
    normalizedImagesDir=normalized / "images",
    normalizedMarkdownPath=normalized / "document.md",
    normalizedJsonPath=normalized / "document.json",
    documentRoot=root,
  )


class OrchestratorTests(unittest.TestCase):
  def test_mineru_success_no_fallback(self):
    mineru = _FakeMineru(behavior="ok")
    paddle = _FakePaddle(behavior="ok")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      result = parseOne(
        source="https://example.com/a.pdf",
        outputDir=outputDir,
        mineruAdapter=mineru,
        paddleAdapter=paddle,
      )

    self.assertEqual(mineru.calledUrl, 1)
    self.assertEqual(paddle.calledUrl, 0)
    self.assertTrue(str(result.paths.documentRoot).endswith("document_parser_output/a"))

  def test_no_fallback_does_not_require_paddle_token(self):
    mineru = _FakeMineru(behavior="ok")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      parseOne(
        source="https://example.com/a.pdf",
        outputDir=outputDir,
        mineruAdapter=mineru,
        paddleAdapter=None,
      )

  def test_quota_triggers_fallback_for_pdf_url(self):
    mineru = _FakeMineru(behavior="quota")
    paddle = _FakePaddle(behavior="ok")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      parseOne(
        source="https://example.com/a.pdf",
        outputDir=outputDir,
        mineruAdapter=mineru,
        paddleAdapter=paddle,
      )

    self.assertEqual(mineru.calledUrl, 1)
    self.assertEqual(paddle.calledUrl, 1)

  def test_quota_does_not_fallback_for_docx(self):
    mineru = _FakeMineru(behavior="quota")
    paddle = _FakePaddle(behavior="ok")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with self.assertRaisesRegex(Exception, "code=-60018"):
        parseOne(
          source="/tmp/a.docx",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
        )

    self.assertEqual(paddle.calledFile, 0)

  def test_fallback_failure_returns_both_errors(self):
    mineru = _FakeMineru(behavior="quota")
    paddle = _FakePaddle(behavior="fail")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with self.assertRaises(DocumentParserOrchestratorError) as ctx:
        parseOne(
          source="https://example.com/a.pdf",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
        )

    msg = str(ctx.exception)
    self.assertIn("mineru_error=", msg)
    self.assertIn("paddleocr_error=", msg)


if __name__ == "__main__":
  unittest.main()

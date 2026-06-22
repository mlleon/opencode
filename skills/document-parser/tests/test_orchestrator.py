import tempfile
import unittest
import json
from dataclasses import dataclass
from pathlib import Path


from importlib import import_module


_orchestrator = import_module("scripts.orchestrator")

DocumentParserOrchestratorError = _orchestrator.DocumentParserOrchestratorError
DocumentParserFallbackDisabledError = _orchestrator.DocumentParserFallbackDisabledError
DocumentParserPageLimitError = _orchestrator.DocumentParserPageLimitError
ParseOptions = _orchestrator.ParseOptions
parseMany = _orchestrator.parseMany
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
    self.lastOptions = None

  def extractFromUrl(self, *, url: str, outputDir: Path, options=None):
    self.calledUrl += 1
    self.lastOptions = options
    if self.behavior == "ok":
      return _makePaths(outputDir=outputDir, stem="a")
    if self.behavior == "quota":
      raise Exception("HTTP 200, code=-60018, msg=Daily extract task limit reached")
    if self.behavior == "page_limit":
      raise Exception("HTTP 200, code=-60006, msg=The page count exceeds the 200 page limit")
    raise Exception("HTTP 500, msg=internal")

  def extractFromLocalFiles(self, *, filePaths, outputDir: Path, options=None):
    self.calledLocal += 1
    self.lastOptions = options
    if self.behavior == "ok":
      return [_makePaths(outputDir=outputDir, stem="a")]
    if self.behavior == "quota":
      raise Exception("HTTP 200, code=-60018, msg=Daily extract task limit reached")
    if self.behavior == "page_limit":
      raise Exception("HTTP 200, code=-60006, msg=The page count exceeds the 200 page limit")
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
  def test_parse_options_defaults_are_provider_neutral(self):
    options = ParseOptions()

    self.assertIsNone(options.pageRange)
    self.assertIsNone(options.modelVersion)
    self.assertIsNone(options.language)
    self.assertIsNone(options.isOcr)
    self.assertIsNone(options.enableTable)
    self.assertIsNone(options.enableFormula)
    self.assertIsNone(options.pdfPageCount)
    self.assertFalse(options.parseOnly)
    self.assertFalse(options.disableFallback)

  def test_parse_one_forwards_typed_options_to_mineru_adapter(self):
    mineru = _FakeMineru(behavior="ok")
    paddle = _FakePaddle(behavior="ok")
    options = ParseOptions(
      pageRange="1-10",
      modelVersion="vlm",
      language="ch",
      isOcr=False,
      enableTable=False,
      enableFormula=False,
      pdfPageCount=244,
      parseOnly=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      result = parseOne(
        source="https://example.com/a.pdf",
        outputDir=outputDir,
        mineruAdapter=mineru,
        paddleAdapter=paddle,
        options=options,
      )

    self.assertEqual(mineru.calledUrl, 1)
    self.assertIs(mineru.lastOptions, options)
    self.assertEqual(paddle.calledUrl, 0)
    self.assertTrue(str(result.paths.documentRoot).endswith("document_parser_output/a"))

  def test_parse_many_accepts_typed_options_for_each_source(self):
    mineru = _FakeMineru(behavior="ok")
    options = ParseOptions(pageRange="2", parseOnly=True)

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      results = parseMany(
        sources=["https://example.com/a.pdf", "https://example.com/b.pdf"],
        outputDir=outputDir,
        mineruAdapter=mineru,
        options=options,
      )

    self.assertEqual(len(results), 2)
    self.assertEqual(mineru.calledUrl, 2)
    self.assertIs(mineru.lastOptions, options)

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

  def test_default_quota_like_failure_still_calls_paddle_once(self):
    mineru = _FakeMineru(behavior="quota")
    paddle = _FakePaddle(behavior="ok")
    options = ParseOptions(disableFallback=False)

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      parseOne(
        source="https://example.com/a.pdf",
        outputDir=outputDir,
        mineruAdapter=mineru,
        paddleAdapter=paddle,
        options=options,
      )

    self.assertEqual(mineru.calledUrl, 1)
    self.assertEqual(paddle.calledUrl, 1)

  def test_disable_fallback_quota_like_failure_fails_closed_before_paddle(self):
    mineru = _FakeMineru(behavior="quota")
    paddle = _FakePaddle(behavior="ok")
    options = ParseOptions(disableFallback=True)

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with self.assertRaises(DocumentParserFallbackDisabledError) as ctx:
        parseOne(
          source="https://example.com/a.pdf",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
          options=options,
        )

    payload = ctx.exception.toDict()
    self.assertEqual(mineru.calledUrl, 1)
    self.assertEqual(paddle.calledUrl, 0)
    self.assertIs(payload["fallbackDisabled"], True)
    self.assertIs(payload["fallbackAttempted"], False)
    self.assertEqual(payload["primaryProvider"], "mineru_v4")
    self.assertEqual(payload["blockedFallbackProvider"], "paddleocr")
    self.assertEqual(payload["primaryError"]["stage"], "mineru_v4")
    self.assertEqual(payload["primaryError"]["httpStatus"], 200)
    self.assertEqual(payload["primaryError"]["code"], -60018)
    self.assertEqual(payload["primaryError"]["msg"], "Daily extract task limit reached")
    self.assertIn("code=-60018", payload["primaryError"]["errMsg"])
    self.assertEqual(json.loads(str(ctx.exception)), payload)

  def test_page_limit_error_shape_is_unchanged_with_or_without_no_fallback(self):
    for disableFallback in (False, True):
      with self.subTest(disableFallback=disableFallback):
        mineru = _FakeMineru(behavior="page_limit")
        paddle = _FakePaddle(behavior="ok")
        options = ParseOptions(
          pageRange="201-244",
          pdfPageCount=244,
          parseOnly=True,
          disableFallback=disableFallback,
        )

        with tempfile.TemporaryDirectory() as tmp:
          outputDir = Path(tmp)
          with self.assertRaises(DocumentParserPageLimitError) as ctx:
            parseOne(
              source="/tmp/a.pdf",
              outputDir=outputDir,
              mineruAdapter=mineru,
              paddleAdapter=paddle,
              options=options,
            )

        payload = ctx.exception.toDict()
        self.assertEqual(mineru.calledLocal, 1)
        self.assertEqual(paddle.calledFile, 0)
        self.assertEqual(
          payload,
          {
            "errorCode": -60006,
            "provider": "mineru_v4",
            "pdfPageCount": 244,
            "requestedPageRange": "201-244",
            "suggestedPageRange": "1-200",
            "retryHint": payload["retryHint"],
          },
        )
        self.assertIn("--page-range 1-200", payload["retryHint"])
        self.assertIn("本地 PDF 共 244 页", payload["retryHint"])

  def test_parse_only_does_not_change_fallback_policy(self):
    with self.subTest(disableFallback=False):
      mineru = _FakeMineru(behavior="quota")
      paddle = _FakePaddle(behavior="ok")
      options = ParseOptions(parseOnly=True, disableFallback=False)

      with tempfile.TemporaryDirectory() as tmp:
        outputDir = Path(tmp)
        parseOne(
          source="https://example.com/a.pdf",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
          options=options,
        )

      self.assertEqual(mineru.calledUrl, 1)
      self.assertEqual(paddle.calledUrl, 1)

    with self.subTest(disableFallback=True):
      mineru = _FakeMineru(behavior="quota")
      paddle = _FakePaddle(behavior="ok")
      options = ParseOptions(parseOnly=True, disableFallback=True)

      with tempfile.TemporaryDirectory() as tmp:
        outputDir = Path(tmp)
        with self.assertRaises(DocumentParserFallbackDisabledError) as ctx:
          parseOne(
            source="https://example.com/a.pdf",
            outputDir=outputDir,
            mineruAdapter=mineru,
            paddleAdapter=paddle,
            options=options,
          )

      self.assertEqual(mineru.calledUrl, 1)
      self.assertEqual(paddle.calledUrl, 0)

  def test_provider_page_limit_for_url_returns_structured_error_without_paddle_fallback(self):
    mineru = _FakeMineru(behavior="page_limit")
    paddle = _FakePaddle(behavior="ok")
    options = ParseOptions(pageRange=None, parseOnly=True)

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with self.assertRaises(DocumentParserPageLimitError) as ctx:
        parseOne(
          source="https://example.com/a.pdf",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
          options=options,
        )

    payload = ctx.exception.toDict()
    self.assertEqual(mineru.calledUrl, 1)
    self.assertEqual(paddle.calledUrl, 0)
    self.assertEqual(payload["errorCode"], -60006)
    self.assertEqual(payload["provider"], "mineru_v4")
    self.assertIsNone(payload["pdfPageCount"])
    self.assertIsNone(payload["requestedPageRange"])
    self.assertEqual(payload["suggestedPageRange"], "1-200")
    self.assertIn("--page-range 1-200", payload["retryHint"])
    self.assertEqual(json.loads(str(ctx.exception)), payload)

  def test_provider_page_limit_includes_local_pdf_page_count_when_available(self):
    mineru = _FakeMineru(behavior="page_limit")
    paddle = _FakePaddle(behavior="ok")
    options = ParseOptions(pageRange="201-244", pdfPageCount=244, parseOnly=True)

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with self.assertRaises(DocumentParserPageLimitError) as ctx:
        parseOne(
          source="/tmp/a.pdf",
          outputDir=outputDir,
          mineruAdapter=mineru,
          paddleAdapter=paddle,
          options=options,
        )

    payload = ctx.exception.toDict()
    self.assertEqual(mineru.calledLocal, 1)
    self.assertEqual(paddle.calledFile, 0)
    self.assertEqual(payload["errorCode"], -60006)
    self.assertEqual(payload["pdfPageCount"], 244)
    self.assertEqual(payload["requestedPageRange"], "201-244")
    self.assertEqual(payload["suggestedPageRange"], "1-200")
    self.assertIn("本地 PDF 共 244 页", payload["retryHint"])

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

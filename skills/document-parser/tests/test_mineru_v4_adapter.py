import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch
import sys
from importlib.util import spec_from_file_location, module_from_spec


_SKILL_ROOT = Path(__file__).resolve().parent.parent

# Dynamically load modules to avoid LSP import resolution issues
_mineru_v4_spec = spec_from_file_location(
  "scripts.providers.mineru_v4",
  _SKILL_ROOT / "scripts" / "providers" / "mineru_v4.py"
)
assert _mineru_v4_spec is not None and _mineru_v4_spec.loader is not None
_mineru_v4_module = module_from_spec(_mineru_v4_spec)
sys.modules["scripts.providers.mineru_v4"] = _mineru_v4_module
_mineru_v4_spec.loader.exec_module(_mineru_v4_module)

_orchestrator_spec = spec_from_file_location(
  "scripts.orchestrator",
  _SKILL_ROOT / "scripts" / "orchestrator.py"
)
assert _orchestrator_spec is not None and _orchestrator_spec.loader is not None
_orchestrator_module = module_from_spec(_orchestrator_spec)
sys.modules["scripts.orchestrator"] = _orchestrator_module
_orchestrator_spec.loader.exec_module(_orchestrator_module)

MinerUV4Adapter = _mineru_v4_module.MinerUV4Adapter
MinerUV4BatchLimitError = _mineru_v4_module.MinerUV4BatchLimitError
MinerUV4Config = _mineru_v4_module.MinerUV4Config
MinerUV4PollTimeoutError = _mineru_v4_module.MinerUV4PollTimeoutError
ParseOptions = _orchestrator_module.ParseOptions


class _FakeResponse:
  def __init__(
    self,
    *,
    statusCode: int,
    jsonBody: Optional[Dict[str, object]] = None,
    text: str = "",
    content: bytes = b"",
  ):
    self.status_code = statusCode
    self._jsonBody = jsonBody
    self.text = text
    self.content = content

  def json(self):
    if self._jsonBody is None:
      raise ValueError("not json")
    return self._jsonBody


def _buildZipBytes(*, markdown: str, jsonObj: object, imageName: str = "a.png") -> bytes:
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("full.md", markdown)
    zf.writestr("content_list_v2.json", json.dumps(jsonObj, ensure_ascii=False))
    zf.writestr(f"images/{imageName}", b"img")
  return buf.getvalue()


class MinerUV4AdapterTests(unittest.TestCase):
  def test_url_submit_running_done(self):
    zipBytes = _buildZipBytes(
      markdown="![x](./images/a.png)\n",
      jsonObj=[{"type": "p", "text": "hi"}],
    )

    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollRunning = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"state": "running"}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {"state": "done", "full_zip_url": "https://zip"},
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollRunning, pollDone])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=zipBytes),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir)

      self.assertTrue((paths.rawMineruDir / "full.md").exists())
      self.assertTrue((paths.rawMineruDir / "content_list_v2.json").exists())
      self.assertTrue((paths.rawMineruDir / "images" / "a.png").exists())
      self.assertTrue(paths.normalizedMarkdownPath.exists())
      self.assertTrue(paths.normalizedJsonPath.exists())
      self.assertTrue((paths.normalizedImagesDir / "a.png").exists())

      md = paths.normalizedMarkdownPath.read_text(encoding="utf-8")
      self.assertIn("![x](images/a.png)", md)

      submitPayload = session.request.call_args_list[0].kwargs["json"]
      self.assertEqual(submitPayload, {"url": "https://example.com/a.pdf"})

  def test_url_submit_payload_includes_page_ranges_and_core_params(self):
    zipBytes = _buildZipBytes(
      markdown="# hi\n",
      jsonObj=[{"type": "p", "text": "hi"}],
    )

    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {"state": "done", "full_zip_url": "https://zip"},
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollDone])

    options = ParseOptions(
      pageRange="2-4",
      modelVersion="vlm",
      language="ch",
      isOcr=False,
      enableTable=False,
      enableFormula=True,
      rangeSource="url",
      disableFallback=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=zipBytes),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromUrl(
          url="https://example.com/a.pdf",
          outputDir=outputDir,
          options=options,
        )

      submitPayload = session.request.call_args_list[0].kwargs["json"]
      self.assertEqual(
        submitPayload,
        {
          "url": "https://example.com/a.pdf",
          "page_ranges": "2-4",
          "model_version": "vlm",
          "language": "ch",
          "is_ocr": False,
          "enable_table": False,
          "enable_formula": True,
        },
      )
      self.assertNotIn("disableFallback", submitPayload)
      self.assertNotIn("disable_fallback", submitPayload)

      normalized = json.loads(paths.normalizedJsonPath.read_text(encoding="utf-8"))
      self.assertEqual(
        normalized["extras"]["parseRequest"],
        {
          "requestedPageRange": "2-4",
          "providerPageRange": "2-4",
          "rangeSource": "url",
          "disableFallback": True,
          "modelVersion": "vlm",
          "language": "ch",
          "isOcr": False,
          "enableTable": False,
          "enableFormula": True,
        },
      )
      self.assertEqual(
        normalized["extras"]["parseResult"],
        {
          "providerPageRange": "2-4",
          "taskId": "t1",
        },
      )
      self.assertEqual(normalized["extras"]["raw"], [{"type": "p", "text": "hi"}])
      self.assertEqual(normalized["meta"]["backend"], "mineru_v4")

  def test_local_batch_payload_includes_page_ranges_and_core_params(self):
    zipBytes = _buildZipBytes(
      markdown="# local\n",
      jsonObj=[{"type": "p", "text": "local"}],
    )

    batchResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"batch_id": "b1", "file_urls": ["https://upload"]}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {
          "extract_result": [
            {
              "state": "done",
              "file_name": "a.pdf",
              "full_zip_url": "https://zip",
            }
          ]
        },
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[batchResp, pollDone])

    options = ParseOptions(
      pageRange="3",
      modelVersion="doc",
      language="en",
      isOcr=True,
      enableTable=True,
      enableFormula=False,
      pdfPageCount=42,
      rangeSource="local-pdf",
      disableFallback=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      filePath = outputDir / "a.pdf"
      filePath.write_bytes(b"pdf")
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch("scripts.providers.mineru_v4.requests.put", return_value=_FakeResponse(statusCode=200)),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=zipBytes),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromLocalFiles(
          filePaths=[filePath],
          outputDir=outputDir,
          options=options,
        )[0]

      batchPayload = session.request.call_args_list[0].kwargs["json"]
      self.assertEqual(
        batchPayload,
        {
          "files": [
            {
              "name": "a.pdf",
              "page_ranges": "3",
              "model_version": "doc",
              "language": "en",
              "is_ocr": True,
              "enable_table": True,
              "enable_formula": False,
            }
          ]
        },
      )
      self.assertNotIn("disableFallback", batchPayload["files"][0])
      self.assertNotIn("disable_fallback", batchPayload["files"][0])

      normalized = json.loads(paths.normalizedJsonPath.read_text(encoding="utf-8"))
      self.assertEqual(
        normalized["extras"]["parseRequest"],
        {
          "requestedPageRange": "3",
          "providerPageRange": "3",
          "rangeSource": "local-pdf",
          "pdfPageCount": 42,
          "disableFallback": True,
          "modelVersion": "doc",
          "language": "en",
          "isOcr": True,
          "enableTable": True,
          "enableFormula": False,
        },
      )
      self.assertEqual(normalized["extras"]["parseResult"]["batchId"], "b1")
      self.assertEqual(normalized["extras"]["parseResult"]["providerPageRange"], "3")

  def test_no_options_url_payload_preserves_baseline(self):
    """options=None 时 URL submit payload 只包含 url 字段，无额外 parse 参数。"""
    zipBytes = _buildZipBytes(
      markdown="# hi\n",
      jsonObj=[{"type": "p", "text": "hi"}],
    )

    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {"state": "done", "full_zip_url": "https://zip"},
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollDone])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=zipBytes),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir, options=None)

      submitPayload = session.request.call_args_list[0].kwargs["json"]
      self.assertEqual(submitPayload, {"url": "https://example.com/a.pdf"})

      normalized = json.loads(paths.normalizedJsonPath.read_text(encoding="utf-8"))
      # options=None 时 parseRequest 为空 dict → 不写入 extras
      self.assertNotIn("parseRequest", normalized["extras"])
      # parseResult 仍然记录 taskId 作为 provenance
      self.assertEqual(normalized["extras"]["parseResult"], {"taskId": "t1"})
      self.assertEqual(normalized["extras"]["raw"], [{"type": "p", "text": "hi"}])
      self.assertEqual(normalized["meta"]["backend"], "mineru_v4")
      self.assertEqual(normalized["meta"]["fallback"], False)

  def test_no_options_local_batch_payload_preserves_baseline(self):
    """options=None 时 local batch payload 的 files 条目只包含 name 字段。"""
    zipBytes = _buildZipBytes(
      markdown="# local\n",
      jsonObj=[{"type": "p", "text": "local"}],
    )

    batchResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"batch_id": "b1", "file_urls": ["https://upload"]}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {
          "extract_result": [
            {
              "state": "done",
              "file_name": "a.pdf",
              "full_zip_url": "https://zip",
            }
          ]
        },
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[batchResp, pollDone])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      filePath = outputDir / "a.pdf"
      filePath.write_bytes(b"pdf")
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch("scripts.providers.mineru_v4.requests.put", return_value=_FakeResponse(statusCode=200)),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=zipBytes),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromLocalFiles(
          filePaths=[filePath],
          outputDir=outputDir,
          options=None,
        )[0]

      batchPayload = session.request.call_args_list[0].kwargs["json"]
      self.assertEqual(batchPayload, {"files": [{"name": "a.pdf"}]})

      normalized = json.loads(paths.normalizedJsonPath.read_text(encoding="utf-8"))
      self.assertNotIn("parseRequest", normalized["extras"])
      self.assertEqual(normalized["extras"]["parseResult"], {"batchId": "b1"})
      self.assertEqual(normalized["extras"]["raw"], [{"type": "p", "text": "local"}])

  def test_url_state_failed(self):
    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollFailed = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"state": "failed", "err_msg": "bad"}},
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollFailed])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(Exception, "state=failed"):
          adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir)

  def test_code_not_zero_fails(self):
    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": -1, "msg": "no"},
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with patch("scripts.providers.mineru_v4.requests.Session", return_value=session):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(Exception, "code=-1"):
          adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir)

  def test_poll_timeout(self):
    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollRunning = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"state": "running"}},
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollRunning, pollRunning, pollRunning])

    times = [0.0, 0.0, 1.0, 2.0, 3.1]

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
        patch("scripts.providers.mineru_v4.time.time", side_effect=times),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=3, pollIntervalSeconds=0))
        with self.assertRaises(MinerUV4PollTimeoutError):
          adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir)

  def test_batch_gt_50_fails(self):
    adapter = MinerUV4Adapter(config=MinerUV4Config(token="t"))
    filePaths = [Path(f"/tmp/{i}.pdf") for i in range(51)]
    with self.assertRaises(MinerUV4BatchLimitError):
      adapter.extractFromLocalFiles(filePaths=filePaths, outputDir=Path("/tmp"))

  def test_zip_path_traversal_rejected(self):
    zipBytes = _buildZipBytes(
      markdown="# hi\n",
      jsonObj=[{"type": "p"}],
    )
    buf = io.BytesIO(zipBytes)
    with zipfile.ZipFile(buf, "a", compression=zipfile.ZIP_DEFLATED) as zf:
      zf.writestr("../evil.txt", "nope")

    postResp = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"task_id": "t1"}},
    )
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {"state": "done", "full_zip_url": "https://zip"},
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[postResp, pollDone])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.mineru_v4.requests.Session", return_value=session),
        patch(
          "scripts.providers.mineru_v4.requests.get",
          return_value=_FakeResponse(statusCode=200, content=buf.getvalue()),
        ),
        patch("scripts.providers.mineru_v4.time.sleep", return_value=None),
      ):
        adapter = MinerUV4Adapter(config=MinerUV4Config(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(Exception, "路径穿越"):
          adapter.extractFromUrl(url="https://example.com/a.pdf", outputDir=outputDir)


if __name__ == "__main__":
  unittest.main()

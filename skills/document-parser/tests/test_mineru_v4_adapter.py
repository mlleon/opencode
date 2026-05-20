import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch


from scripts.providers.mineru_v4 import (
  MinerUV4Adapter,
  MinerUV4BatchLimitError,
  MinerUV4Config,
  MinerUV4PollTimeoutError,
)


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

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import Mock, patch


from scripts.providers.paddleocr_jobs import (
  PaddleOcrJobsAdapter,
  PaddleOcrJobsApiError,
  PaddleOcrJobsConfig,
  PaddleOcrJobsPollTimeoutError,
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


class PaddleOcrJobsAdapterTests(unittest.TestCase):
  def test_pending_running_done_downloads_and_localizes_images(self):
    submitResp = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"jobId": "jid"}})
    pollPending = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"state": "pending"}})
    pollRunning = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"state": "running"}})
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {
          "state": "done",
          "resultUrl": {
            "jsonUrl": "https://jsonl",
            "markdownUrl": "https://md",
          },
        },
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[submitResp, pollPending, pollRunning, pollDone])

    remoteImageUrl = "https://example.com/a.png"
    remoteDigest = hashlib.sha256(remoteImageUrl.encode("utf-8")).hexdigest()[:16]
    remoteFileName = f"{remoteDigest}.png"

    dataBytes = b"hello-image"
    dataB64 = base64.b64encode(dataBytes).decode("ascii")
    dataDigest = hashlib.sha256(dataBytes).hexdigest()[:16]
    dataFileName = f"{dataDigest}.png"

    markdown = (
      f"![r]({remoteImageUrl})\n"
      f"![d](data:image/png;base64,{dataB64})\n"
    )

    def fakeGet(url: str, **_kwargs):
      if url == "https://jsonl":
        return _FakeResponse(statusCode=200, text="{}\n")
      if url == "https://md":
        return _FakeResponse(statusCode=200, text=markdown)
      if url == remoteImageUrl:
        return _FakeResponse(statusCode=200, content=b"PNG")
      raise AssertionError(f"unexpected url: {url}")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.paddleocr_jobs.requests.Session", return_value=session),
        patch("scripts.providers.paddleocr_jobs.requests.get", side_effect=fakeGet),
        patch("scripts.providers.paddleocr_jobs.time.sleep", return_value=None),
      ):
        adapter = PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        paths = adapter.extractFromUrl(url="https://example.com/doc.pdf", outputDir=outputDir)

      self.assertTrue((paths.rawPaddleocrDir / "job-jid.jsonl").exists())
      self.assertTrue((paths.rawPaddleocrDir / "job-jid.md").exists())
      self.assertTrue(paths.normalizedMarkdownPath.exists())
      self.assertTrue(paths.normalizedJsonPath.exists())
      self.assertTrue((paths.normalizedImagesDir / remoteFileName).exists())
      self.assertTrue((paths.normalizedImagesDir / dataFileName).exists())

      normalized = paths.normalizedMarkdownPath.read_text(encoding="utf-8")
      self.assertIn(f"![r](images/{remoteFileName})", normalized)
      self.assertIn(f"![d](images/{dataFileName})", normalized)

  def test_failed_state_raises(self):
    submitResp = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"jobId": "jid"}})
    pollFailed = _FakeResponse(
      statusCode=200,
      jsonBody={"code": 0, "data": {"state": "failed", "errorMsg": "bad"}},
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[submitResp, pollFailed])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.paddleocr_jobs.requests.Session", return_value=session),
        patch("scripts.providers.paddleocr_jobs.time.sleep", return_value=None),
      ):
        adapter = PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(PaddleOcrJobsApiError, "state=failed"):
          adapter.extractFromUrl(url="https://example.com/doc.pdf", outputDir=outputDir)

  def test_poll_timeout_raises(self):
    submitResp = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"jobId": "jid"}})
    pollRunning = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"state": "running"}})

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[submitResp, pollRunning, pollRunning, pollRunning])

    times = [0.0, 0.0, 1.0, 2.0, 3.1]

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.paddleocr_jobs.requests.Session", return_value=session),
        patch("scripts.providers.paddleocr_jobs.time.sleep", return_value=None),
        patch("scripts.providers.paddleocr_jobs.time.time", side_effect=times),
      ):
        adapter = PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token="t", timeoutSeconds=3, pollIntervalSeconds=0))
        with self.assertRaises(PaddleOcrJobsPollTimeoutError):
          adapter.extractFromUrl(url="https://example.com/doc.pdf", outputDir=outputDir)

  def test_download_markdown_fails_non_200(self):
    submitResp = _FakeResponse(statusCode=200, jsonBody={"code": 0, "data": {"jobId": "jid"}})
    pollDone = _FakeResponse(
      statusCode=200,
      jsonBody={
        "code": 0,
        "data": {
          "state": "done",
          "resultUrl": {
            "jsonUrl": "https://jsonl",
            "markdownUrl": "https://md",
          },
        },
      },
    )

    session = Mock()
    session.headers = {}
    session.request = Mock(side_effect=[submitResp, pollDone])

    def fakeGet(url: str, **_kwargs):
      if url == "https://jsonl":
        return _FakeResponse(statusCode=200, text="{}\n")
      if url == "https://md":
        return _FakeResponse(statusCode=404, text="no")
      raise AssertionError(f"unexpected url: {url}")

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with (
        patch("scripts.providers.paddleocr_jobs.requests.Session", return_value=session),
        patch("scripts.providers.paddleocr_jobs.requests.get", side_effect=fakeGet),
      ):
        adapter = PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(PaddleOcrJobsApiError, "HTTP 404"):
          adapter.extractFromUrl(url="https://example.com/doc.pdf", outputDir=outputDir)

  def test_quota_limit_errors_are_explainable(self):
    session = Mock()
    session.headers = {}

    quotaResp = _FakeResponse(statusCode=403, jsonBody={"code": 12001, "msg": "已达每日页数上限"})
    session.request = Mock(side_effect=[quotaResp])

    with tempfile.TemporaryDirectory() as tmp:
      outputDir = Path(tmp)
      with patch("scripts.providers.paddleocr_jobs.requests.Session", return_value=session):
        adapter = PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token="t", timeoutSeconds=5, pollIntervalSeconds=0))
        with self.assertRaisesRegex(PaddleOcrJobsApiError, "HTTP 403"):
          adapter.extractFromUrl(url="https://example.com/doc.pdf", outputDir=outputDir)


if __name__ == "__main__":
  unittest.main()

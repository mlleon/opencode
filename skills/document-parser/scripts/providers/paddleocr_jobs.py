from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from scripts import errors
from scripts import output_contract


_DEFAULT_BASE_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr"
_DEFAULT_MODEL = "PaddleOCR-VL-1.5"


@dataclass(frozen=True)
class PaddleOcrJobsConfig:
  token: str
  baseUrl: str = _DEFAULT_BASE_URL
  timeoutSeconds: int = 600
  pollIntervalSeconds: float = 5.0


class PaddleOcrJobsAdapterError(Exception):
  pass


class PaddleOcrJobsPollTimeoutError(PaddleOcrJobsAdapterError):
  pass


class PaddleOcrJobsApiError(PaddleOcrJobsAdapterError):
  def __init__(
    self,
    *,
    httpStatus: Optional[int],
    code: Optional[int],
    msg: Optional[str],
    errMsg: Optional[str],
    stage: str,
  ):
    self.httpStatus = httpStatus
    self.code = code
    self.msg = msg
    self.errMsg = errMsg
    self.stage = stage

    pieces: List[str] = []
    if httpStatus is not None:
      pieces.append(f"HTTP {httpStatus}")
    if code is not None:
      pieces.append(f"code={code}")
    if msg is not None:
      pieces.append(f"msg={msg}")
    if errMsg:
      pieces.append(f"errMsg={errMsg}")
    super().__init__(", ".join(pieces) or "PaddleOCR Jobs API error")


class PaddleOcrJobsAdapter:
  def __init__(self, *, config: PaddleOcrJobsConfig):
    self._config = config
    self._session = requests.Session()
    self._session.headers.update({"Authorization": f"Bearer {config.token}"})

  def extractFromUrl(
    self,
    *,
    url: str,
    outputDir: Path,
    stem: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    optionalPayload: Optional[Dict[str, object]] = None,
  ) -> output_contract.OutputPaths:
    paths = output_contract.get_output_paths(
      output_dir=outputDir,
      stem=stem or _getSourceStem(url),
    )
    _ensureDirs(paths)

    jobId = self._submitUrlJob(url=url, model=model, optionalPayload=optionalPayload)
    jobData = self._pollJob(jobId=jobId)
    jsonUrl, markdownUrl = _extractResultUrls(jobData)

    rawJsonText = self._downloadText(url=jsonUrl, stage="download_json")
    rawMarkdownText = self._downloadText(url=markdownUrl, stage="download_markdown")

    rawJsonPath = paths.rawPaddleocrDir / f"job-{jobId}.jsonl"
    rawMarkdownPath = paths.rawPaddleocrDir / f"job-{jobId}.md"
    rawJsonPath.write_text(rawJsonText, encoding="utf-8")
    rawMarkdownPath.write_text(rawMarkdownText, encoding="utf-8")

    normalizedMarkdown = self._localizeMarkdownImages(
      markdown=rawMarkdownText,
      imagesDir=paths.normalizedImagesDir,
    )
    output_contract.validate_offline_reproducible(normalizedMarkdown)
    paths.normalizedMarkdownPath.write_text(normalizedMarkdown, encoding="utf-8")

    envelope = output_contract.build_normalized_envelope(
      output_dir=outputDir,
      stem=paths.documentRoot.name,
      input_source=url,
      backend="paddleocr_jobs",
      markdown=normalizedMarkdown,
      fallback=True,
      warnings=[output_contract.DEGRADED_OCR_FALLBACK],
      pages=None,
      extras={"jobId": jobId, "raw": {"jsonUrl": jsonUrl, "markdownUrl": markdownUrl}},
    )
    paths.normalizedJsonPath.write_text(
      json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
      encoding="utf-8",
    )

    return paths

  def extractFromFile(
    self,
    *,
    filePath: Path,
    outputDir: Path,
    stem: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    optionalPayload: Optional[Dict[str, object]] = None,
  ) -> output_contract.OutputPaths:
    paths = output_contract.get_output_paths(
      output_dir=outputDir,
      stem=stem or _getSourceStem(str(filePath)),
    )
    _ensureDirs(paths)

    jobId = self._submitFileJob(filePath=filePath, model=model, optionalPayload=optionalPayload)
    jobData = self._pollJob(jobId=jobId)
    jsonUrl, markdownUrl = _extractResultUrls(jobData)

    rawJsonText = self._downloadText(url=jsonUrl, stage="download_json")
    rawMarkdownText = self._downloadText(url=markdownUrl, stage="download_markdown")

    rawJsonPath = paths.rawPaddleocrDir / f"job-{jobId}.jsonl"
    rawMarkdownPath = paths.rawPaddleocrDir / f"job-{jobId}.md"
    rawJsonPath.write_text(rawJsonText, encoding="utf-8")
    rawMarkdownPath.write_text(rawMarkdownText, encoding="utf-8")

    normalizedMarkdown = self._localizeMarkdownImages(
      markdown=rawMarkdownText,
      imagesDir=paths.normalizedImagesDir,
    )
    output_contract.validate_offline_reproducible(normalizedMarkdown)
    paths.normalizedMarkdownPath.write_text(normalizedMarkdown, encoding="utf-8")

    envelope = output_contract.build_normalized_envelope(
      output_dir=outputDir,
      stem=paths.documentRoot.name,
      input_source=str(filePath),
      backend="paddleocr_jobs",
      markdown=normalizedMarkdown,
      fallback=True,
      warnings=[output_contract.DEGRADED_OCR_FALLBACK],
      pages=None,
      extras={"jobId": jobId, "raw": {"jsonUrl": jsonUrl, "markdownUrl": markdownUrl}},
    )
    paths.normalizedJsonPath.write_text(
      json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
      encoding="utf-8",
    )

    return paths

  def _submitUrlJob(
    self,
    *,
    url: str,
    model: str,
    optionalPayload: Optional[Dict[str, object]],
  ) -> str:
    payload: Dict[str, object] = {"fileUrl": url, "model": model}
    if optionalPayload is not None:
      payload["optionalPayload"] = optionalPayload

    resp = self._requestJson(
      method="POST",
      endpoint="/jobs",
      jsonBody=payload,
      files=None,
      stage="submit_url",
    )
    data = _extractDict(resp, "data")
    jobId = _extractStr(data, "jobId")
    if not jobId:
      raise PaddleOcrJobsApiError(
        httpStatus=200,
        code=None,
        msg="missing jobId",
        errMsg=json.dumps(resp, ensure_ascii=False),
        stage="submit_url",
      )
    return jobId

  def _submitFileJob(
    self,
    *,
    filePath: Path,
    model: str,
    optionalPayload: Optional[Dict[str, object]],
  ) -> str:
    data: Dict[str, object] = {"model": model}
    if optionalPayload is not None:
      data["optionalPayload"] = json.dumps(optionalPayload, ensure_ascii=False)

    with open(filePath, "rb") as f:
      resp = self._requestJson(
        method="POST",
        endpoint="/jobs",
        jsonBody=data,
        files={"file": f},
        stage="submit_file",
      )
    dataObj = _extractDict(resp, "data")
    jobId = _extractStr(dataObj, "jobId")
    if not jobId:
      raise PaddleOcrJobsApiError(
        httpStatus=200,
        code=None,
        msg="missing jobId",
        errMsg=json.dumps(resp, ensure_ascii=False),
        stage="submit_file",
      )
    return jobId

  def _pollJob(self, *, jobId: str) -> Dict[str, object]:
    start = time.time()
    while True:
      if time.time() - start > self._config.timeoutSeconds:
        raise PaddleOcrJobsPollTimeoutError(
          f"轮询超时 ({self._config.timeoutSeconds}s)，jobId: {jobId}"
        )

      resp = self._requestJson(
        method="GET",
        endpoint=f"/jobs/{jobId}",
        jsonBody=None,
        files=None,
        stage="poll",
      )
      data = _extractDict(resp, "data")
      state = _extractStr(data, "state")

      if state == "done":
        return data
      if state == "failed":
        errMsg = _extractStr(data, "errorMsg") or "解析失败"
        raise PaddleOcrJobsApiError(
          httpStatus=200,
          code=None,
          msg="state=failed",
          errMsg=errMsg,
          stage="poll",
        )

      time.sleep(self._config.pollIntervalSeconds)

  def _downloadText(self, *, url: str, stage: str) -> str:
    resp = requests.get(url, timeout=self._config.timeoutSeconds)
    if resp.status_code != 200:
      raise PaddleOcrJobsApiError(
        httpStatus=resp.status_code,
        code=None,
        msg="download failed",
        errMsg=resp.text,
        stage=stage,
      )
    return resp.text

  def _requestJson(
    self,
    *,
    method: str,
    endpoint: str,
    jsonBody: Optional[Dict[str, object]],
    files: Optional[Dict[str, BinaryIO]],
    stage: str,
  ) -> Dict[str, object]:
    url = f"{self._config.baseUrl}{endpoint}"

    if files is None:
      resp = self._session.request(
        method,
        url,
        json=jsonBody,
        timeout=self._config.timeoutSeconds,
      )
    else:
      resp = self._session.request(
        method,
        url,
        data=jsonBody,
        files=files,
        timeout=self._config.timeoutSeconds,
      )

    httpStatus = resp.status_code
    try:
      body = resp.json()
    except ValueError:
      body = {"raw": resp.text}

    normalized = errors.normalizeError(body)
    code = normalized.code
    msg = normalized.msg
    errMsg = normalized.errMsg

    if httpStatus != 200:
      raise PaddleOcrJobsApiError(
        httpStatus=httpStatus,
        code=code,
        msg=msg,
        errMsg=errMsg,
        stage=stage,
      )

    if not isinstance(body, dict):
      raise PaddleOcrJobsApiError(
        httpStatus=httpStatus,
        code=code,
        msg="non-dict response",
        errMsg=str(body),
        stage=stage,
      )

    if code not in (None, 0):
      raise PaddleOcrJobsApiError(
        httpStatus=httpStatus,
        code=code,
        msg=msg,
        errMsg=errMsg,
        stage=stage,
      )

    result: Dict[str, object] = {}
    for key, value in body.items():
      if isinstance(key, str):
        result[key] = value
    return result

  def _localizeMarkdownImages(self, *, markdown: str, imagesDir: Path) -> str:
    def repl(match: re.Match[str]) -> str:
      original = match.group(1).strip()
      urlPart, tail = _splitMarkdownLinkTarget(original)

      if urlPart.startswith("http://") or urlPart.startswith("https://"):
        fileName, content = _downloadRemoteImage(urlPart)
        dest = imagesDir / fileName
        dest.write_bytes(content)
        return match.group(0).replace(match.group(1), f"images/{fileName}{tail}")

      if urlPart.startswith("data:image/"):
        fileName, content = _decodeDataImage(urlPart)
        dest = imagesDir / fileName
        dest.write_bytes(content)
        return match.group(0).replace(match.group(1), f"images/{fileName}{tail}")

      return match.group(0)

    imagesDir.mkdir(parents=True, exist_ok=True)
    return _MARKDOWN_IMAGE_RE.sub(repl, markdown)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _downloadRemoteImage(url: str) -> Tuple[str, bytes]:
  resp = requests.get(url, timeout=30)
  if resp.status_code != 200:
    raise PaddleOcrJobsApiError(
      httpStatus=resp.status_code,
      code=None,
      msg="download image failed",
      errMsg=resp.text,
      stage="download_image",
    )
  ext = _guessImageExtFromUrl(url) or "bin"
  digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
  return f"{digest}.{ext}", resp.content


def _guessImageExtFromUrl(url: str) -> Optional[str]:
  parsed = urlparse(url)
  name = Path(parsed.path).name
  if not name:
    return None
  suffix = Path(name).suffix
  if not suffix:
    return None
  return suffix.lstrip(".")


def _decodeDataImage(dataUrl: str) -> Tuple[str, bytes]:
  if "," not in dataUrl:
    raise PaddleOcrJobsApiError(
      httpStatus=200,
      code=None,
      msg="invalid data image url",
      errMsg="missing comma separator",
      stage="decode_image",
    )
  header, payload = dataUrl.split(",", 1)
  match = re.match(r"data:image/([^;]+);base64", header)
  ext = match.group(1) if match else "bin"
  data = base64.b64decode(payload)
  digest = hashlib.sha256(data).hexdigest()[:16]
  return f"{digest}.{ext}", data


def _extractResultUrls(jobData: Dict[str, object]) -> Tuple[str, str]:
  resultUrlObj = jobData.get("resultUrl")
  if not isinstance(resultUrlObj, dict):
    raise PaddleOcrJobsApiError(
      httpStatus=200,
      code=None,
      msg="missing resultUrl",
      errMsg=json.dumps(jobData, ensure_ascii=False),
      stage="poll",
    )

  jsonUrl = resultUrlObj.get("jsonUrl")
  markdownUrl = resultUrlObj.get("markdownUrl")
  if not isinstance(jsonUrl, str) or not isinstance(markdownUrl, str):
    raise PaddleOcrJobsApiError(
      httpStatus=200,
      code=None,
      msg="missing jsonUrl/markdownUrl",
      errMsg=json.dumps(resultUrlObj, ensure_ascii=False),
      stage="poll",
    )

  return jsonUrl, markdownUrl


def _splitMarkdownLinkTarget(target: str) -> Tuple[str, str]:
  stripped = target.strip()
  if not stripped:
    return "", ""

  if stripped.startswith("<") and ">" in stripped:
    end = stripped.find(">")
    return stripped[1:end], stripped[end + 1 :]

  for idx, ch in enumerate(stripped):
    if ch.isspace():
      return stripped[:idx], stripped[idx:]
  return stripped, ""


def _ensureDirs(paths: output_contract.OutputPaths) -> None:
  paths.rawPaddleocrDir.mkdir(parents=True, exist_ok=True)
  paths.rawMineruDir.mkdir(parents=True, exist_ok=True)
  paths.normalizedDir.mkdir(parents=True, exist_ok=True)
  paths.normalizedImagesDir.mkdir(parents=True, exist_ok=True)


def _getSourceStem(source: str) -> str:
  if isinstance(source, str) and source.startswith("http"):
    parsed = urlparse(source)
    name = Path(parsed.path).name
    stem = Path(name).stem if name else "url"
    return stem or "url"
  return Path(source).stem or "file"


def _extractDict(data: Dict[str, object], key: str) -> Dict[str, object]:
  value = data.get(key)
  return value if isinstance(value, dict) else {}


def _extractStr(data: Dict[str, object], key: str) -> Optional[str]:
  value = data.get(key)
  if isinstance(value, str):
    stripped = value.strip()
    return stripped or None
  return None

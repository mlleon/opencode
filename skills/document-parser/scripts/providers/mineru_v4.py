from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from scripts import errors
from scripts import output_contract


_DEFAULT_BASE_URL = "https://mineru.net/api/v4"


@dataclass(frozen=True)
class MinerUV4Config:
  token: str
  baseUrl: str = _DEFAULT_BASE_URL
  timeoutSeconds: int = 600
  pollIntervalSeconds: float = 3.0


class MinerUV4AdapterError(Exception):
  pass


class MinerUV4PollTimeoutError(MinerUV4AdapterError):
  pass


class MinerUV4BatchLimitError(MinerUV4AdapterError):
  pass


class MinerUV4ApiError(MinerUV4AdapterError):
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
    super().__init__(", ".join(pieces) or "MinerU v4 API error")


class MinerUV4Adapter:
  def __init__(self, *, config: MinerUV4Config):
    self._config = config
    self._session = requests.Session()
    self._session.headers.update(
      {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
      }
    )

  def extractFromUrl(self, *, url: str, outputDir: Path) -> output_contract.OutputPaths:
    stem = _getSourceStem(url)
    paths = output_contract.get_output_paths(output_dir=outputDir, stem=stem)
    paths.rawMineruDir.mkdir(parents=True, exist_ok=True)
    paths.normalizedDir.mkdir(parents=True, exist_ok=True)
    paths.normalizedImagesDir.mkdir(parents=True, exist_ok=True)

    taskId = self._submitUrlTask(url=url)
    taskData = self._pollTask(taskId=taskId)
    zipUrl = _extractStr(taskData, "full_zip_url")
    if not zipUrl:
      raise MinerUV4ApiError(
        httpStatus=200,
        code=None,
        msg="missing full_zip_url",
        errMsg=json.dumps(taskData, ensure_ascii=False),
        stage="mineru_v4",
      )

    zipBytes = self._downloadZip(zipUrl)
    _extractZipBytes(zipBytes=zipBytes, destDir=paths.rawMineruDir)

    self._writeNormalizedIfPresent(
      outputDir=outputDir,
      stem=stem,
      inputSource=url,
      rawMineruDir=paths.rawMineruDir,
      normalizedImagesDir=paths.normalizedImagesDir,
      normalizedMarkdownPath=paths.normalizedMarkdownPath,
      normalizedJsonPath=paths.normalizedJsonPath,
    )
    return paths

  def extractFromLocalFiles(
    self,
    *,
    filePaths: List[Path],
    outputDir: Path,
  ) -> List[output_contract.OutputPaths]:
    if len(filePaths) > 50:
      raise MinerUV4BatchLimitError("/file-urls/batch 单次最多 50 个文件")

    batchId, uploadUrls = self._requestBatchUploadUrls(filePaths=filePaths)
    self._uploadFiles(filePaths=filePaths, uploadUrls=uploadUrls)

    extractResults = self._pollBatchResults(batchId=batchId)

    outputPathsList: List[output_contract.OutputPaths] = []
    for idx, item in enumerate(extractResults):
      state = _extractStr(item, "state")
      fileName = _extractStr(item, "file_name") or filePaths[idx].name
      stem = _getSourceStem(fileName)

      paths = output_contract.get_output_paths(output_dir=outputDir, stem=stem)
      paths.rawMineruDir.mkdir(parents=True, exist_ok=True)
      paths.normalizedDir.mkdir(parents=True, exist_ok=True)
      paths.normalizedImagesDir.mkdir(parents=True, exist_ok=True)

      if state == "done":
        zipUrl = _extractStr(item, "full_zip_url")
        if not zipUrl:
          raise MinerUV4ApiError(
            httpStatus=200,
            code=None,
            msg="missing full_zip_url",
            errMsg=json.dumps(item, ensure_ascii=False),
            stage="mineru_v4",
          )
        zipBytes = self._downloadZip(zipUrl)
        _extractZipBytes(zipBytes=zipBytes, destDir=paths.rawMineruDir)
        self._writeNormalizedIfPresent(
          outputDir=outputDir,
          stem=stem,
          inputSource=str(filePaths[idx]),
          rawMineruDir=paths.rawMineruDir,
          normalizedImagesDir=paths.normalizedImagesDir,
          normalizedMarkdownPath=paths.normalizedMarkdownPath,
          normalizedJsonPath=paths.normalizedJsonPath,
        )
      elif state == "failed":
        errMsg = _extractStr(item, "err_msg") or "解析失败"
        raise MinerUV4ApiError(
          httpStatus=200,
          code=None,
          msg="state=failed",
          errMsg=errMsg,
          stage="mineru_v4",
        )
      else:
        raise MinerUV4ApiError(
          httpStatus=200,
          code=None,
          msg=f"unexpected state={state}",
          errMsg=json.dumps(item, ensure_ascii=False),
          stage="mineru_v4",
        )

      outputPathsList.append(paths)

    return outputPathsList

  def _submitUrlTask(self, *, url: str) -> str:
    resp = self._requestJson(
      method="POST",
      endpoint="/extract/task",
      jsonBody={"url": url},
      stage="mineru_v4",
    )
    data = _extractDict(resp, "data")
    taskId = _extractStr(data, "task_id")
    if not taskId:
      raise MinerUV4ApiError(
        httpStatus=200,
        code=None,
        msg="missing task_id",
        errMsg=json.dumps(resp, ensure_ascii=False),
        stage="mineru_v4",
      )
    return taskId

  def _pollTask(self, *, taskId: str) -> Dict[str, object]:
    start = time.time()
    while True:
      if time.time() - start > self._config.timeoutSeconds:
        raise MinerUV4PollTimeoutError(f"轮询超时 ({self._config.timeoutSeconds}s)，task_id: {taskId}")

      resp = self._requestJson(
        method="GET",
        endpoint=f"/extract/task/{taskId}",
        jsonBody=None,
        stage="mineru_v4",
      )
      data = _extractDict(resp, "data")
      state = _extractStr(data, "state")

      if state == "done":
        return data
      if state == "failed":
        errMsg = _extractStr(data, "err_msg") or "解析失败"
        raise MinerUV4ApiError(
          httpStatus=200,
          code=None,
          msg="state=failed",
          errMsg=errMsg,
          stage="mineru_v4",
        )

      time.sleep(self._config.pollIntervalSeconds)

  def _requestBatchUploadUrls(self, *, filePaths: List[Path]) -> tuple[str, List[str]]:
    files: List[Dict[str, str]] = []
    for filePath in filePaths:
      files.append({"name": filePath.name})

    resp = self._requestJson(
      method="POST",
      endpoint="/file-urls/batch",
      jsonBody={"files": files},
      stage="mineru_v4",
    )
    data = _extractDict(resp, "data")
    batchId = _extractStr(data, "batch_id")
    fileUrlsObj = data.get("file_urls")
    uploadUrls: List[str] = []
    if isinstance(fileUrlsObj, list):
      for item in fileUrlsObj:
        if isinstance(item, str):
          uploadUrls.append(item)

    if not batchId or len(uploadUrls) != len(filePaths):
      raise MinerUV4ApiError(
        httpStatus=200,
        code=None,
        msg="missing batch_id or file_urls",
        errMsg=json.dumps(resp, ensure_ascii=False),
        stage="mineru_v4",
      )
    return batchId, uploadUrls

  def _uploadFiles(self, *, filePaths: List[Path], uploadUrls: List[str]) -> None:
    for filePath, uploadUrl in zip(filePaths, uploadUrls):
      with open(filePath, "rb") as f:
        resp = requests.put(uploadUrl, data=f, timeout=self._config.timeoutSeconds)
      if resp.status_code not in (200, 201):
        raise MinerUV4ApiError(
          httpStatus=resp.status_code,
          code=None,
          msg="upload failed",
          errMsg=resp.text,
          stage="mineru_v4",
        )

  def _pollBatchResults(self, *, batchId: str) -> List[Dict[str, object]]:
    start = time.time()
    while True:
      if time.time() - start > self._config.timeoutSeconds:
        raise MinerUV4PollTimeoutError(
          f"轮询超时 ({self._config.timeoutSeconds}s)，batch_id: {batchId}"
        )

      resp = self._requestJson(
        method="GET",
        endpoint=f"/extract-results/batch/{batchId}",
        jsonBody=None,
        stage="mineru_v4",
      )
      data = _extractDict(resp, "data")
      extractResultObj = data.get("extract_result")
      if not isinstance(extractResultObj, list):
        raise MinerUV4ApiError(
          httpStatus=200,
          code=None,
          msg="missing extract_result",
          errMsg=json.dumps(resp, ensure_ascii=False),
          stage="mineru_v4",
        )

      results: List[Dict[str, object]] = []
      pending = 0
      for item in extractResultObj:
        if not isinstance(item, dict):
          continue
        state = item.get("state")
        if state not in ("done", "failed"):
          pending += 1
        results.append(item)

      if pending == 0 and results:
        return results

      time.sleep(self._config.pollIntervalSeconds)

  def _downloadZip(self, zipUrl: str) -> bytes:
    resp = requests.get(zipUrl, timeout=self._config.timeoutSeconds)
    if resp.status_code != 200:
      raise MinerUV4ApiError(
        httpStatus=resp.status_code,
        code=None,
        msg="download zip failed",
        errMsg=resp.text,
        stage="mineru_v4",
      )
    return resp.content

  def _requestJson(
    self,
    *,
    method: str,
    endpoint: str,
    jsonBody: Optional[Dict[str, object]],
    stage: str,
  ) -> Dict[str, object]:
    url = f"{self._config.baseUrl}{endpoint}"
    resp = self._session.request(
      method,
      url,
      json=jsonBody,
      timeout=self._config.timeoutSeconds,
    )

    httpStatus = resp.status_code
    try:
      body = resp.json()
    except ValueError:
      body = {"raw": resp.text}

    if httpStatus != 200:
      raise MinerUV4ApiError(
        httpStatus=httpStatus,
        code=errors.normalizeError(body).code,
        msg=errors.normalizeError(body).msg,
        errMsg=errors.normalizeError(body).errMsg,
        stage=stage,
      )

    code = None
    msg = None
    if isinstance(body, dict):
      codeVal = body.get("code")
      msgVal = body.get("msg")
      if isinstance(codeVal, int):
        code = codeVal
      if isinstance(msgVal, str):
        msg = msgVal
    if code not in (None, 0):
      raise MinerUV4ApiError(
        httpStatus=httpStatus,
        code=code,
        msg=msg,
        errMsg=errors.normalizeError(body).errMsg,
        stage=stage,
      )

    if not isinstance(body, dict):
      raise MinerUV4ApiError(
        httpStatus=httpStatus,
        code=code,
        msg="non-dict response",
        errMsg=str(body),
        stage=stage,
      )

    result: Dict[str, object] = {}
    for key, value in body.items():
      if isinstance(key, str):
        result[key] = value
    return result

  def _writeNormalizedIfPresent(
    self,
    *,
    outputDir: Path,
    stem: str,
    inputSource: str,
    rawMineruDir: Path,
    normalizedImagesDir: Path,
    normalizedMarkdownPath: Path,
    normalizedJsonPath: Path,
  ) -> None:
    rawMarkdownPath = rawMineruDir / "full.md"
    rawJsonPath = rawMineruDir / "content_list_v2.json"
    rawImagesDir = rawMineruDir / "images"

    if rawImagesDir.exists() and rawImagesDir.is_dir():
      _copyTree(srcDir=rawImagesDir, destDir=normalizedImagesDir)

    if not rawMarkdownPath.exists() or not rawJsonPath.exists():
      return

    markdown = rawMarkdownPath.read_text(encoding="utf-8")
    markdown = _rewriteMarkdownImageLinks(markdown)
    output_contract.validate_offline_reproducible(markdown)

    normalizedMarkdownPath.write_text(markdown, encoding="utf-8")

    with open(rawJsonPath, encoding="utf-8") as f:
      rawJson = json.load(f)

    envelope = output_contract.build_normalized_envelope(
      output_dir=outputDir,
      stem=stem,
      input_source=inputSource,
      backend="mineru_v4",
      markdown=markdown,
      fallback=False,
      warnings=[],
      pages=None,
      extras={"raw": rawJson},
    )
    normalizedJsonPath.write_text(
      json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
      encoding="utf-8",
    )


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _rewriteMarkdownImageLinks(markdown: str) -> str:
  def repl(match: re.Match[str]) -> str:
    link = match.group(1).strip()
    if link.startswith("http://") or link.startswith("https://"):
      return match.group(0)

    normalized = link.replace("\\", "/")
    normalized = normalized.lstrip("./")
    parts = [p for p in normalized.split("/") if p]
    if "images" in parts:
      idx = parts.index("images")
      rel = "/".join(parts[idx:])
      return match.group(0).replace(match.group(1), rel)
    return match.group(0)

  return _MARKDOWN_IMAGE_RE.sub(repl, markdown)


def _getSourceStem(source: str) -> str:
  if isinstance(source, str) and source.startswith("http"):
    parsed = urlparse(source)
    name = Path(parsed.path).name
    stem = Path(name).stem if name else "url"
    return stem or "url"
  return Path(source).stem or "file"


def _extractZipBytes(*, zipBytes: bytes, destDir: Path) -> None:
  destDir.mkdir(parents=True, exist_ok=True)
  with zipfile.ZipFile(io.BytesIO(zipBytes)) as zf:
    _safeExtractAll(zf=zf, destDir=destDir)


def _safeExtractAll(*, zf: zipfile.ZipFile, destDir: Path) -> None:
  destDirResolved = destDir.resolve()
  for member in zf.infolist():
    memberName = member.filename
    if not memberName:
      continue
    memberPath = Path(memberName)

    if memberPath.is_absolute():
      raise MinerUV4AdapterError(f"zip 解压检测到绝对路径: {memberName}")

    targetPath = (destDirResolved / memberPath).resolve()
    if not str(targetPath).startswith(str(destDirResolved) + "/") and targetPath != destDirResolved:
      raise MinerUV4AdapterError(f"zip 解压检测到路径穿越: {memberName}")

    if member.is_dir():
      targetPath.mkdir(parents=True, exist_ok=True)
      continue

    targetPath.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(targetPath, "wb") as out:
      out.write(src.read())


def _copyTree(*, srcDir: Path, destDir: Path) -> None:
  destDir.mkdir(parents=True, exist_ok=True)
  for srcPath in srcDir.rglob("*"):
    rel = srcPath.relative_to(srcDir)
    destPath = destDir / rel
    if srcPath.is_dir():
      destPath.mkdir(parents=True, exist_ok=True)
      continue
    destPath.parent.mkdir(parents=True, exist_ok=True)
    destPath.write_bytes(srcPath.read_bytes())


def _extractDict(data: Dict[str, object], key: str) -> Dict[str, object]:
  value = data.get(key)
  return value if isinstance(value, dict) else {}


def _extractStr(data: Dict[str, object], key: str) -> Optional[str]:
  value = data.get(key)
  if isinstance(value, str):
    stripped = value.strip()
    return stripped or None
  return None

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from . import errors
from . import fallback_decider
from . import output_contract
from .credentials import getMinerUToken, getPaddleOcrToken
from .providers.mineru_v4 import MinerUV4Adapter, MinerUV4Config
from .providers.paddleocr_jobs import PaddleOcrJobsAdapter, PaddleOcrJobsConfig


class DocumentParserOrchestratorError(Exception):
  pass


class DocumentParserPageLimitError(DocumentParserOrchestratorError):
  def __init__(
    self,
    *,
    errorCode: int,
    provider: str,
    pdfPageCount: Optional[int],
    requestedPageRange: Optional[str],
    suggestedPageRange: str,
    retryHint: str,
  ):
    self.errorCode: int = errorCode
    self.provider: str = provider
    self.pdfPageCount: Optional[int] = pdfPageCount
    self.requestedPageRange: Optional[str] = requestedPageRange
    self.suggestedPageRange: str = suggestedPageRange
    self.retryHint: str = retryHint
    super().__init__(json.dumps(self.toDict(), ensure_ascii=False))

  def toDict(self) -> dict[str, object]:
    return {
      "errorCode": self.errorCode,
      "provider": self.provider,
      "pdfPageCount": self.pdfPageCount,
      "requestedPageRange": self.requestedPageRange,
      "suggestedPageRange": self.suggestedPageRange,
      "retryHint": self.retryHint,
    }


class DocumentParserFallbackDisabledError(DocumentParserOrchestratorError):
  def __init__(
    self,
    *,
    primaryProvider: str,
    blockedFallbackProvider: str,
    primaryError: errors.NormalizedError,
  ):
    self.fallbackDisabled: bool = True
    self.fallbackAttempted: bool = False
    self.primaryProvider: str = primaryProvider
    self.blockedFallbackProvider: str = blockedFallbackProvider
    self.primaryError: errors.NormalizedError = primaryError
    super().__init__(json.dumps(self.toDict(), ensure_ascii=False))

  def toDict(self) -> dict[str, object]:
    return {
      "fallbackDisabled": self.fallbackDisabled,
      "fallbackAttempted": self.fallbackAttempted,
      "primaryProvider": self.primaryProvider,
      "blockedFallbackProvider": self.blockedFallbackProvider,
      "primaryError": {
        "stage": self.primaryError.stage,
        "httpStatus": self.primaryError.httpStatus,
        "code": self.primaryError.code,
        "msg": self.primaryError.msg,
        "errMsg": self.primaryError.errMsg,
      },
    }


@dataclass(frozen=True)
class OrchestratorResult:
  paths: output_contract.OutputPaths


@dataclass(frozen=True)
class ParseOptions:
  pageRange: Optional[str] = None
  modelVersion: Optional[str] = None
  language: Optional[str] = None
  isOcr: Optional[bool] = None
  enableTable: Optional[bool] = None
  enableFormula: Optional[bool] = None
  pdfPageCount: Optional[int] = None
  rangeSource: Optional[str] = None
  parseOnly: bool = False
  disableFallback: bool = False


def parseOne(
  *,
  source: str,
  outputDir: Path,
  options: Optional[ParseOptions] = None,
  mineruAdapter: Optional[MinerUV4Adapter] = None,
  paddleAdapter: Optional[PaddleOcrJobsAdapter] = None,
) -> OrchestratorResult:
  mineru = mineruAdapter or MinerUV4Adapter(config=MinerUV4Config(token=getMinerUToken()))

  try:
    paths = _parseWithMineru(source=source, outputDir=outputDir, mineru=mineru, options=options)
    return OrchestratorResult(paths=paths)
  except Exception as mineruErr:
    if fallback_decider.isMinerUPageLimitError(mineruErr):
      raise _buildPageLimitError(err=mineruErr, options=options) from mineruErr

    if not fallback_decider.isMinerUQuotaLikeError(mineruErr, source=source):
      raise

    if not _isPaddleOcrSupportedSource(source):
      raise

    if options is not None and options.disableFallback:
      raise _buildFallbackDisabledError(err=mineruErr) from mineruErr

    paddle = paddleAdapter or PaddleOcrJobsAdapter(config=PaddleOcrJobsConfig(token=getPaddleOcrToken()))

    try:
      paths = _parseWithPaddle(source=source, outputDir=outputDir, paddle=paddle)
      return OrchestratorResult(paths=paths)
    except Exception as paddleErr:
      raise DocumentParserOrchestratorError(
        "MinerU 配额/限流触发回退，但 PaddleOCR 仍失败："
        f"mineru_error={mineruErr}; paddleocr_error={paddleErr}"
      ) from paddleErr


def parseMany(
  *,
  sources: List[str],
  outputDir: Path,
  options: Optional[ParseOptions] = None,
  mineruAdapter: Optional[MinerUV4Adapter] = None,
  paddleAdapter: Optional[PaddleOcrJobsAdapter] = None,
) -> List[OrchestratorResult]:
  results: List[OrchestratorResult] = []
  for source in sources:
    results.append(
      parseOne(
        source=source,
        outputDir=outputDir,
        options=options,
        mineruAdapter=mineruAdapter,
        paddleAdapter=paddleAdapter,
      )
    )
  return results


def _parseWithMineru(
  *,
  source: str,
  outputDir: Path,
  mineru: MinerUV4Adapter,
  options: Optional[ParseOptions],
) -> output_contract.OutputPaths:
  if source.startswith("http"):
    return mineru.extractFromUrl(url=source, outputDir=outputDir, options=options)
  return mineru.extractFromLocalFiles(filePaths=[Path(source)], outputDir=outputDir, options=options)[0]


def _parseWithPaddle(*, source: str, outputDir: Path, paddle: PaddleOcrJobsAdapter) -> output_contract.OutputPaths:
  if source.startswith("http"):
    return paddle.extractFromUrl(url=source, outputDir=outputDir)
  return paddle.extractFromFile(filePath=Path(source), outputDir=outputDir)


def _isPaddleOcrSupportedSource(source: str) -> bool:
  suffix = _guessSuffix(source)
  if suffix in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
    return True
  return False


def _buildPageLimitError(
  *,
  err: object,
  options: Optional[ParseOptions],
) -> DocumentParserPageLimitError:
  normalized = errors.normalizeError(err, stage="mineru_v4")
  requestedPageRange = options.pageRange if options is not None else None
  pdfPageCount = options.pdfPageCount if options is not None else None
  suggestedPageRange = "1-200"
  retryHint = _buildPageLimitRetryHint(
    suggestedPageRange=suggestedPageRange,
    requestedPageRange=requestedPageRange,
    pdfPageCount=pdfPageCount,
  )
  return DocumentParserPageLimitError(
    errorCode=normalized.code if normalized.code is not None else -60006,
    provider="mineru_v4",
    pdfPageCount=pdfPageCount,
    requestedPageRange=requestedPageRange,
    suggestedPageRange=suggestedPageRange,
    retryHint=retryHint,
  )


def _buildFallbackDisabledError(*, err: object) -> DocumentParserFallbackDisabledError:
  return DocumentParserFallbackDisabledError(
    primaryProvider="mineru_v4",
    blockedFallbackProvider="paddleocr",
    primaryError=errors.normalizeError(err, stage="mineru_v4"),
  )


def _buildPageLimitRetryHint(
  *,
  suggestedPageRange: str,
  requestedPageRange: Optional[str],
  pdfPageCount: Optional[int],
) -> str:
  parts = [
    f"MinerU 返回页数超限；请重新运行并显式添加 --page-range {suggestedPageRange}。",
    "本工具不会自动重试、拆分 PDF 或切换到 PaddleOCR。",
  ]
  if requestedPageRange is not None:
    parts.append(f"本次请求页段：{requestedPageRange}。")
  if pdfPageCount is not None:
    parts.append(f"本地 PDF 共 {pdfPageCount} 页。")
  return " ".join(parts)


def _guessSuffix(source: str) -> str:
  if source.startswith("http"):
    parsed = urlparse(source)
    return Path(parsed.path).suffix.lower()
  return Path(source).suffix.lower()

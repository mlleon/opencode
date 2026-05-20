from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from scripts import fallback_decider
from scripts import output_contract
from scripts.credentials import getMinerUToken, getPaddleOcrToken
from scripts.providers.mineru_v4 import MinerUV4Adapter, MinerUV4Config
from scripts.providers.paddleocr_jobs import PaddleOcrJobsAdapter, PaddleOcrJobsConfig


class DocumentParserOrchestratorError(Exception):
  pass


@dataclass(frozen=True)
class OrchestratorResult:
  paths: output_contract.OutputPaths


def parseOne(
  *,
  source: str,
  outputDir: Path,
  mineruAdapter: Optional[MinerUV4Adapter] = None,
  paddleAdapter: Optional[PaddleOcrJobsAdapter] = None,
) -> OrchestratorResult:
  mineru = mineruAdapter or MinerUV4Adapter(config=MinerUV4Config(token=getMinerUToken()))

  try:
    paths = _parseWithMineru(source=source, outputDir=outputDir, mineru=mineru)
    return OrchestratorResult(paths=paths)
  except Exception as mineruErr:
    if not fallback_decider.isMinerUQuotaLikeError(mineruErr, source=source):
      raise

    if not _isPaddleOcrSupportedSource(source):
      raise

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
  mineruAdapter: Optional[MinerUV4Adapter] = None,
  paddleAdapter: Optional[PaddleOcrJobsAdapter] = None,
) -> List[OrchestratorResult]:
  results: List[OrchestratorResult] = []
  for source in sources:
    results.append(
      parseOne(
        source=source,
        outputDir=outputDir,
        mineruAdapter=mineruAdapter,
        paddleAdapter=paddleAdapter,
      )
    )
  return results


def _parseWithMineru(*, source: str, outputDir: Path, mineru: MinerUV4Adapter) -> output_contract.OutputPaths:
  if source.startswith("http"):
    return mineru.extractFromUrl(url=source, outputDir=outputDir)
  return mineru.extractFromLocalFiles(filePaths=[Path(source)], outputDir=outputDir)[0]


def _parseWithPaddle(*, source: str, outputDir: Path, paddle: PaddleOcrJobsAdapter) -> output_contract.OutputPaths:
  if source.startswith("http"):
    return paddle.extractFromUrl(url=source, outputDir=outputDir)
  return paddle.extractFromFile(filePath=Path(source), outputDir=outputDir)


def _isPaddleOcrSupportedSource(source: str) -> bool:
  suffix = _guessSuffix(source)
  if suffix in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
    return True
  return False


def _guessSuffix(source: str) -> str:
  if source.startswith("http"):
    parsed = urlparse(source)
    return Path(parsed.path).suffix.lower()
  return Path(source).suffix.lower()

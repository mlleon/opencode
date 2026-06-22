from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, TypedDict, TypeAlias, Union


OUTPUT_SUBDIR = "document_parser_output"

NORMALIZED_DIRNAME = "normalized"
RAW_DIRNAME = "raw"

MINERU_RAW_DIRNAME = "mineru"
PADDLEOCR_RAW_DIRNAME = "paddleocr"

NORMALIZED_MARKDOWN_FILENAME = "document.md"
NORMALIZED_JSON_FILENAME = "document.json"
NORMALIZED_IMAGES_DIRNAME = "images"


DEGRADED_OCR_FALLBACK = "DEGRADED_OCR_FALLBACK"


JsonValue: TypeAlias = Union[
  None,
  bool,
  int,
  float,
  str,
  List["JsonValue"],
  Dict[str, "JsonValue"],
]


class EnvelopeMeta(TypedDict):
  input: str
  backend: str
  timestamp: str
  fallback: bool
  warnings: List[str]


class PageEnvelope(TypedDict, total=False):
  number: int
  markdown: str
  extras: Dict[str, JsonValue]


class NormalizedEnvelope(TypedDict):
  meta: EnvelopeMeta
  markdown: str
  pages: Optional[List[PageEnvelope]]
  artifacts: List[str]
  extras: Dict[str, JsonValue]


@dataclass(frozen=True)
class OutputPaths:
  documentRoot: Path
  normalizedDir: Path
  normalizedMarkdownPath: Path
  normalizedJsonPath: Path
  normalizedImagesDir: Path
  rawMineruDir: Path
  rawPaddleocrDir: Path


def get_output_root(output_dir: Path) -> Path:
  return output_dir / OUTPUT_SUBDIR


def get_document_root(*, output_dir: Path, stem: str) -> Path:
  return get_output_root(output_dir) / stem


def get_normalized_dir(*, output_dir: Path, stem: str) -> Path:
  return get_document_root(output_dir=output_dir, stem=stem) / NORMALIZED_DIRNAME


def get_raw_dir(*, output_dir: Path, stem: str) -> Path:
  return get_document_root(output_dir=output_dir, stem=stem) / RAW_DIRNAME


def get_raw_mineru_dir(*, output_dir: Path, stem: str) -> Path:
  return get_raw_dir(output_dir=output_dir, stem=stem) / MINERU_RAW_DIRNAME


def get_raw_paddleocr_dir(*, output_dir: Path, stem: str) -> Path:
  return get_raw_dir(output_dir=output_dir, stem=stem) / PADDLEOCR_RAW_DIRNAME


def get_normalized_markdown_path(*, output_dir: Path, stem: str) -> Path:
  return get_normalized_dir(output_dir=output_dir, stem=stem) / NORMALIZED_MARKDOWN_FILENAME


def get_normalized_json_path(*, output_dir: Path, stem: str) -> Path:
  return get_normalized_dir(output_dir=output_dir, stem=stem) / NORMALIZED_JSON_FILENAME


def get_normalized_images_dir(*, output_dir: Path, stem: str) -> Path:
  return get_normalized_dir(output_dir=output_dir, stem=stem) / NORMALIZED_IMAGES_DIRNAME


def get_output_paths(*, output_dir: Path, stem: str) -> OutputPaths:
  document_root = get_document_root(output_dir=output_dir, stem=stem)
  normalized_dir = document_root / NORMALIZED_DIRNAME

  return OutputPaths(
    documentRoot=document_root,
    normalizedDir=normalized_dir,
    normalizedMarkdownPath=normalized_dir / NORMALIZED_MARKDOWN_FILENAME,
    normalizedJsonPath=normalized_dir / NORMALIZED_JSON_FILENAME,
    normalizedImagesDir=normalized_dir / NORMALIZED_IMAGES_DIRNAME,
    rawMineruDir=document_root / RAW_DIRNAME / MINERU_RAW_DIRNAME,
    rawPaddleocrDir=document_root / RAW_DIRNAME / PADDLEOCR_RAW_DIRNAME,
  )


def build_artifacts_manifest(*, output_dir: Path, stem: str) -> List[str]:
  paths = get_output_paths(output_dir=output_dir, stem=stem)

  artifacts = [
    paths.normalizedMarkdownPath,
    paths.normalizedJsonPath,
    paths.normalizedImagesDir,
    paths.rawMineruDir,
    paths.rawPaddleocrDir,
  ]
  return [_to_output_relative_path(output_dir=output_dir, path=p) for p in artifacts]


def build_normalized_envelope(
  *,
  output_dir: Path,
  stem: str,
  input_source: str,
  backend: str,
  markdown: str,
  fallback: bool,
  warnings: List[str],
  pages: Optional[List[PageEnvelope]],
  extras: Dict[str, JsonValue],
  parseRequest: Optional[Dict[str, JsonValue]] = None,
  parseResult: Optional[Dict[str, JsonValue]] = None,
) -> NormalizedEnvelope:
  validate_offline_reproducible(markdown)
  envelopeExtras = dict(extras)
  if parseRequest:
    envelopeExtras["parseRequest"] = dict(parseRequest)
  if parseResult:
    envelopeExtras["parseResult"] = dict(parseResult)

  return {
    "meta": {
      "input": input_source,
      "backend": backend,
      "timestamp": _utc_timestamp(),
      "fallback": fallback,
      "warnings": list(warnings),
    },
    "markdown": markdown,
    "pages": pages,
    "artifacts": build_artifacts_manifest(output_dir=output_dir, stem=stem),
    "extras": envelopeExtras,
  }


_REMOTE_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)")


def find_remote_image_links(markdown: str) -> List[str]:
  return [match.group(1) for match in _REMOTE_IMAGE_LINK_RE.finditer(markdown)]


def validate_offline_reproducible(markdown: str) -> None:
  remote_links = find_remote_image_links(markdown)
  if remote_links:
    raise ValueError(f"最终 Markdown 包含远程图片链接: {remote_links[0]}")


def _to_output_relative_path(*, output_dir: Path, path: Path) -> str:
  return path.relative_to(output_dir).as_posix()


def _utc_timestamp() -> str:
  return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

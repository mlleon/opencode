#!/usr/bin/env python3
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
  projectRoot: Path
  memorySourceRoot: Path
  rawRoot: Path
  assetsRoot: Path
  stagingRoot: Path


@dataclass(frozen=True)
class TranscriptPaths:
  workRoot: Path
  rawDir: Path
  normalizedDir: Path
  analysisDir: Path
  structuredDir: Path
  transcriptTxt: Path
  transcriptJson: Path
  transcriptSrt: Path
  normalizedJson: Path
  normalizedMarkdown: Path
  segmentsJson: Path
  classificationJson: Path
  analysisJson: Path
  assistJson: Path
  reviewDir: Path
  structuredMarkdown: Path


def get_project_paths(project_root: Path) -> ProjectPaths:
  root = project_root.resolve()
  memory_source = root / "memory-source"
  return ProjectPaths(
    projectRoot=root,
    memorySourceRoot=memory_source,
    rawRoot=memory_source / "raw",
    assetsRoot=memory_source / "assets",
    stagingRoot=root / ".cache" / "transcribe-video",
  )


def make_slug(value: str, fallback: str = "transcript") -> str:
  cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip())
  cleaned = re.sub(r"-+", "-", cleaned).strip("-_")
  return cleaned[:80] or fallback


def make_work_id(source_path: Path) -> str:
  resolved = str(source_path.resolve())
  digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
  return f"{make_slug(source_path.stem)}-{digest}"


def get_transcript_paths(project_root: Path, source_path: Path, work_id: str | None = None) -> TranscriptPaths:
  project_paths = get_project_paths(project_root)
  actual_work_id = work_id or make_work_id(source_path)
  work_root = project_paths.stagingRoot / actual_work_id
  raw_dir = work_root / "raw"
  normalized_dir = work_root / "normalized"
  analysis_dir = work_root / "analysis"
  structured_dir = work_root / "structured"
  return TranscriptPaths(
    workRoot=work_root,
    rawDir=raw_dir,
    normalizedDir=normalized_dir,
    analysisDir=analysis_dir,
    structuredDir=structured_dir,
    transcriptTxt=raw_dir / "transcript.txt",
    transcriptJson=raw_dir / "transcript.json",
    transcriptSrt=raw_dir / "transcript.srt",
    normalizedJson=normalized_dir / "transcript.normalized.json",
    normalizedMarkdown=normalized_dir / "transcript.normalized.md",
    segmentsJson=analysis_dir / "segments.json",
    classificationJson=analysis_dir / "classification.json",
    analysisJson=analysis_dir / "analysis.json",
    assistJson=analysis_dir / "assist.json",
    reviewDir=work_root / "review",
    structuredMarkdown=structured_dir / "document.md",
  )


def get_final_raw_path(project_root: Path, final_stem: str) -> Path:
  return get_project_paths(project_root).rawRoot / "03-transcripts" / f"{final_stem}.md"


def get_final_assets_dir(project_root: Path, final_stem: str) -> Path:
  return get_project_paths(project_root).assetsRoot / "raw" / "transcripts" / final_stem


def ensure_parent(path: Path) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
  ensure_parent(path)
  tmp_path = path.with_name(path.name + ".tmp")
  tmp_path.write_text(content, encoding="utf-8")
  tmp_path.replace(path)

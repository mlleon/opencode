#!/usr/bin/env python3
import json
import re
from pathlib import Path

try:
  from paths import get_project_paths
  from taxonomy import load_taxonomy
except ImportError:
  from .paths import get_project_paths
  from .taxonomy import load_taxonomy


FORBIDDEN_RAW_SUFFIXES = {
  ".json", ".jsonl", ".txt", ".srt", ".vtt", ".mp4", ".mov", ".mkv", ".mp3", ".wav",
  ".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".zip", ".tmp", ".part", ".pyc",
}


def has_agent_instruction_file(path: Path) -> bool:
  return (path / "CLAUDE.md").exists() or (path / "AGENTS.md").exists()


def validate_project_structure(project_root: Path) -> list[str]:
  errors: list[str] = []
  paths = get_project_paths(project_root)
  if not paths.memorySourceRoot.exists():
    errors.append("memory-source 不存在")
  if not has_agent_instruction_file(paths.projectRoot):
    errors.append("projectRoot 下缺少 CLAUDE.md 或 AGENTS.md")
  if paths.memorySourceRoot.exists() and not has_agent_instruction_file(paths.memorySourceRoot):
    errors.append("memory-source 下缺少 CLAUDE.md 或 AGENTS.md")
  if not paths.rawRoot.exists():
    errors.append("memory-source/raw 不存在")
  if not paths.assetsRoot.exists():
    errors.append("memory-source/assets 不存在")
  return errors


def _parse_frontmatter(content: str) -> dict[str, str]:
  if not content.startswith("---\n"):
    return {}
  end = content.find("\n---", 4)
  if end < 0:
    return {}
  frontmatter = content[4:end]
  result: dict[str, str] = {}
  for line in frontmatter.splitlines():
    if ":" not in line or line.startswith(" "):
      continue
    key, value = line.split(":", 1)
    result[key.strip()] = value.strip().strip('"')
  return result


def validate_transcript_outputs(project_root: Path) -> list[str]:
  errors = validate_project_structure(project_root)
  paths = get_project_paths(project_root)
  raw_transcripts = paths.rawRoot / "03-transcripts"
  taxonomy = load_taxonomy()
  if not raw_transcripts.exists():
    return errors

  for file_path in raw_transcripts.rglob("*"):
    if file_path.is_dir():
      continue
    if file_path.suffix.lower() != ".md":
      errors.append(f"raw/03-transcripts 只能包含 Markdown: {file_path}")
      continue
    content = file_path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(content)
    if frontmatter.get("source_type") != "transcript":
      errors.append(f"缺少 source_type: transcript: {file_path}")
    if frontmatter.get("review_status") != "pending":
      errors.append(f"review_status 必须为 pending: {file_path}")
    primary = frontmatter.get("primary_domain")
    if primary not in taxonomy.domains:
      errors.append(f"primary_domain 非法: {file_path}")
    if not re.search(r"\d{2}:\d{2}", content):
      errors.append(f"转录 Markdown 缺少时间戳: {file_path}")

  raw_files = paths.rawRoot.rglob("*") if paths.rawRoot.exists() else []
  for file_path in raw_files:
    if file_path.is_dir():
      if file_path.name == "__pycache__":
        errors.append(f"raw 中禁止 __pycache__: {file_path}")
      continue
    if file_path.suffix.lower() in FORBIDDEN_RAW_SUFFIXES:
      errors.append(f"raw 中禁止过程/二进制文件: {file_path}")
  return errors


def validate_or_raise(project_root: Path) -> None:
  errors = validate_transcript_outputs(project_root)
  if errors:
    raise ValueError("\n".join(errors))


def write_validation_report(project_root: Path, output_path: Path) -> dict[str, object]:
  errors = validate_transcript_outputs(project_root)
  report = {"ok": not errors, "errors": errors}
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
  return report

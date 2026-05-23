#!/usr/bin/env python3
import shutil
from pathlib import Path

try:
  from paths import atomic_write_text, get_final_assets_dir, get_final_raw_path, make_slug
except ImportError:
  from .paths import atomic_write_text, get_final_assets_dir, get_final_raw_path, make_slug


def resolve_final_stem(source_path: Path, explicit_stem: str | None = None) -> str:
  if explicit_stem:
    return make_slug(explicit_stem)
  return make_slug(source_path.stem)


def copy_if_exists(source: Path, target: Path) -> None:
  if not source.exists():
    return
  target.parent.mkdir(parents=True, exist_ok=True)
  tmp_path = target.with_name(target.name + ".tmp")
  shutil.copy2(source, tmp_path)
  tmp_path.replace(target)


def postprocess_to_memory_source(
  project_root: Path,
  source_path: Path,
  structured_markdown_path: Path,
  support_files: list[Path],
  final_stem: str | None = None,
) -> dict[str, str]:
  actual_stem = resolve_final_stem(source_path, final_stem)
  final_raw_path = get_final_raw_path(project_root, actual_stem)
  final_assets_dir = get_final_assets_dir(project_root, actual_stem)

  markdown = structured_markdown_path.read_text(encoding="utf-8")
  atomic_write_text(final_raw_path, markdown)

  for file_path in support_files:
    if file_path.exists() and file_path.is_file():
      copy_if_exists(file_path, final_assets_dir / file_path.name)

  return {
    "finalStem": actual_stem,
    "rawPath": str(final_raw_path),
    "assetsDir": str(final_assets_dir),
  }

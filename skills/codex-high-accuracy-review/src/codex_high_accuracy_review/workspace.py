"""准备 disposable workspace 中可被 Codex 读取的安全输入副本."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codex_high_accuracy_review import contract, staging

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspaceFiles:
    """已复制到 disposable workspace 的输入文件和安全 hash."""

    plan_path: Path
    draft_path: Path | None
    source_metadata_path: Path
    plan_sha256: str
    draft_sha256: str | None


def prepare_review_workspace(
    staged: staging.StagedReviewEnvironment,
) -> WorkspaceFiles:
    """复制 plan/draft 并写入 metadata-only source.json."""
    inputs_dir = staged.disposable_workspace / "inputs"
    metadata_path = (
        staged.disposable_workspace / contract.WORKSPACE_SOURCE_METADATA_PATH
    )
    inputs_dir.mkdir(parents=True)
    metadata_path.parent.mkdir(parents=True)

    plan_path = staged.disposable_workspace / contract.WORKSPACE_PLAN_PATH
    _ = shutil.copyfile(staged.plan_source_path, plan_path, follow_symlinks=False)
    draft_path = _copy_draft(staged)
    plan_sha256 = _sha256(staged.plan_source_path)
    draft_sha256 = (
        _sha256(staged.draft_source_path) if staged.draft_source_path else None
    )
    metadata = {
        "plan_source_path": str(staged.plan_source_path),
        "plan_sha256": plan_sha256,
        "draft_source_path": str(staged.draft_source_path)
        if staged.draft_source_path
        else None,
        "draft_sha256": draft_sha256,
    }
    _ = metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return WorkspaceFiles(
        plan_path=plan_path,
        draft_path=draft_path,
        source_metadata_path=metadata_path,
        plan_sha256=plan_sha256,
        draft_sha256=draft_sha256,
    )


def _copy_draft(staged: staging.StagedReviewEnvironment) -> Path | None:
    if staged.draft_source_path is None:
        return None
    draft_path = staged.disposable_workspace / contract.WORKSPACE_DRAFT_PATH
    _ = shutil.copyfile(staged.draft_source_path, draft_path, follow_symlinks=False)
    return draft_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ("WorkspaceFiles", "prepare_review_workspace")

"""捕获白名单全局 guardrail 路径的 baseline/final manifest."""

from __future__ import annotations

import hashlib
import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from codex_high_accuracy_review import contract

type ManifestType = Literal["baseline", "final"]

TRANSIENT_NAMES = frozenset(
    (
        ".pytest-source-roots",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "uv.lock",
    ),
)


class ManifestEntry(TypedDict):
    """manifest entry 的固定字段集合."""

    path: str
    exists: bool
    kind: str
    mode: str
    sha256: str


class ManifestDocument(TypedDict):
    """manifest v1 JSON 形状, 只覆盖 contract 白名单路径."""

    schema: str
    manifest_type: str
    generated_at: str
    approved_path_patterns: list[str]
    entries: list[ManifestEntry]


def sibling_manifest_path(receipt_path: Path) -> Path:
    """为 wrapper receipt 生成同目录 manifest 路径."""
    return receipt_path.with_name(f"{receipt_path.stem}-global-manifest.json")


def write_global_manifest(path: Path, manifest_type: ManifestType) -> None:
    """写入限定白名单的 global file manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = capture_global_manifest(manifest_type)
    _ = path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def capture_global_manifest(manifest_type: ManifestType) -> ManifestDocument:
    """读取当前全局 guardrail 文件元数据, 不触碰项目业务源码."""
    return ManifestDocument(
        schema=contract.MANIFEST_SCHEMA,
        manifest_type=manifest_type,
        generated_at=_utc_timestamp(),
        approved_path_patterns=list(contract.APPROVED_GLOBAL_PATH_PATTERNS),
        entries=[_entry_for(path) for path in _approved_paths()],
    )


def _approved_paths() -> tuple[Path, ...]:
    claude_rule = Path(contract.APPROVED_GLOBAL_PATH_PATTERNS[0])
    installed_shim = Path(contract.APPROVED_GLOBAL_PATH_PATTERNS[1])
    source_tree = Path(contract.SOURCE_TREE_ROOT)
    tree_paths = (
        _walk_source_tree(source_tree) if source_tree.exists() else (source_tree,)
    )
    return (claude_rule, installed_shim, *tree_paths)


def _walk_source_tree(source_tree: Path) -> tuple[Path, ...]:
    paths = [source_tree]
    for root, dir_names, file_names in source_tree.walk():
        dir_names[:] = sorted(name for name in dir_names if name not in TRANSIENT_NAMES)
        paths.extend(root / name for name in dir_names)
        paths.extend(
            root / name for name in sorted(file_names) if name not in TRANSIENT_NAMES
        )
    return tuple(paths)


def _entry_for(path: Path) -> ManifestEntry:
    if not path.exists() and not path.is_symlink():
        return ManifestEntry(
            path=str(path),
            exists=False,
            kind="missing",
            mode="",
            sha256="",
        )

    path_stat = path.lstat()
    return ManifestEntry(
        path=str(path),
        exists=True,
        kind=_kind_for(path_stat.st_mode),
        mode=oct(stat.S_IMODE(path_stat.st_mode)),
        sha256=_sha256_for(path, path_stat.st_mode),
    )


def _kind_for(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "other"


def _sha256_for(path: Path, mode: int) -> str:
    if stat.S_ISREG(mode):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if stat.S_ISLNK(mode):
        return hashlib.sha256(str(path.readlink()).encode()).hexdigest()
    return ""


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


__all__ = (
    "ManifestDocument",
    "ManifestEntry",
    "ManifestType",
    "capture_global_manifest",
    "sibling_manifest_path",
    "write_global_manifest",
)

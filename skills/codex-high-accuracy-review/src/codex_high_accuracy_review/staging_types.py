"""Codex staging 层的 typed value objects 与安全原因枚举."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final, override

from codex_high_accuracy_review import contract

CONFIG_FILE_NAME: Final = "config.toml"
AUTH_FILE_NAME: Final = "auth.json"
DIRECTORY_MODE: Final = 0o700
SECRET_FILE_MODE: Final = 0o600
SECURE_UMASK: Final = 0o077


@unique
class PreflightRejectionReason(StrEnum):
    """staging fail-closed 时允许暴露的安全原因."""

    MISSING_CONFIG = "missing_config"
    MISSING_AUTH = "missing_auth"
    MISSING_SOURCE_HOME = "missing_source_home"
    MISSING_INPUT = "missing_input"
    NOT_DIRECTORY = "not_directory"
    NOT_REGULAR_FILE = "not_regular_file"
    PATH_TRAVERSAL = "path_traversal"
    SYMLINKED_PATH = "symlinked_path"
    TEMP_SOURCE_PATH = "temp_source_path"
    OUTSIDE_PLAN_DIR = "outside_plan_dir"
    OUTSIDE_DRAFT_DIR = "outside_draft_dir"
    UNSAFE_TEMP_ROOT = "unsafe_temp_root"


@dataclass(frozen=True, slots=True)
class PreflightRejectedError(Exception):
    """staging 前置检查失败, 且只携带 metadata-only 安全原因."""

    reason: PreflightRejectionReason
    path: Path | None = None

    @override
    def __str__(self) -> str:
        """返回 safe reason, 不包含 auth/prompt/output 原文."""
        if self.path is None:
            return self.reason.value
        return f"{self.reason.value}: {self.path}"


@dataclass(frozen=True, slots=True)
class StagingRequest:
    """一次 plan-only 复审需要 canonicalize 的 source 输入."""

    project_root: Path
    plan: Path
    draft: Path | None = None
    temp_root: Path = Path(contract.DISPOSABLE_TEMP_ROOT)


@dataclass(frozen=True, slots=True)
class SourceCodexHome:
    """已解析并验证过的 source Codex home."""

    source_codex_home: Path
    source_config_path: Path
    source_auth_path: Path
    config_toml: str


@dataclass(frozen=True, slots=True)
class CanonicalReviewInputs:
    """已通过 realpath 和目录边界检查的 source 输入."""

    project_root: Path
    plan_source_path: Path
    draft_source_path: Path | None


@dataclass(frozen=True, slots=True)
class StagedReviewEnvironment:
    """复制 secret 后可传给后续 Codex command 层的 staging 结果."""

    source_codex_home: Path
    source_config_path: Path
    source_auth_path: Path
    config_toml: str
    project_root: Path
    plan_source_path: Path
    draft_source_path: Path | None
    disposable_workspace: Path
    disposable_codex_home: Path
    child_codex_home_env: str

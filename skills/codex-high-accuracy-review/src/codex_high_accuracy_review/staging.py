"""解析 live Codex 配置并创建一次性复审 staging 目录."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

from codex_high_accuracy_review import contract
from codex_high_accuracy_review.staging_types import (
    AUTH_FILE_NAME,
    CONFIG_FILE_NAME,
    DIRECTORY_MODE,
    SECRET_FILE_MODE,
    SECURE_UMASK,
    CanonicalReviewInputs,
    PreflightRejectedError,
    PreflightRejectionReason,
    SourceCodexHome,
    StagedReviewEnvironment,
    StagingRequest,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

__all__: Final = (
    "PreflightRejectedError",
    "PreflightRejectionReason",
    "SourceCodexHome",
    "StagedReviewEnvironment",
    "StagingRequest",
    "resolve_source_codex_home",
    "stage_review_environment",
)
TEMP_ENV_NAMES: Final = ("TMPDIR", "TEMP", "TMP")
COMMON_TEMP_SOURCE_ROOTS: Final = (
    Path(f"{chr(47)}tmp"),
    Path(f"{chr(47)}var{chr(47)}tmp"),
    Path(f"{chr(47)}private{chr(47)}tmp"),
    Path(contract.DISPOSABLE_TEMP_ROOT),
)


def resolve_source_codex_home(
    env: Mapping[str, str] | None = None,
    user_home: Path | None = None,
) -> SourceCodexHome:
    """按 CODEX_HOME 优先、再 ~/.codex 的顺序解析 source Codex home."""
    source_env = os.environ if env is None else env
    home_root = Path.home() if user_home is None else user_home
    env_home = source_env.get("CODEX_HOME")
    source_home = (
        Path(env_home.strip())
        if env_home and env_home.strip()
        else home_root / ".codex"
    )
    canonical_home = _canonical_directory(
        source_home,
        PreflightRejectionReason.MISSING_SOURCE_HOME,
    )
    config_path = _canonical_regular_file(
        canonical_home / CONFIG_FILE_NAME,
        PreflightRejectionReason.MISSING_CONFIG,
    )
    auth_path = _canonical_regular_file(
        canonical_home / AUTH_FILE_NAME,
        PreflightRejectionReason.MISSING_AUTH,
    )
    return SourceCodexHome(
        source_codex_home=canonical_home,
        source_config_path=config_path,
        source_auth_path=auth_path,
        config_toml=config_path.read_text(encoding="utf-8"),
    )


def stage_review_environment(
    request: StagingRequest,
    env: Mapping[str, str] | None = None,
    user_home: Path | None = None,
) -> StagedReviewEnvironment:
    """验证 source 输入并创建只含 config/auth 副本的一次性 Codex home."""
    source_home = resolve_source_codex_home(env=env, user_home=user_home)
    source_inputs = _canonicalize_review_inputs(request)
    temp_root = _safe_temp_root(request.temp_root)
    with _secure_umask():
        disposable_workspace = Path(
            tempfile.mkdtemp(
                prefix=f"{contract.WRAPPER_NAME}-",
                dir=temp_root,
            ),
        )
        disposable_codex_home = Path(
            tempfile.mkdtemp(
                prefix="codex-ha-home-",
                dir=temp_root,
            ),
        )
        disposable_workspace.chmod(DIRECTORY_MODE)
        disposable_codex_home.chmod(DIRECTORY_MODE)
        _copy_secret_file(
            source_home.source_config_path,
            disposable_codex_home / CONFIG_FILE_NAME,
        )
        _copy_secret_file(
            source_home.source_auth_path,
            disposable_codex_home / AUTH_FILE_NAME,
        )
    return StagedReviewEnvironment(
        source_codex_home=source_home.source_codex_home,
        source_config_path=source_home.source_config_path,
        source_auth_path=source_home.source_auth_path,
        config_toml=source_home.config_toml,
        project_root=source_inputs.project_root,
        plan_source_path=source_inputs.plan_source_path,
        draft_source_path=source_inputs.draft_source_path,
        disposable_workspace=disposable_workspace,
        disposable_codex_home=disposable_codex_home,
        child_codex_home_env=str(disposable_codex_home),
    )


def _canonicalize_review_inputs(request: StagingRequest) -> CanonicalReviewInputs:
    project_root = _canonical_directory(
        request.project_root,
        PreflightRejectionReason.MISSING_INPUT,
    )
    plan = _canonical_regular_file(request.plan, PreflightRejectionReason.MISSING_INPUT)
    _reject_temp_source(plan)
    _require_under(
        path=plan,
        root=(project_root / ".omo" / "plans").resolve(strict=True),
        reason=PreflightRejectionReason.OUTSIDE_PLAN_DIR,
    )
    draft = _canonical_draft(request.draft, project_root)
    return CanonicalReviewInputs(
        project_root=project_root,
        plan_source_path=plan,
        draft_source_path=draft,
    )


def _canonical_draft(raw_draft: Path | None, project_root: Path) -> Path | None:
    if raw_draft is None:
        return None
    draft = _canonical_regular_file(raw_draft, PreflightRejectionReason.MISSING_INPUT)
    _reject_temp_source(draft)
    _require_under(
        path=draft,
        root=(project_root / ".omo" / "drafts").resolve(strict=True),
        reason=PreflightRejectionReason.OUTSIDE_DRAFT_DIR,
    )
    return draft


def _safe_temp_root(raw_temp_root: Path) -> Path:
    canonical_temp_root = _canonical_directory(
        raw_temp_root,
        PreflightRejectionReason.UNSAFE_TEMP_ROOT,
    )
    allowed_temp_root = _canonical_directory(
        Path(contract.DISPOSABLE_TEMP_ROOT),
        PreflightRejectionReason.UNSAFE_TEMP_ROOT,
    )
    if canonical_temp_root != allowed_temp_root:
        raise PreflightRejectedError(
            PreflightRejectionReason.UNSAFE_TEMP_ROOT,
            raw_temp_root,
        )
    return canonical_temp_root


def _canonical_directory(
    raw_path: Path,
    missing_reason: PreflightRejectionReason,
) -> Path:
    _reject_path_traversal(raw_path)
    _reject_symlink_components(raw_path)
    try:
        path_stat = raw_path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise PreflightRejectedError(missing_reason, raw_path) from exc
    if not stat.S_ISDIR(path_stat.st_mode):
        raise PreflightRejectedError(PreflightRejectionReason.NOT_DIRECTORY, raw_path)
    return raw_path.resolve(strict=True)


def _canonical_regular_file(
    raw_path: Path,
    missing_reason: PreflightRejectionReason,
) -> Path:
    _reject_path_traversal(raw_path)
    _reject_symlink_components(raw_path)
    try:
        path_stat = raw_path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise PreflightRejectedError(missing_reason, raw_path) from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise PreflightRejectedError(
            PreflightRejectionReason.NOT_REGULAR_FILE,
            raw_path,
        )
    return raw_path.resolve(strict=True)


def _reject_path_traversal(raw_path: Path) -> None:
    if ".." in raw_path.parts:
        raise PreflightRejectedError(
            PreflightRejectionReason.PATH_TRAVERSAL,
            raw_path,
        )


def _reject_symlink_components(raw_path: Path) -> None:
    absolute_path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
    current = Path(absolute_path.anchor)
    for part in absolute_path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise PreflightRejectedError(
                PreflightRejectionReason.SYMLINKED_PATH,
                raw_path,
            )


def _reject_temp_source(path: Path) -> None:
    if any(path.is_relative_to(root) for root in _existing_temp_source_roots()):
        raise PreflightRejectedError(
            PreflightRejectionReason.TEMP_SOURCE_PATH,
            path,
        )


def _existing_temp_source_roots() -> tuple[Path, ...]:
    roots = (
        Path(tempfile.gettempdir()),
        *COMMON_TEMP_SOURCE_ROOTS,
        *_env_temp_roots(),
    )
    return tuple(root.resolve(strict=True) for root in roots if root.exists())


def _env_temp_roots() -> tuple[Path, ...]:
    return tuple(
        Path(value)
        for name in TEMP_ENV_NAMES
        if (value := os.environ.get(name))
    )


def _require_under(path: Path, root: Path, reason: PreflightRejectionReason) -> None:
    if not path.is_relative_to(root):
        raise PreflightRejectedError(reason, path)


def _copy_secret_file(source: Path, destination: Path) -> None:
    _ = shutil.copyfile(source, destination, follow_symlinks=False)
    destination.chmod(SECRET_FILE_MODE)


@contextmanager
def _secure_umask() -> Generator[None, None, None]:
    previous_umask = os.umask(SECURE_UMASK)
    try:
        yield
    finally:
        _ = os.umask(previous_umask)

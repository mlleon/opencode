from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from codex_high_accuracy_review import contract, staging

if TYPE_CHECKING:
    from collections.abc import Generator

CONFIG_TEXT: Final = 'model_provider = "vsllm"\nmodel = "gpt-5.5-pro20x"\n'
AUTH_TEXT: Final = '{"token":"fixture"}\n'
SAFE_SOURCE_ROOT: Final = Path(__file__).resolve().parents[1] / ".pytest-source-roots"


@dataclass(frozen=True, slots=True)
class FixturePaths:
    codex_home: Path
    project_root: Path
    plan: Path
    draft: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_codex_home(path: Path, *, include_auth: bool = True) -> Path:
    path.mkdir(parents=True)
    _ = path.joinpath("config.toml").write_text(CONFIG_TEXT, encoding="utf-8")
    if include_auth:
        _ = path.joinpath("auth.json").write_text(AUTH_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def source_root(tmp_path: Path) -> Generator[Path, None, None]:
    root = SAFE_SOURCE_ROOT / tmp_path.name
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _make_fixture(tmp_path: Path, source_root: Path) -> FixturePaths:
    codex_home = _make_codex_home(tmp_path / "codex-home")
    project_root = source_root / "project"
    plan = project_root / ".omo" / "plans" / "review.md"
    draft = project_root / ".omo" / "drafts" / "blueprint.md"
    plan.parent.mkdir(parents=True)
    draft.parent.mkdir(parents=True)
    _ = plan.write_text("# Plan\n", encoding="utf-8")
    _ = draft.write_text("# Draft\n", encoding="utf-8")
    return FixturePaths(
        codex_home=codex_home,
        project_root=project_root,
        plan=plan,
        draft=draft,
    )


def _request(paths: FixturePaths) -> staging.StagingRequest:
    return staging.StagingRequest(
        project_root=paths.project_root,
        plan=paths.plan,
        draft=paths.draft,
    )


def _cleanup_staged(result: staging.StagedReviewEnvironment) -> None:
    shutil.rmtree(result.disposable_workspace, ignore_errors=True)
    shutil.rmtree(result.disposable_codex_home, ignore_errors=True)


def test_stage_review_environment_uses_codex_home_and_secure_modes(
    tmp_path: Path,
    source_root: Path,
) -> None:
    # Given: CODEX_HOME 和默认 ~/.codex 都存在, 且 source/project 输入真实存在.
    paths = _make_fixture(tmp_path, source_root)
    default_home = _make_codex_home(tmp_path / "home" / ".codex")
    config_path = paths.codex_home / "config.toml"
    auth_path = paths.codex_home / "auth.json"
    before = (
        config_path.stat().st_mtime_ns,
        auth_path.stat().st_mtime_ns,
        _sha256(config_path),
        _sha256(auth_path),
    )

    # When: staging 解析 live Codex home 并复制 disposable home.
    result = staging.stage_review_environment(
        _request(paths),
        env={"CODEX_HOME": str(paths.codex_home)},
        user_home=default_home.parent,
    )

    try:
        # Then: env CODEX_HOME 胜过默认 home, staging 副本 mode 安全.
        assert result.source_codex_home == paths.codex_home.resolve(strict=True)
        assert result.source_codex_home != default_home.resolve(strict=True)
        assert result.source_config_path == config_path.resolve(strict=True)
        assert result.source_auth_path == auth_path.resolve(strict=True)
        assert result.config_toml == CONFIG_TEXT
        assert result.project_root == paths.project_root.resolve(strict=True)
        assert result.plan_source_path == paths.plan.resolve(strict=True)
        assert result.draft_source_path == paths.draft.resolve(strict=True)
        assert result.disposable_workspace.parent == Path(contract.DISPOSABLE_TEMP_ROOT)
        assert result.disposable_codex_home.parent == Path(
            contract.DISPOSABLE_TEMP_ROOT,
        )
        assert result.child_codex_home_env == str(result.disposable_codex_home)
        assert stat.S_IMODE(result.disposable_workspace.stat().st_mode) == 0o700
        assert stat.S_IMODE(result.disposable_codex_home.stat().st_mode) == 0o700
        assert stat.S_IMODE(
            result.disposable_codex_home.joinpath("config.toml").stat().st_mode,
        ) == 0o600
        assert stat.S_IMODE(
            result.disposable_codex_home.joinpath("auth.json").stat().st_mode,
        ) == 0o600
        assert result.disposable_codex_home.joinpath("config.toml").is_file()
        assert result.disposable_codex_home.joinpath("auth.json").is_file()
        assert (
            config_path.stat().st_mtime_ns,
            auth_path.stat().st_mtime_ns,
            _sha256(config_path),
            _sha256(auth_path),
        ) == before
    finally:
        _cleanup_staged(result)


def test_resolve_source_codex_home_falls_back_to_default(tmp_path: Path) -> None:
    # Given: env 未设置 CODEX_HOME, 用户 home 下存在 ~/.codex.
    user_home = tmp_path / "home"
    default_home = _make_codex_home(user_home / ".codex")

    # When: 解析 source Codex home.
    result = staging.resolve_source_codex_home(env={}, user_home=user_home)

    # Then: 使用默认 ~/.codex, 并读取 config.toml.
    assert result.source_codex_home == default_home.resolve(strict=True)
    assert result.source_config_path == default_home.joinpath("config.toml").resolve(
        strict=True,
    )
    assert result.config_toml == CONFIG_TEXT


def test_missing_auth_rejects_before_staging(
    tmp_path: Path,
    source_root: Path,
) -> None:
    # Given: config.toml 存在但 auth.json 缺失.
    paths = _make_fixture(tmp_path, source_root)
    codex_home = _make_codex_home(tmp_path / "codex-without-auth", include_auth=False)

    # When: staging 尝试解析 source Codex home.
    with pytest.raises(staging.PreflightRejectedError) as exc_info:
        _ = staging.stage_review_environment(
            _request(paths),
            env={"CODEX_HOME": str(codex_home)},
            user_home=tmp_path,
        )

    # Then: 失败原因是 metadata-only 的 missing_auth, 且没有创建 disposable 目录.
    assert exc_info.value.reason is staging.PreflightRejectionReason.MISSING_AUTH


def test_temp_source_plan_rejects(tmp_path: Path, source_root: Path) -> None:
    # Given: plan 位于 /tmp/opencode 下, 代表过时临时 source 副本.
    temp_project = Path(
        tempfile.mkdtemp(
            prefix="pytest-codex-ha-temp-source-",
            dir=contract.DISPOSABLE_TEMP_ROOT,
        ),
    )
    try:
        paths = _make_fixture(tmp_path, source_root)
        plan = temp_project / ".omo" / "plans" / "review.md"
        draft = temp_project / ".omo" / "drafts" / "blueprint.md"
        plan.parent.mkdir(parents=True)
        draft.parent.mkdir(parents=True)
        _ = plan.write_text("# Temp plan\n", encoding="utf-8")
        _ = draft.write_text("# Temp draft\n", encoding="utf-8")

        # When: staging 收到 temp source plan.
        with pytest.raises(staging.PreflightRejectedError) as exc_info:
            _ = staging.stage_review_environment(
                staging.StagingRequest(
                    project_root=temp_project,
                    plan=plan,
                    draft=draft,
                ),
                env={"CODEX_HOME": str(paths.codex_home)},
                user_home=tmp_path,
            )

        # Then: fail-closed, 不允许用 /tmp/opencode source 输入启动复审.
        assert (
            exc_info.value.reason
            is staging.PreflightRejectionReason.TEMP_SOURCE_PATH
        )
    finally:
        shutil.rmtree(temp_project, ignore_errors=True)


def test_general_tmp_source_plan_rejects(
    tmp_path: Path,
    source_root: Path,
) -> None:
    # Given: plan 位于 /tmp 但不在 /tmp/opencode 下.
    temp_project = Path(
        tempfile.mkdtemp(
            prefix="pytest-codex-ha-general-temp-source-",
            dir="/tmp",
        ),
    )
    result: staging.StagedReviewEnvironment | None = None
    try:
        paths = _make_fixture(tmp_path, source_root)
        plan = temp_project / ".omo" / "plans" / "review.md"
        draft = temp_project / ".omo" / "drafts" / "blueprint.md"
        plan.parent.mkdir(parents=True)
        draft.parent.mkdir(parents=True)
        _ = plan.write_text("# General temp plan\n", encoding="utf-8")
        _ = draft.write_text("# General temp draft\n", encoding="utf-8")

        # When: staging 收到任意 /tmp source plan.
        with pytest.raises(staging.PreflightRejectedError) as exc_info:
            result = staging.stage_review_environment(
                staging.StagingRequest(
                    project_root=temp_project,
                    plan=plan,
                    draft=draft,
                ),
                env={"CODEX_HOME": str(paths.codex_home)},
                user_home=tmp_path,
            )

        # Then: 非 /tmp/opencode 的 temp source 同样 fail-closed.
        assert (
            exc_info.value.reason
            is staging.PreflightRejectionReason.TEMP_SOURCE_PATH
        )
    finally:
        if result is not None:
            _cleanup_staged(result)
        shutil.rmtree(temp_project, ignore_errors=True)


def test_path_traversal_draft_rejects(tmp_path: Path, source_root: Path) -> None:
    # Given: draft 参数包含 .., 即使 realpath 最终仍落在 drafts 目录.
    paths = _make_fixture(tmp_path, source_root)
    traversal_draft = (
        paths.project_root / ".omo" / "drafts" / ".." / "drafts" / "blueprint.md"
    )

    # When: staging canonicalize draft.
    with pytest.raises(staging.PreflightRejectedError) as exc_info:
        _ = staging.stage_review_environment(
            staging.StagingRequest(
                project_root=paths.project_root,
                plan=paths.plan,
                draft=traversal_draft,
            ),
            env={"CODEX_HOME": str(paths.codex_home)},
            user_home=tmp_path,
        )

    # Then: path traversal 被显式拒绝, 而不是 resolve 后静默接受.
    assert exc_info.value.reason is staging.PreflightRejectionReason.PATH_TRAVERSAL


def test_symlinked_plan_rejects(tmp_path: Path, source_root: Path) -> None:
    # Given: plan 参数是指向真实 plan 的 symlink.
    paths = _make_fixture(tmp_path, source_root)
    symlink_plan = paths.plan.parent / "symlink-plan.md"
    symlink_plan.symlink_to(paths.plan)

    # When: staging canonicalize symlinked plan.
    with pytest.raises(staging.PreflightRejectedError) as exc_info:
        _ = staging.stage_review_environment(
            staging.StagingRequest(
                project_root=paths.project_root,
                plan=symlink_plan,
                draft=paths.draft,
            ),
            env={"CODEX_HOME": str(paths.codex_home)},
            user_home=tmp_path,
        )

    # Then: symlink 输入被拒绝, 不跟随到真实文件.
    assert exc_info.value.reason is staging.PreflightRejectionReason.SYMLINKED_PATH


def test_unsafe_temp_root_rejects(tmp_path: Path, source_root: Path) -> None:
    # Given: staging temp root 不是真实 /tmp/opencode 目录.
    paths = _make_fixture(tmp_path, source_root)
    unsafe_temp_root = tmp_path / "unsafe-temp-root"

    # When: staging 尝试在 unsafe temp root 下创建 disposable 目录.
    with pytest.raises(staging.PreflightRejectedError) as exc_info:
        _ = staging.stage_review_environment(
            staging.StagingRequest(
                project_root=paths.project_root,
                plan=paths.plan,
                draft=paths.draft,
                temp_root=unsafe_temp_root,
            ),
            env={"CODEX_HOME": str(paths.codex_home)},
            user_home=tmp_path,
        )

    # Then: unsafe /tmp/opencode parent condition 被 fail-closed.
    assert exc_info.value.reason is staging.PreflightRejectionReason.UNSAFE_TEMP_ROOT

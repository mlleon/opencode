from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Final

from codex_high_accuracy_review import contract

HELP_MARKERS: Final[tuple[str, ...]] = (
    "Usage: codex-ha-review",
    "${CODEX_HOME:-~/.codex}/config.toml",
    "--plan",
    "--draft",
    "--dry-run",
)


def _command_env() -> dict[str, str]:
    env = os.environ.copy()
    shim_dir = str(Path(contract.INSTALLED_SHIM_PATH).parent)
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"
    return env


def _run(argv: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        argv,
        cwd=cwd,
        env=_command_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def _command_v() -> subprocess.CompletedProcess[str]:
    return _run(
        ("/bin/bash", "-lc", "command -v codex-ha-review"),
        Path(contract.SOURCE_TREE_ROOT),
    )


def _assert_tiny_delegating_shim(shim: Path, source: Path) -> None:
    if shim.is_symlink():
        assert shim.resolve(strict=True) == source.resolve(strict=True)
        return

    shim_text = shim.read_text(encoding="utf-8")
    logical_lines = tuple(
        line
        for line in shim_text.splitlines()
        if line.strip() and not line.startswith("#")
    )
    assert len(logical_lines) <= 4
    assert "exec" in shim_text
    assert str(source) in shim_text
    assert "codex_high_accuracy_review.command_gate" not in shim_text
    assert "stage_review_environment" not in shim_text


def test_source_script_exists_and_global_command_resolves_to_shim() -> None:
    # Given: Todo 5 freezes the source executable and installed shim paths in contract.
    source = Path(contract.WRAPPER_SOURCE_PATH)
    shim = Path(contract.INSTALLED_SHIM_PATH)

    # When: the installed command is resolved through the intended user PATH.
    command_lookup = _command_v()

    # Then: both paths exist, source is executable, and command -v sees the shim.
    assert source.is_file()
    assert os.access(source, os.X_OK)
    assert shim.exists() or shim.is_symlink()
    assert command_lookup.returncode == 0
    assert command_lookup.stdout.strip() == str(shim)
    assert command_lookup.stderr == ""
    _assert_tiny_delegating_shim(shim, source)


def test_source_script_delegates_cli_logic_to_typechecked_module() -> None:
    # Given: executable bin files are outside the project-level basedpyright include.
    source_text = Path(contract.WRAPPER_SOURCE_PATH).read_text(encoding="utf-8")

    # When: checking where CLI parsing logic lives.
    # Then: source script only bootstraps sys.path and calls the src-owned typed CLI.
    assert "from codex_high_accuracy_review.cli import main" in source_text
    assert "ArgumentParser" not in source_text
    assert "ReviewRequest(" not in source_text


def test_global_shim_help_prints_usage_without_mutating_cwd(tmp_path: Path) -> None:
    # Given: help should be safe to run from an arbitrary source project.
    project_root = tmp_path / "project"
    project_root.mkdir()

    # When: the globally installed shim is asked for help.
    result = _run((contract.INSTALLED_SHIM_PATH, "--help"), project_root)

    # Then: wrapper usage is printed and the caller directory remains untouched.
    assert result.returncode == 0
    assert result.stderr == ""
    for marker in HELP_MARKERS:
        assert marker in result.stdout
    assert not tuple(project_root.iterdir())


def test_source_and_shim_help_match_when_invoked_directly(tmp_path: Path) -> None:
    # Given: the global shim must delegate instead of carrying a stale logic copy.
    source = Path(contract.WRAPPER_SOURCE_PATH)
    project_root = tmp_path / "project"
    project_root.mkdir()

    # When: help is read through both entry points.
    source_result = _run((str(source), "--help"), project_root)
    shim_result = _run((contract.INSTALLED_SHIM_PATH, "--help"), project_root)

    # Then: both paths expose the same wrapper usage and exit successfully.
    assert source_result.returncode == 0
    assert shim_result.returncode == 0
    assert source_result.stdout == shim_result.stdout
    assert source_result.stderr == ""
    assert shim_result.stderr == ""

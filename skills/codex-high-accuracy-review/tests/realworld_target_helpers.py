from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Final

from codex_high_accuracy_review import contract

PROJECT_ROOT_ENV: Final = "CODEX_HA_REVIEW_TEST_PROJECT_ROOT"
PROJECT_ROOT: Final = Path(
    os.environ.get(PROJECT_ROOT_ENV, str(Path.home() / "workspace" / "llm-broker")),
).expanduser()
PLAN_PATH: Final = PROJECT_ROOT / ".omo/plans/vsllm-realworld-diagnostics.md"
DRAFT_PATH: Final = PROJECT_ROOT / ".omo/drafts/vsllm-realworld-diagnostics.md"
CONFIG_PATH: Final = Path(
    os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
).expanduser() / "config.toml"
LIVE_TARGET_SKIP_REASON: Final = "live vsllm real-world target files are unavailable"
LIVE_TARGET_UNAVAILABLE: Final = (
    not PLAN_PATH.is_file() or not DRAFT_PATH.is_file() or not CONFIG_PATH.is_file()
)
FORBIDDEN_RECEIPT_TEXT: Final = (
    "Read only these copied files",
    "OKAY <short reason>",
    "REJECT <short reason>",
    "vsllm-openai/gpt-5.5-pro20x",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def receipt_string(path: Path, field_name: str) -> str:
    pattern = re.compile(rf'  "{re.escape(field_name)}": "([^"]*)"')
    match = pattern.search(receipt_text(path))
    if match is None:
        raise AssertionError
    return match.group(1)


def wrapper_env(extra_path: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(CONFIG_PATH.parent)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env


def run_wrapper(
    args: tuple[str, ...],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        (contract.WRAPPER_SOURCE_PATH, *args),
        cwd=PROJECT_ROOT,
        env=wrapper_env() if env is None else env,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_safe_receipt(receipt_path: Path) -> None:
    text = receipt_path.read_text(encoding="utf-8")
    for forbidden_text in FORBIDDEN_RECEIPT_TEXT:
        assert forbidden_text not in text


def assert_staging_cleaned(receipt_path: Path) -> None:
    workspace = Path(receipt_string(receipt_path, "disposable_workspace"))
    codex_home = Path(receipt_string(receipt_path, "disposable_codex_home"))
    assert not workspace.exists()
    assert not codex_home.exists()


def common_args(receipt_path: Path) -> tuple[str, ...]:
    return (
        "--project-root",
        str(PROJECT_ROOT),
        "--plan",
        str(PLAN_PATH),
        "--draft",
        str(DRAFT_PATH),
        "--receipt-out",
        str(receipt_path),
    )

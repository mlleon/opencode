"""Codex 高精度复审 wrapper 的 typed CLI 入口."""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from codex_high_accuracy_review import contract
from codex_high_accuracy_review.runtime import ReviewRequest, run_review

if TYPE_CHECKING:
    from collections.abc import Sequence

HELP_TEXT: Final = (
    f"Usage: {contract.WRAPPER_NAME} --project-root <path> --plan <path> "
    "[--draft <path>] [--receipt-out <path>] [--dry-run]\n\n"
    "Codex high-accuracy plan review wrapper.\n\n"
    "Options:\n"
    "  --project-root <path>  Source project root containing .omo/plans "
    "and .omo/drafts.\n"
    "  --plan <path>          Live .omo/plans file to review.\n"
    "  --draft <path>         Optional live .omo/drafts file paired with "
    "the plan.\n"
    "  --receipt-out <path>   Optional metadata-only receipt output path.\n"
    "  --dry-run              Validate wrapper setup without spawning real Codex.\n"
    "  -h, --help             Show this usage.\n\n"
    f"Model source: {contract.MODEL_CONFIG_SOURCE}\n"
    f"Prompt mode: {contract.PROMPT_INPUT_MODE}\n"
    f"Source script: {contract.WRAPPER_SOURCE_PATH}\n"
)


class ParsedArgs(Namespace):
    """argparse 写入后的已知字段集合."""

    project_root: str
    plan: str
    draft: str | None
    receipt_out: str | None
    dry_run: bool

    def __init__(self) -> None:
        super().__init__()
        self.project_root = ""
        self.plan = ""
        self.draft = None
        self.receipt_out = None
        self.dry_run = False


@dataclass(frozen=True, slots=True)
class CliOptions:
    """从 argv 解析出的 wrapper 输入."""

    project_root: Path
    plan: Path
    draft: Path | None
    receipt_out: Path | None
    dry_run: bool


def main(argv: Sequence[str] | None = None) -> int:
    """运行 wrapper CLI 并返回进程退出码."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    if _wants_help(args):
        _ = sys.stdout.write(HELP_TEXT)
        return 0

    options = parse_cli_options(args)
    result = run_review(
        ReviewRequest(
            project_root=options.project_root,
            plan=options.plan,
            draft=options.draft,
            dry_run=options.dry_run,
            receipt_out=options.receipt_out,
        ),
    )
    manifest_suffix = (
        f" manifest={result.manifest_path}" if result.manifest_path else ""
    )
    status_line = f"status={result.status.value} receipt={result.receipt_path}"
    _ = sys.stdout.write(f"{status_line}{manifest_suffix}\n")
    return result.exit_code


def parse_cli_options(args: tuple[str, ...]) -> CliOptions:
    """把 argparse 边界结果转换成明确类型的 CLI options."""
    namespace = _build_parser().parse_args(args, namespace=ParsedArgs())
    return CliOptions(
        project_root=Path(namespace.project_root),
        plan=Path(namespace.plan),
        draft=Path(namespace.draft) if namespace.draft else None,
        receipt_out=Path(namespace.receipt_out) if namespace.receipt_out else None,
        dry_run=namespace.dry_run,
    )


def _wants_help(args: tuple[str, ...]) -> bool:
    return not args or any(arg in ("-h", "--help") for arg in args)


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog=contract.WRAPPER_NAME, add_help=False)
    _ = parser.add_argument("--project-root", required=True)
    _ = parser.add_argument("--plan", required=True)
    _ = parser.add_argument("--draft")
    _ = parser.add_argument("--receipt-out")
    _ = parser.add_argument("--dry-run", action="store_true")
    return parser


__all__ = ("HELP_TEXT", "CliOptions", "main", "parse_cli_options")

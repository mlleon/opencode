"""Codex exec 命令装配与内存决策解析层."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from codex_high_accuracy_review import contract

if TYPE_CHECKING:
    from collections.abc import Mapping

OKAY_MARKER: Final = "OKAY"
REJECT_MARKER: Final = "REJECT"
DECISION_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(OKAY|REJECT)(?:\s+.*)?$",
)
OKAY_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bOKAY\b")
REJECT_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bREJECT\b")
DECISION_BY_MARKER: Final[Mapping[str, contract.ReviewDecision]] = {
    OKAY_MARKER: contract.ReviewDecision.OKAY,
    REJECT_MARKER: contract.ReviewDecision.REJECT,
}


@dataclass(frozen=True, slots=True)
class ChildEnv:
    """Codex 子进程允许覆盖的环境变量集合."""

    codex_home: str

    def as_assignment(self) -> str:
        """返回 evidence/receipt 可持久化的 CODEX_HOME 赋值."""
        return f"CODEX_HOME={self.codex_home}"

    def with_base(self, base_env: Mapping[str, str]) -> Mapping[str, str]:
        """把 CODEX_HOME 覆盖合并到调用者提供的进程环境."""
        return {**base_env, "CODEX_HOME": self.codex_home}


@dataclass(frozen=True, slots=True)
class CodexExecCommand:
    """不包含 prompt 正文的 Codex exec 命令数据."""

    argv: tuple[str, ...]
    child_env: ChildEnv
    prompt_input_mode: str


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """内存中的模板渲染结果, 不应写入 receipt/evidence."""

    template_path: Path
    input_mode: str
    body: str


@dataclass(frozen=True, slots=True)
class ChildProcessResult:
    """Codex 子进程输出的内存快照."""

    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True, slots=True)
class CommandGateResult:
    """可持久化的 command/gate 决策元数据."""

    status: contract.ReceiptStatus
    review_decision: contract.ReviewDecision
    wrapper_exit_code: int
    codex_exit_code: int | None


@dataclass(frozen=True, slots=True)
class CodexExecRequest:
    """执行 Codex exec 所需的 command/gate 层输入."""

    workspace: Path
    disposable_codex_home: Path
    prompt: str


@dataclass(frozen=True, slots=True)
class CommandGateReceiptFields:
    """后续 receipt 层可安全持久化的 command/gate 字段."""

    argv_without_prompt: tuple[str, ...]
    child_codex_home_env: str
    prompt_input_mode: str
    wrapper_exit_code: int
    codex_exit_code: int | None
    review_decision: contract.ReviewDecision


def build_codex_exec_command(
    *,
    workspace: Path,
    disposable_codex_home: Path,
) -> CodexExecCommand:
    """构造固定的 config-driven Codex exec argv 与 CODEX_HOME 覆盖."""
    argv = (
        "codex",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "-s",
        "read-only",
        "-c",
        f'model_reasoning_effort="{contract.REASONING_EFFORT}"',
    )
    return CodexExecCommand(
        argv=argv,
        child_env=ChildEnv(codex_home=str(disposable_codex_home)),
        prompt_input_mode=contract.PROMPT_INPUT_MODE,
    )


def render_review_prompt() -> RenderedPrompt:
    """从 contract 固定路径读取复审 prompt 模板到内存."""
    template_path = Path(contract.PROMPT_TEMPLATE_PATH)
    return RenderedPrompt(
        template_path=template_path,
        input_mode=contract.PROMPT_INPUT_MODE,
        body=template_path.read_text(encoding="utf-8"),
    )


def wrapper_exit_code_for(
    *,
    status: contract.ReceiptStatus,
    review_decision: contract.ReviewDecision,
) -> int:
    """按计划固定的 status/review_decision 映射 wrapper exit code."""
    match status:
        case contract.ReceiptStatus.DRY_RUN:
            return 0
        case contract.ReceiptStatus.PREFLIGHT_REJECTED:
            return 4
        case contract.ReceiptStatus.CODEX_FAILED:
            return 5
        case contract.ReceiptStatus.WRAPPER_FAILED:
            return 6
        case contract.ReceiptStatus.EXECUTED:
            return _executed_exit_code_for(review_decision)


def parse_child_result(child_result: ChildProcessResult) -> CommandGateResult:
    """只用内存 stdout 与子进程退出码解析复审决策."""
    if child_result.exit_code != 0:
        return CommandGateResult(
            status=contract.ReceiptStatus.CODEX_FAILED,
            review_decision=contract.ReviewDecision.NOT_RUN,
            wrapper_exit_code=wrapper_exit_code_for(
                status=contract.ReceiptStatus.CODEX_FAILED,
                review_decision=contract.ReviewDecision.NOT_RUN,
            ),
            codex_exit_code=child_result.exit_code,
        )

    decision = _parse_stdout_decision(child_result.stdout)
    return CommandGateResult(
        status=contract.ReceiptStatus.EXECUTED,
        review_decision=decision,
        wrapper_exit_code=wrapper_exit_code_for(
            status=contract.ReceiptStatus.EXECUTED,
            review_decision=decision,
        ),
        codex_exit_code=child_result.exit_code,
    )


def execute_codex_exec(request: CodexExecRequest) -> CommandGateResult:
    """通过 stdin 运行 Codex exec, 并只返回安全决策元数据."""
    command = build_codex_exec_command(
        workspace=request.workspace,
        disposable_codex_home=request.disposable_codex_home,
    )
    try:
        completed_process = subprocess.run(  # noqa: S603
            command.argv,
            input=request.prompt,
            text=True,
            capture_output=True,
            check=False,
            env=command.child_env.with_base(os.environ),
        )
    except OSError:
        return CommandGateResult(
            status=contract.ReceiptStatus.WRAPPER_FAILED,
            review_decision=contract.ReviewDecision.NOT_RUN,
            wrapper_exit_code=wrapper_exit_code_for(
                status=contract.ReceiptStatus.WRAPPER_FAILED,
                review_decision=contract.ReviewDecision.NOT_RUN,
            ),
            codex_exit_code=None,
        )

    return parse_child_result(
        ChildProcessResult(
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
            exit_code=completed_process.returncode,
        ),
    )


def build_command_gate_receipt_fields(
    command: CodexExecCommand,
    result: CommandGateResult,
) -> CommandGateReceiptFields:
    """生成不含 prompt/stdout/stderr 正文的 receipt 字段."""
    return CommandGateReceiptFields(
        argv_without_prompt=command.argv,
        child_codex_home_env=command.child_env.as_assignment(),
        prompt_input_mode=command.prompt_input_mode,
        wrapper_exit_code=result.wrapper_exit_code,
        codex_exit_code=result.codex_exit_code,
        review_decision=result.review_decision,
    )


def _executed_exit_code_for(review_decision: contract.ReviewDecision) -> int:
    match review_decision:
        case contract.ReviewDecision.OKAY:
            return 0
        case contract.ReviewDecision.REJECT:
            return 2
        case contract.ReviewDecision.MALFORMED | contract.ReviewDecision.NOT_RUN:
            return 3


def _parse_stdout_decision(stdout: str) -> contract.ReviewDecision:
    final_line = _last_non_empty_stdout_line(stdout)
    if final_line is None:
        return contract.ReviewDecision.MALFORMED
    if _has_conflicting_markers(stdout):
        return contract.ReviewDecision.MALFORMED

    match_result = DECISION_LINE_PATTERN.fullmatch(final_line)
    if match_result is None:
        return contract.ReviewDecision.MALFORMED

    return DECISION_BY_MARKER.get(
        match_result.group(1),
        contract.ReviewDecision.MALFORMED,
    )


def _last_non_empty_stdout_line(stdout: str) -> str | None:
    lines = tuple(line for line in stdout.rstrip().splitlines() if line.strip())
    if not lines:
        return None
    return lines[-1].rstrip()


def _has_conflicting_markers(stdout: str) -> bool:
    return bool(OKAY_MARKER_PATTERN.search(stdout)) and bool(
        REJECT_MARKER_PATTERN.search(stdout),
    )


__all__ = (
    "ChildEnv",
    "ChildProcessResult",
    "CodexExecCommand",
    "CodexExecRequest",
    "CommandGateReceiptFields",
    "CommandGateResult",
    "RenderedPrompt",
    "build_codex_exec_command",
    "build_command_gate_receipt_fields",
    "execute_codex_exec",
    "parse_child_result",
    "render_review_prompt",
    "wrapper_exit_code_for",
)

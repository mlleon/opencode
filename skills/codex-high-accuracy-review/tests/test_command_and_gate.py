from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from typing import Final

import pytest

from codex_high_accuracy_review import command_gate, contract

FORBIDDEN_ARGV_TOKENS: Final[tuple[str, ...]] = (
    "-m",
    "--model",
    "--ignore-user-config",
    "--dangerously-bypass-approvals-and-sandbox",
    "vsllm-openai/gpt-5.5-pro20x",
)


def test_build_codex_exec_command_uses_safe_config_driven_argv(
    tmp_path: Path,
) -> None:
    # Given: Todo 3 只允许 config-driven Codex exec, 不允许 session model 覆盖.
    workspace = tmp_path / "workspace"
    disposable_home = tmp_path / "codex-home"

    # When: 构造 Codex 子进程命令数据.
    command = command_gate.build_codex_exec_command(
        workspace=workspace,
        disposable_codex_home=disposable_home,
    )

    # Then: argv 精确匹配计划, 且 prompt/env 与危险 flag 隔离.
    assert command.argv == (
        "codex",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "-s",
        "read-only",
        "-c",
        'model_reasoning_effort="xhigh"',
    )
    assert command.child_env.codex_home == str(disposable_home)
    assert command.child_env.as_assignment() == f"CODEX_HOME={disposable_home}"
    assert command.prompt_input_mode == contract.PROMPT_INPUT_MODE
    assert command.prompt_input_mode == "stdin"
    for forbidden_token in FORBIDDEN_ARGV_TOKENS:
        assert forbidden_token not in command.argv


def test_render_review_prompt_uses_fixed_template_and_stdin_mode() -> None:
    # Given: prompt 模板路径由 contract 固定.
    # When: 渲染复审 prompt.
    rendered = command_gate.render_review_prompt()

    # Then: prompt 来自固定模板, 只作为 stdin 输入在内存中传递.
    assert rendered.template_path == Path(contract.PROMPT_TEMPLATE_PATH)
    assert rendered.input_mode == contract.PROMPT_INPUT_MODE
    assert rendered.input_mode == "stdin"
    assert "inputs/plan.md" in rendered.body
    assert "inputs/draft.md" in rendered.body
    assert "OKAY" in rendered.body
    assert "REJECT" in rendered.body


@pytest.mark.parametrize(
    ("child_result", "expected_status", "expected_decision", "expected_exit"),
    [
        (
            command_gate.ChildProcessResult(
                stdout="notes are allowed before the final line\nOKAY approved\n",
                stderr="REJECT on stderr is ignored",
                exit_code=0,
            ),
            contract.ReceiptStatus.EXECUTED,
            contract.ReviewDecision.OKAY,
            0,
        ),
        (
            command_gate.ChildProcessResult(
                stdout="REJECT missing invariant\n",
                stderr="",
                exit_code=0,
            ),
            contract.ReceiptStatus.EXECUTED,
            contract.ReviewDecision.REJECT,
            2,
        ),
        (
            command_gate.ChildProcessResult(stdout="MAYBE\n", stderr="", exit_code=0),
            contract.ReceiptStatus.EXECUTED,
            contract.ReviewDecision.MALFORMED,
            3,
        ),
        (
            command_gate.ChildProcessResult(stdout="\n  \n", stderr="", exit_code=0),
            contract.ReceiptStatus.EXECUTED,
            contract.ReviewDecision.MALFORMED,
            3,
        ),
        (
            command_gate.ChildProcessResult(
                stdout="",
                stderr="OKAY stderr only",
                exit_code=0,
            ),
            contract.ReceiptStatus.EXECUTED,
            contract.ReviewDecision.MALFORMED,
            3,
        ),
        (
            command_gate.ChildProcessResult(
                stdout="OKAY would be ignored on child failure\n",
                stderr="provider failure body is memory-only",
                exit_code=7,
            ),
            contract.ReceiptStatus.CODEX_FAILED,
            contract.ReviewDecision.NOT_RUN,
            5,
        ),
    ],
)
def test_parse_child_result_maps_decisions_without_stderr_participation(
    child_result: command_gate.ChildProcessResult,
    expected_status: contract.ReceiptStatus,
    expected_decision: contract.ReviewDecision,
    expected_exit: int,
) -> None:
    # Given: 子进程 stdout/stderr 只在内存中交给 gate.
    # When: 解析复审决策.
    result = command_gate.parse_child_result(child_result)

    # Then: 只根据计划规则输出 metadata-safe gate 结果.
    assert result.status == expected_status
    assert result.review_decision == expected_decision
    assert result.wrapper_exit_code == expected_exit
    assert result.codex_exit_code == child_result.exit_code


@pytest.mark.parametrize(
    "stdout",
    [
        "REJECT first marker\nOKAY second marker\n",
        "OKAY approved but REJECT also appears\n",
        "vsllm-openai/gpt-5.5-pro20x\n",
    ],
)
def test_parse_child_result_marks_conflicts_and_session_model_text_malformed(
    stdout: str,
) -> None:
    # Given: stdout 包含冲突 marker 或历史错误 session model 字符串.
    child_result = command_gate.ChildProcessResult(
        stdout=stdout, stderr="", exit_code=0
    )

    # When: 解析 stdout 最终行.
    result = command_gate.parse_child_result(child_result)

    # Then: 不把这些输出当成可通过的 OKAY/REJECT 决策.
    assert result.status == contract.ReceiptStatus.EXECUTED
    assert result.review_decision == contract.ReviewDecision.MALFORMED
    assert result.wrapper_exit_code == 3


@pytest.mark.parametrize(
    ("status", "decision", "expected_exit"),
    [
        (contract.ReceiptStatus.DRY_RUN, contract.ReviewDecision.NOT_RUN, 0),
        (contract.ReceiptStatus.PREFLIGHT_REJECTED, contract.ReviewDecision.NOT_RUN, 4),
        (contract.ReceiptStatus.CODEX_FAILED, contract.ReviewDecision.NOT_RUN, 5),
        (contract.ReceiptStatus.WRAPPER_FAILED, contract.ReviewDecision.NOT_RUN, 6),
        (contract.ReceiptStatus.EXECUTED, contract.ReviewDecision.OKAY, 0),
        (contract.ReceiptStatus.EXECUTED, contract.ReviewDecision.REJECT, 2),
        (contract.ReceiptStatus.EXECUTED, contract.ReviewDecision.MALFORMED, 3),
    ],
)
def test_wrapper_exit_code_for_status_and_decision_is_fixed(
    status: contract.ReceiptStatus,
    decision: contract.ReviewDecision,
    expected_exit: int,
) -> None:
    # Given: plan 固定 wrapper exit-code contract.
    # When: 根据 status 和 review_decision 计算 wrapper exit code.
    wrapper_exit_code = command_gate.wrapper_exit_code_for(
        status=status,
        review_decision=decision,
    )

    # Then: 每个可执行状态都有确定映射.
    assert wrapper_exit_code == expected_exit


def test_execute_codex_exec_passes_prompt_on_stdin_and_codex_home_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: PATH 中只有测试注入的 fake codex, 它只记录安全布尔元数据.
    workspace = tmp_path / "workspace"
    disposable_home = tmp_path / "codex-home"
    workspace.mkdir()
    disposable_home.mkdir()
    report_path = tmp_path / "fake-codex-report.txt"
    fake_codex = tmp_path / "codex"
    _ = fake_codex.write_text(
        r"""#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from pathlib import Path
stdin_body = sys.stdin.read()
report = [
    "argv=" + repr(sys.argv[1:]),
    "codex_home=" + os.environ.get("CODEX_HOME", ""),
    "stdin_has_plan=" + str("inputs/plan.md" in stdin_body),
    "stdin_has_draft=" + str("inputs/draft.md" in stdin_body),
]
Path(os.environ["FAKE_CODEX_REPORT"]).write_text(
    "\n".join(report),
    encoding="utf-8",
)
sys.stdout.write(os.environ["FAKE_CODEX_STDOUT"])
sys.stderr.write(os.environ.get("FAKE_CODEX_STDERR", ""))
raise SystemExit(int(os.environ.get("FAKE_CODEX_EXIT", "0")))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_CODEX_REPORT", str(report_path))
    monkeypatch.setenv("FAKE_CODEX_STDOUT", "narrative\nOKAY approved\n")
    monkeypatch.setenv("FAKE_CODEX_STDERR", "stderr is not a decision\n")
    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")

    # When: command gate 执行 fake codex.
    rendered = command_gate.render_review_prompt()
    request = command_gate.CodexExecRequest(
        workspace=workspace,
        disposable_codex_home=disposable_home,
        prompt=rendered.body,
    )
    result = command_gate.execute_codex_exec(request)
    command = command_gate.build_codex_exec_command(
        workspace=workspace,
        disposable_codex_home=disposable_home,
    )

    # Then: prompt 走 stdin, child CODEX_HOME 指向 disposable home, argv 无 prompt.
    report_text = report_path.read_text(encoding="utf-8")
    assert "stdin_has_plan=True" in report_text
    assert "stdin_has_draft=True" in report_text
    assert f"codex_home={disposable_home}" in report_text
    assert repr(list(command.argv[1:])) in report_text
    assert rendered.body not in report_text
    assert result.status == contract.ReceiptStatus.EXECUTED
    assert result.review_decision == contract.ReviewDecision.OKAY
    assert result.wrapper_exit_code == 0
    assert result.codex_exit_code == 0


def test_command_gate_receipt_fields_are_metadata_only(tmp_path: Path) -> None:
    # Given: command + gate 结果需要交给后续 receipt 层持久化.
    command = command_gate.build_codex_exec_command(
        workspace=tmp_path / "workspace",
        disposable_codex_home=tmp_path / "codex-home",
    )
    result = command_gate.parse_child_result(
        command_gate.ChildProcessResult(
            stdout="OKAY approved\n",
            stderr="raw",
            exit_code=0,
        ),
    )

    # When: 生成 command/gate 可持久化字段.
    receipt_fields = command_gate.build_command_gate_receipt_fields(command, result)
    receipt_field_names = tuple(field.name for field in fields(receipt_fields))

    # Then: 只包含 metadata, 不包含 prompt/stdout/stderr/narrative 原文.
    assert receipt_field_names == (
        "argv_without_prompt",
        "child_codex_home_env",
        "prompt_input_mode",
        "wrapper_exit_code",
        "codex_exit_code",
        "review_decision",
    )
    for forbidden_field in contract.FORBIDDEN_RECEIPT_FIELDS:
        assert forbidden_field not in receipt_field_names
    assert receipt_fields.argv_without_prompt == command.argv
    assert (
        receipt_fields.child_codex_home_env == f"CODEX_HOME={tmp_path / 'codex-home'}"
    )
    assert receipt_fields.prompt_input_mode == "stdin"
    assert receipt_fields.wrapper_exit_code == 0
    assert receipt_fields.codex_exit_code == 0
    assert receipt_fields.review_decision == contract.ReviewDecision.OKAY

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from codex_high_accuracy_review import contract

EXPECTED_REQUIRED_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
    "schema",
    "status",
    "execution_mode",
    "review_type",
    "source_codex_home",
    "source_config_path",
    "source_auth_present",
    "resolved_model_provider",
    "resolved_model",
    "resolved_reasoning_effort",
    "project_root",
    "plan_source_path",
    "plan_sha256",
    "disposable_workspace",
    "disposable_codex_home",
    "child_codex_home_env",
    "argv_without_prompt",
    "prompt_template_path",
    "prompt_template_sha256",
    "prompt_input_mode",
    "started_at",
    "ended_at",
    "wrapper_exit_code",
    "review_decision",
)

EXPECTED_OPTIONAL_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
    "draft_source_path",
    "draft_sha256",
    "codex_exit_code",
    "rejection_reason",
    "codex_binary_path",
)

FORBIDDEN_RECEIPT_FIELD_FIXTURES: Final[tuple[str, ...]] = (
    "prompt",
    "prompt_body",
    "rendered_prompt",
    "prompt_argv",
    "stdout",
    "stderr",
    "codex_stdout",
    "codex_stderr",
    "codex_stdout_text",
    "codex_stderr_text",
    "auth_json",
    "auth_json_contents",
    "api_key",
    "api_token",
    "bearer_token",
    "model_output",
    "review_narrative",
    "raw_narrative",
    "provider_raw_error",
)


def test_fixed_contract_identity_when_loaded() -> None:
    # Given: 顶层任务固定了全局 wrapper 与 prompt 输入模式.
    # When: contract 模块被导入.
    # Then: 所有身份字段都不是自由裁量或 session 推断值.
    source_tree_root = Path(contract.__file__).resolve().parents[2]
    assert contract.WRAPPER_NAME == "codex-ha-review"
    assert str(source_tree_root) == contract.SOURCE_TREE_ROOT
    assert str(source_tree_root / "bin/codex-ha-review") == (
        contract.WRAPPER_SOURCE_PATH
    )
    assert str(Path.home() / ".local/bin/codex-ha-review") == (
        contract.INSTALLED_SHIM_PATH
    )
    assert str(source_tree_root / "templates/plan-review.txt") == (
        contract.PROMPT_TEMPLATE_PATH
    )
    assert contract.PROMPT_INPUT_MODE == "stdin"
    assert contract.MODEL_CONFIG_SOURCE == "${CODEX_HOME:-~/.codex}/config.toml"
    assert contract.REASONING_EFFORT == "xhigh"
    assert contract.REVIEW_TYPE == "plan_high_accuracy"
    assert contract.RECEIPT_SCHEMA == "codex_high_accuracy_review_receipt.v1"
    assert contract.UTC_TIMESTAMP_PATTERN == r"^\d{8}T\d{6}Z(?:-\d+)?$"


def test_enums_are_exact_when_serialized() -> None:
    # Given: 后续 receipt 只能序列化封闭状态与复审决策.
    # When: 从 contract 枚举列出可序列化值.
    # Then: 每个允许值都固定, 且没有别名.
    assert tuple(item.value for item in contract.ReceiptStatus) == (
        "dry_run",
        "executed",
        "preflight_rejected",
        "codex_failed",
        "wrapper_failed",
    )
    assert tuple(item.value for item in contract.ReviewDecision) == (
        "okay",
        "reject",
        "malformed",
        "not_run",
    )


def test_receipt_schema_is_metadata_only_when_fields_are_listed() -> None:
    # Given: receipt 只允许持久化元数据, 禁止原始复审材料.
    # When: 列出 required/optional schema 字段.
    # Then: 完整 schema 精确匹配, 并排除 prompt/output/auth 原文字段.
    assert contract.REQUIRED_RECEIPT_FIELDS == EXPECTED_REQUIRED_RECEIPT_FIELDS
    assert contract.OPTIONAL_RECEIPT_FIELDS == EXPECTED_OPTIONAL_RECEIPT_FIELDS
    assert contract.ALLOWED_RECEIPT_FIELDS == (
        EXPECTED_REQUIRED_RECEIPT_FIELDS + EXPECTED_OPTIONAL_RECEIPT_FIELDS
    )
    for forbidden_field in FORBIDDEN_RECEIPT_FIELD_FIXTURES:
        assert not contract.is_receipt_field_allowed(forbidden_field)
        assert forbidden_field not in contract.ALLOWED_RECEIPT_FIELDS


def test_manifest_schema_covers_only_approved_global_paths() -> None:
    # Given: baseline/final manifest 只覆盖用户自有全局 guardrail 路径.
    # When: 检查 manifest 路径规则.
    # Then: 项目源码、临时副本或 secret 路径都不能进入 manifest 范围.
    assert contract.MANIFEST_SCHEMA == "codex_ha_review_global_file_manifest.v1"
    assert contract.MANIFEST_TYPES == ("baseline", "final")
    assert contract.MANIFEST_REQUIRED_FIELDS == (
        "schema",
        "manifest_type",
        "generated_at",
        "approved_path_patterns",
        "entries",
    )
    assert contract.MANIFEST_ENTRY_FIELDS == (
        "path",
        "exists",
        "kind",
        "mode",
        "sha256",
    )
    source_tree_root = Path(contract.__file__).resolve().parents[2]
    expected_path_patterns = (
        str(Path.home() / ".claude/CLAUDE.md"),
        str(Path.home() / ".local/bin/codex-ha-review"),
        f"{source_tree_root}/**",
    )
    assert expected_path_patterns == contract.APPROVED_GLOBAL_PATH_PATTERNS
    assert contract.are_manifest_path_patterns_approved(
        contract.APPROVED_GLOBAL_PATH_PATTERNS,
    )
    assert not contract.are_manifest_path_patterns_approved(
        (
            *contract.APPROVED_GLOBAL_PATH_PATTERNS,
            str(Path.home() / "workspace/llm-broker/**"),
        ),
    )
    assert not contract.are_manifest_path_patterns_approved(
        contract.APPROVED_GLOBAL_PATH_PATTERNS[:-1],
    )


def test_runtime_sources_do_not_embed_current_machine_home_literal() -> None:
    # Given: guardrail 代码需要能迁移到不同用户名/home 路径的机器.
    source_files = (
        Path(contract.__file__),
        Path(contract.WRAPPER_SOURCE_PATH),
    )

    # When: 读取 runtime path 决策所在源码.
    combined_source = "\n".join(
        path.read_text(encoding="utf-8") for path in source_files
    )

    # Then: 源码不得把当前机器 home 当成契约常量.
    assert str(Path.home()) not in combined_source
    assert "Path.home()" in combined_source
    assert "Path(__file__).resolve()" in combined_source


@pytest.mark.parametrize(
    "candidate",
    ["codex-review", "codex-ha-review --model gpt-5.5", "codex-ha-review2"],
)
def test_alternate_wrapper_names_are_rejected_when_checked(candidate: str) -> None:
    # Given: wrapper 名称是固定全局命令契约.
    # When: 检查非精确候选值.
    # Then: contract 拒绝候选值, 而不是允许执行者自由裁量.
    assert not contract.is_wrapper_name_allowed(candidate)


@pytest.mark.parametrize("candidate", ["argv", "file", "stdout", "prompt_argv"])
def test_non_stdin_prompt_modes_are_rejected_when_checked(candidate: str) -> None:
    # Given: prompt 传递不得把渲染后正文暴露到 argv 或文件.
    # When: 检查非 stdin 模式.
    # Then: 只有 stdin 是有效模式.
    assert not contract.is_prompt_input_mode_allowed(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "vsllm-openai/gpt-5.5-pro20x",
        "gpt-5.5-pro20x",
        "session_model",
        "config.toml or equivalent",
        "--model gpt-5.5-pro20x",
    ],
)
def test_model_source_guesses_are_rejected_when_checked(candidate: str) -> None:
    # Given: model 来源只能是 Codex config 文件.
    # When: 检查 provider 前缀猜测或软替代措辞.
    # Then: contract 拒绝这些候选值.
    assert not contract.is_model_source_allowed(candidate)


def test_exact_contract_values_are_accepted_when_checked() -> None:
    # Given: 精确字面量是唯一允许的 contract 值.
    # When: helper 收到这些精确字面量.
    # Then: 每个 helper 只接受固定值.
    assert contract.is_wrapper_name_allowed("codex-ha-review")
    assert contract.is_prompt_input_mode_allowed("stdin")
    assert contract.is_model_source_allowed("${CODEX_HOME:-~/.codex}/config.toml")
    assert contract.is_receipt_field_allowed("argv_without_prompt")
    assert contract.is_receipt_field_allowed("source_auth_present")

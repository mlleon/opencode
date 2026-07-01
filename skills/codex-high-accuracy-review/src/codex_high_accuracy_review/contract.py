"""固定 Codex 高精度复审 wrapper 的路径、schema 与枚举契约."""

from __future__ import annotations

from enum import StrEnum, unique
from pathlib import Path
from typing import Final

WRAPPER_NAME: Final = "codex-ha-review"
_SOURCE_TREE_ROOT_PATH: Final = Path(__file__).resolve().parents[2]
_USER_HOME: Final = Path.home()

SOURCE_TREE_ROOT: Final = str(_SOURCE_TREE_ROOT_PATH)
WRAPPER_SOURCE_PATH: Final = str(_SOURCE_TREE_ROOT_PATH / "bin" / WRAPPER_NAME)
INSTALLED_SHIM_PATH: Final = str(_USER_HOME / ".local" / "bin" / WRAPPER_NAME)
PROMPT_TEMPLATE_PATH: Final = str(
    _SOURCE_TREE_ROOT_PATH / "templates" / "plan-review.txt",
)
MODEL_CONFIG_SOURCE: Final = "${CODEX_HOME:-~/.codex}/config.toml"
PROMPT_INPUT_MODE: Final = "stdin"
REASONING_EFFORT: Final = "xhigh"
REVIEW_TYPE: Final = "plan_high_accuracy"
RECEIPT_SCHEMA: Final = "codex_high_accuracy_review_receipt.v1"
MANIFEST_SCHEMA: Final = "codex_ha_review_global_file_manifest.v1"
UTC_TIMESTAMP_PATTERN: Final = r"^\d{8}T\d{6}Z(?:-\d+)?$"

WORKSPACE_PLAN_PATH: Final = "inputs/plan.md"
WORKSPACE_DRAFT_PATH: Final = "inputs/draft.md"
WORKSPACE_SOURCE_METADATA_PATH: Final = "metadata/source.json"
DISPOSABLE_TEMP_ROOT: Final = f"{chr(47)}tmp{chr(47)}opencode"
DISPOSABLE_WORKSPACE_PATTERN: Final = f"{DISPOSABLE_TEMP_ROOT}/codex-ha-review-*"
DISPOSABLE_CODEX_HOME_PATTERN: Final = f"{DISPOSABLE_TEMP_ROOT}/codex-ha-home-*"


@unique
class ReceiptStatus(StrEnum):
    """receipt `status` 字段允许的封闭取值."""

    DRY_RUN = "dry_run"
    EXECUTED = "executed"
    PREFLIGHT_REJECTED = "preflight_rejected"
    CODEX_FAILED = "codex_failed"
    WRAPPER_FAILED = "wrapper_failed"


@unique
class ReviewDecision(StrEnum):
    """receipt `review_decision` 字段允许的封闭取值."""

    OKAY = "okay"
    REJECT = "reject"
    MALFORMED = "malformed"
    NOT_RUN = "not_run"


@unique
class ExecutionMode(StrEnum):
    """receipt `execution_mode` 字段允许的封闭取值."""

    DRY_RUN = "dry_run"
    SPAWNED = "spawned"


REQUIRED_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
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

OPTIONAL_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
    "draft_source_path",
    "draft_sha256",
    "codex_exit_code",
    "rejection_reason",
    "codex_binary_path",
)

ALLOWED_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
    REQUIRED_RECEIPT_FIELDS + OPTIONAL_RECEIPT_FIELDS
)

FORBIDDEN_RECEIPT_FIELDS: Final[tuple[str, ...]] = (
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

MANIFEST_TYPES: Final[tuple[str, ...]] = ("baseline", "final")
MANIFEST_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "schema",
    "manifest_type",
    "generated_at",
    "approved_path_patterns",
    "entries",
)
MANIFEST_ENTRY_FIELDS: Final[tuple[str, ...]] = (
    "path",
    "exists",
    "kind",
    "mode",
    "sha256",
)
APPROVED_GLOBAL_PATH_PATTERNS: Final[tuple[str, ...]] = (
    str(_USER_HOME / ".claude" / "CLAUDE.md"),
    INSTALLED_SHIM_PATH,
    f"{SOURCE_TREE_ROOT}/**",
)


def is_wrapper_name_allowed(candidate: str) -> bool:
    """只接受固定 wrapper 名称."""
    return candidate == WRAPPER_NAME


def is_prompt_input_mode_allowed(candidate: str) -> bool:
    """只接受 stdin prompt 输入模式."""
    return candidate == PROMPT_INPUT_MODE


def is_model_source_allowed(candidate: str) -> bool:
    """只接受 Codex config.toml 作为 model 来源."""
    return candidate == MODEL_CONFIG_SOURCE


def is_receipt_field_allowed(field_name: str) -> bool:
    """只接受 metadata-only receipt schema 中登记的字段."""
    return field_name in ALLOWED_RECEIPT_FIELDS


def are_manifest_path_patterns_approved(path_patterns: tuple[str, ...]) -> bool:
    """只接受完整且精确的全局 manifest 路径白名单."""
    return path_patterns == APPROVED_GLOBAL_PATH_PATTERNS

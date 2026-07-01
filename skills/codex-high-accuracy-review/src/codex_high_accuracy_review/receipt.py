"""写入 metadata-only Codex 高精度复审 receipt."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NotRequired, TypedDict

from codex_high_accuracy_review import contract

if TYPE_CHECKING:
    from pathlib import Path

type ReceiptValue = str | int | bool | None | list[str]


class ReceiptDocument(TypedDict):
    """receipt v1 的 JSON 形状, 不包含 prompt/stdout/stderr/auth 原文."""

    schema: str
    status: str
    execution_mode: str
    review_type: str
    source_codex_home: str
    source_config_path: str
    source_auth_present: bool
    resolved_model_provider: str
    resolved_model: str
    resolved_reasoning_effort: str
    project_root: str
    plan_source_path: str
    plan_sha256: str
    disposable_workspace: str
    disposable_codex_home: str
    child_codex_home_env: str
    argv_without_prompt: list[str]
    prompt_template_path: str
    prompt_template_sha256: str
    prompt_input_mode: str
    started_at: str
    ended_at: str
    wrapper_exit_code: int
    review_decision: str
    draft_source_path: NotRequired[str]
    draft_sha256: NotRequired[str]
    codex_exit_code: NotRequired[int]
    rejection_reason: NotRequired[str]
    codex_binary_path: NotRequired[str]


def write_receipt(path: Path, document: ReceiptDocument) -> None:
    """把 receipt 原子化为稳定 JSON 字段顺序, 并拒绝未知字段."""
    _ensure_allowed_fields(tuple(document))
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _ensure_allowed_fields(field_names: tuple[str, ...]) -> None:
    unknown_fields = tuple(
        field_name
        for field_name in field_names
        if not contract.is_receipt_field_allowed(field_name)
    )
    if unknown_fields:
        raise ReceiptFieldError(unknown_fields)


class ReceiptFieldError(Exception):
    """receipt 出现 contract 未登记字段时 fail-closed."""

    def __init__(self, field_names: tuple[str, ...]) -> None:
        """保存字段名元数据, 不包含任何 receipt 值."""
        super().__init__(",".join(field_names))
        self.field_names: tuple[str, ...] = field_names


__all__ = ("ReceiptDocument", "ReceiptFieldError", "ReceiptValue", "write_receipt")

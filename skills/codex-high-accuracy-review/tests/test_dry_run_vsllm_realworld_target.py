from __future__ import annotations

import re
from pathlib import Path

import pytest

from codex_high_accuracy_review import contract, staging
from tests.realworld_target_helpers import (
    CONFIG_PATH,
    DRAFT_PATH,
    LIVE_TARGET_SKIP_REASON,
    LIVE_TARGET_UNAVAILABLE,
    PLAN_PATH,
    PROJECT_ROOT,
    assert_safe_receipt,
    assert_staging_cleaned,
    common_args,
    receipt_string,
    receipt_text,
    run_wrapper,
    sha256,
)

pytestmark = pytest.mark.skipif(
    LIVE_TARGET_UNAVAILABLE,
    reason=LIVE_TARGET_SKIP_REASON,
)


def test_dry_run_writes_vsllm_receipt_without_spawning_codex(tmp_path: Path) -> None:
    # Given: 当前 live plan/draft 与 live Codex config 是唯一可信输入.
    receipt_path = tmp_path / "dry-run-receipt.json"
    manifest_path = receipt_path.with_name("dry-run-receipt-global-manifest.json")

    # When: wrapper 以 dry-run 执行完整 preflight/staging/prompt/receipt/cleanup.
    result = run_wrapper(("--dry-run", *common_args(receipt_path)))

    # Then: receipt 证明 config-driven 模型、stdin prompt、无 -m、live hash 与 cleanup.
    assert result.returncode == 0
    assert result.stderr == ""
    assert "status=dry_run" in result.stdout
    assert receipt_string(receipt_path, "schema") == contract.RECEIPT_SCHEMA
    assert receipt_string(receipt_path, "status") == (
        contract.ReceiptStatus.DRY_RUN.value
    )
    assert receipt_string(receipt_path, "execution_mode") == (
        contract.ExecutionMode.DRY_RUN.value
    )
    assert receipt_string(receipt_path, "resolved_model_provider") == "vsllm"
    assert receipt_string(receipt_path, "resolved_model") == "gpt-5.5-pro20x"
    assert receipt_string(receipt_path, "resolved_reasoning_effort") == "xhigh"
    assert receipt_string(receipt_path, "source_config_path") == str(CONFIG_PATH)
    assert '  "source_auth_present": true' in receipt_text(receipt_path)
    assert receipt_string(receipt_path, "plan_source_path") == str(PLAN_PATH)
    assert receipt_string(receipt_path, "draft_source_path") == str(DRAFT_PATH)
    assert receipt_string(receipt_path, "plan_sha256") == sha256(PLAN_PATH)
    assert receipt_string(receipt_path, "draft_sha256") == sha256(DRAFT_PATH)
    assert receipt_string(receipt_path, "prompt_input_mode") == "stdin"
    text = receipt_text(receipt_path)
    assert '    "-m"' not in text
    assert '    "--model"' not in text
    assert receipt_string(receipt_path, "child_codex_home_env") == (
        f"CODEX_HOME={receipt_string(receipt_path, 'disposable_codex_home')}"
    )
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert contract.MANIFEST_SCHEMA in manifest_text
    assert contract.APPROVED_GLOBAL_PATH_PATTERNS[2] in manifest_text
    assert_safe_receipt(receipt_path)
    assert_staging_cleaned(receipt_path)


def test_dry_run_without_receipt_out_defaults_to_project_evidence() -> None:
    # Given: caller omits --receipt-out for the live project plan/draft.
    result = run_wrapper(
        (
            "--dry-run",
            "--project-root",
            str(PROJECT_ROOT),
            "--plan",
            str(PLAN_PATH),
            "--draft",
            str(DRAFT_PATH),
        ),
    )
    receipt_match = re.search(r"receipt=([^\s]+)", result.stdout)
    assert receipt_match is not None
    receipt_path = Path(receipt_match.group(1))
    manifest_path = receipt_path.with_name(f"{receipt_path.stem}-global-manifest.json")

    try:
        # Then: default receipt lands under project .omo/evidence, not /tmp/opencode.
        assert result.returncode == 0
        assert result.stderr == ""
        assert receipt_path.parent == PROJECT_ROOT / ".omo" / "evidence"
        assert receipt_path.name.startswith("codex-ha-review-")
        assert manifest_path.parent == receipt_path.parent
        assert receipt_string(receipt_path, "status") == (
            contract.ReceiptStatus.DRY_RUN.value
        )
        assert_safe_receipt(receipt_path)
    finally:
        receipt_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)


def test_tmp_plan_copy_rejects_with_safe_receipt(tmp_path: Path) -> None:
    # Given: plan/draft 被复制到 /tmp 下, 模拟历史 stale source copy 事故.
    temp_project = tmp_path / "stale-project"
    plan_copy = temp_project / ".omo/plans/vsllm-realworld-diagnostics.md"
    draft_copy = temp_project / ".omo/drafts/vsllm-realworld-diagnostics.md"
    plan_copy.parent.mkdir(parents=True)
    draft_copy.parent.mkdir(parents=True)
    _ = plan_copy.write_bytes(PLAN_PATH.read_bytes())
    _ = draft_copy.write_bytes(DRAFT_PATH.read_bytes())
    receipt_path = tmp_path / "rejected-receipt.json"

    # When: wrapper 收到 /tmp source plan.
    result = run_wrapper(
        (
            "--dry-run",
            "--project-root",
            str(temp_project),
            "--plan",
            str(plan_copy),
            "--draft",
            str(draft_copy),
            "--receipt-out",
            str(receipt_path),
        ),
    )

    # Then: fail-closed, receipt 只记录安全 status/reason, 不创建可用 staging 目录.
    assert result.returncode == 4
    assert receipt_string(receipt_path, "status") == (
        contract.ReceiptStatus.PREFLIGHT_REJECTED.value
    )
    assert receipt_string(receipt_path, "review_decision") == (
        contract.ReviewDecision.NOT_RUN.value
    )
    assert receipt_string(receipt_path, "rejection_reason") == (
        staging.PreflightRejectionReason.TEMP_SOURCE_PATH.value
    )
    assert '  "wrapper_exit_code": 4' in receipt_text(receipt_path)
    assert_safe_receipt(receipt_path)

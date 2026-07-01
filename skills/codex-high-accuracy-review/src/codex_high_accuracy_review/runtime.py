"""Codex 高精度复审 wrapper 的 dry-run 与 fake-exec 运行时编排."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_high_accuracy_review import (
    command_gate,
    config,
    contract,
    manifest,
    receipt,
    staging,
    workspace,
)


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """一次 wrapper 调用的已解析 CLI 输入."""

    project_root: Path
    plan: Path
    draft: Path | None
    dry_run: bool
    receipt_out: Path | None = None


@dataclass(frozen=True, slots=True)
class ReviewRunResult:
    """wrapper 执行后可打印的安全结果元数据."""

    exit_code: int
    status: contract.ReceiptStatus
    receipt_path: Path
    manifest_path: Path | None


@dataclass(frozen=True, slots=True)
class _ReceiptContext:
    staged: staging.StagedReviewEnvironment
    workspace_files: workspace.WorkspaceFiles
    resolved_config: config.ResolvedCodexConfig
    rendered_prompt: command_gate.RenderedPrompt
    command_fields: command_gate.CommandGateReceiptFields
    status: contract.ReceiptStatus
    execution_mode: contract.ExecutionMode
    started_at: str
    ended_at: str
    codex_binary_path: str | None


@dataclass(frozen=True, slots=True)
class _PreflightReceiptContext:
    request: ReviewRequest
    rendered_prompt: command_gate.RenderedPrompt
    rejection_reason: staging.PreflightRejectionReason
    started_at: str
    ended_at: str


def run_review(request: ReviewRequest) -> ReviewRunResult:
    """执行 dry-run 或 Codex spawned 路径, 并保证 staging cleanup."""
    started_at = _utc_timestamp()
    receipt_path = _receipt_path_for(request, started_at)
    rendered_prompt = command_gate.render_review_prompt()
    staged: staging.StagedReviewEnvironment | None = None
    try:
        staged = staging.stage_review_environment(
            staging.StagingRequest(
                project_root=request.project_root,
                plan=request.plan,
                draft=request.draft,
            ),
        )
        result = _run_staged_review(
            request=request,
            staged=staged,
            rendered_prompt=rendered_prompt,
            started_at=started_at,
            receipt_path=receipt_path,
        )
    except staging.PreflightRejectedError as error:
        result = _write_preflight_receipt(
            _PreflightReceiptContext(
                request=request,
                rendered_prompt=rendered_prompt,
                rejection_reason=error.reason,
                started_at=started_at,
                ended_at=_utc_timestamp(),
            ),
            receipt_path,
        )
    finally:
        if staged is not None:
            _cleanup_staged(staged)
    return result


def _run_staged_review(
    *,
    request: ReviewRequest,
    staged: staging.StagedReviewEnvironment,
    rendered_prompt: command_gate.RenderedPrompt,
    started_at: str,
    receipt_path: Path,
) -> ReviewRunResult:
    resolved_config = config.parse_codex_config(staged.config_toml)
    workspace_files = workspace.prepare_review_workspace(staged)
    command = command_gate.build_codex_exec_command(
        workspace=staged.disposable_workspace,
        disposable_codex_home=staged.disposable_codex_home,
    )
    codex_binary_path = shutil.which(command.argv[0])
    gate_result = _gate_result_for(request, staged, rendered_prompt)
    command_fields = command_gate.build_command_gate_receipt_fields(
        command, gate_result
    )
    context = _ReceiptContext(
        staged=staged,
        workspace_files=workspace_files,
        resolved_config=resolved_config,
        rendered_prompt=rendered_prompt,
        command_fields=command_fields,
        status=gate_result.status,
        execution_mode=_execution_mode_for(request),
        started_at=started_at,
        ended_at=_utc_timestamp(),
        codex_binary_path=codex_binary_path,
    )
    receipt.write_receipt(receipt_path, _success_receipt(context))
    manifest_path = manifest.sibling_manifest_path(receipt_path)
    manifest.write_global_manifest(manifest_path, "final")
    return ReviewRunResult(
        exit_code=gate_result.wrapper_exit_code,
        status=gate_result.status,
        receipt_path=receipt_path,
        manifest_path=manifest_path,
    )


def _gate_result_for(
    request: ReviewRequest,
    staged: staging.StagedReviewEnvironment,
    rendered_prompt: command_gate.RenderedPrompt,
) -> command_gate.CommandGateResult:
    if request.dry_run:
        return command_gate.CommandGateResult(
            status=contract.ReceiptStatus.DRY_RUN,
            review_decision=contract.ReviewDecision.NOT_RUN,
            wrapper_exit_code=0,
            codex_exit_code=None,
        )
    return command_gate.execute_codex_exec(
        command_gate.CodexExecRequest(
            workspace=staged.disposable_workspace,
            disposable_codex_home=staged.disposable_codex_home,
            prompt=rendered_prompt.body,
        ),
    )


def _success_receipt(context: _ReceiptContext) -> receipt.ReceiptDocument:
    document = receipt.ReceiptDocument(
        schema=contract.RECEIPT_SCHEMA,
        status=context.status.value,
        execution_mode=context.execution_mode.value,
        review_type=contract.REVIEW_TYPE,
        source_codex_home=str(context.staged.source_codex_home),
        source_config_path=str(context.staged.source_config_path),
        source_auth_present=context.staged.source_auth_path.is_file(),
        resolved_model_provider=context.resolved_config.model_provider,
        resolved_model=context.resolved_config.model,
        resolved_reasoning_effort=context.resolved_config.reasoning_effort,
        project_root=str(context.staged.project_root),
        plan_source_path=str(context.staged.plan_source_path),
        plan_sha256=context.workspace_files.plan_sha256,
        disposable_workspace=str(context.staged.disposable_workspace),
        disposable_codex_home=str(context.staged.disposable_codex_home),
        child_codex_home_env=context.command_fields.child_codex_home_env,
        argv_without_prompt=list(context.command_fields.argv_without_prompt),
        prompt_template_path=str(context.rendered_prompt.template_path),
        prompt_template_sha256=_sha256(context.rendered_prompt.template_path),
        prompt_input_mode=context.command_fields.prompt_input_mode,
        started_at=context.started_at,
        ended_at=context.ended_at,
        wrapper_exit_code=context.command_fields.wrapper_exit_code,
        review_decision=context.command_fields.review_decision.value,
    )
    if context.staged.draft_source_path is not None:
        document["draft_source_path"] = str(context.staged.draft_source_path)
    if context.workspace_files.draft_sha256 is not None:
        document["draft_sha256"] = context.workspace_files.draft_sha256
    if context.command_fields.codex_exit_code is not None:
        document["codex_exit_code"] = context.command_fields.codex_exit_code
    if context.codex_binary_path is not None:
        document["codex_binary_path"] = context.codex_binary_path
    return document


def _write_preflight_receipt(
    context: _PreflightReceiptContext,
    receipt_path: Path,
) -> ReviewRunResult:
    wrapper_exit_code = command_gate.wrapper_exit_code_for(
        status=contract.ReceiptStatus.PREFLIGHT_REJECTED,
        review_decision=contract.ReviewDecision.NOT_RUN,
    )
    receipt.write_receipt(receipt_path, _preflight_receipt(context, wrapper_exit_code))
    return ReviewRunResult(
        exit_code=wrapper_exit_code,
        status=contract.ReceiptStatus.PREFLIGHT_REJECTED,
        receipt_path=receipt_path,
        manifest_path=None,
    )


def _preflight_receipt(
    context: _PreflightReceiptContext,
    wrapper_exit_code: int,
) -> receipt.ReceiptDocument:
    return receipt.ReceiptDocument(
        schema=contract.RECEIPT_SCHEMA,
        status=contract.ReceiptStatus.PREFLIGHT_REJECTED.value,
        execution_mode=_execution_mode_for(context.request).value,
        review_type=contract.REVIEW_TYPE,
        source_codex_home="",
        source_config_path="",
        source_auth_present=False,
        resolved_model_provider="",
        resolved_model="",
        resolved_reasoning_effort="",
        project_root=str(context.request.project_root),
        plan_source_path=str(context.request.plan),
        plan_sha256=_sha256_if_file(context.request.plan),
        disposable_workspace="",
        disposable_codex_home="",
        child_codex_home_env="",
        argv_without_prompt=[],
        prompt_template_path=str(context.rendered_prompt.template_path),
        prompt_template_sha256=_sha256(context.rendered_prompt.template_path),
        prompt_input_mode=context.rendered_prompt.input_mode,
        started_at=context.started_at,
        ended_at=context.ended_at,
        wrapper_exit_code=wrapper_exit_code,
        review_decision=contract.ReviewDecision.NOT_RUN.value,
        rejection_reason=context.rejection_reason.value,
    )


def _execution_mode_for(request: ReviewRequest) -> contract.ExecutionMode:
    if request.dry_run:
        return contract.ExecutionMode.DRY_RUN
    return contract.ExecutionMode.SPAWNED


def _receipt_path_for(request: ReviewRequest, started_at: str) -> Path:
    if request.receipt_out is not None:
        return request.receipt_out
    receipt_name = f"codex-ha-review-{started_at}-{os.getpid()}.json"
    return Path(request.project_root) / ".omo" / "evidence" / receipt_name


def _cleanup_staged(staged: staging.StagedReviewEnvironment) -> None:
    shutil.rmtree(staged.disposable_workspace, ignore_errors=True)
    shutil.rmtree(staged.disposable_codex_home, ignore_errors=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_if_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return _sha256(path)


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


__all__ = ("ReviewRequest", "ReviewRunResult", "run_review")

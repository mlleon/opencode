from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from codex_high_accuracy_review import contract
from tests.realworld_target_helpers import (
    LIVE_TARGET_SKIP_REASON,
    LIVE_TARGET_UNAVAILABLE,
    assert_safe_receipt,
    assert_staging_cleaned,
    common_args,
    receipt_string,
    receipt_text,
    run_wrapper,
    wrapper_env,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    LIVE_TARGET_UNAVAILABLE,
    reason=LIVE_TARGET_SKIP_REASON,
)


def test_fake_codex_execution_receipt_proves_spawn_contract(
    tmp_path: Path,
) -> None:
    # Given: PATH 中注入 fake codex, 它只写安全布尔报告并在发现危险 argv/env 时拒绝.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_report_path = tmp_path / "fake-report.json"
    fake_codex = fake_bin / "codex"
    _ = fake_codex.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from pathlib import Path
body = sys.stdin.read()
argv = sys.argv[1:]
home = os.environ.get("CODEX_HOME", "")
workspace = Path(argv[argv.index("-C") + 1])
bad_argv = "-m" in argv or "--model" in argv
home_ok = home.startswith("/tmp/opencode/codex-ha-home-")
stdin_ok = "inputs/plan.md" in body
inputs_ok = workspace.joinpath("inputs/plan.md").is_file()
Path(os.environ["FAKE_CODEX_REPORT"]).write_text("\\n".join(
    (f"codex_home={home}", f"has_forbidden_model_flag={bad_argv}",
     f"env_points_to_home={home_ok}", f"stdin_mode={stdin_ok}",
     f"workspace_has_inputs={inputs_ok}")), encoding="utf-8",
)
if bad_argv or not home_ok or not inputs_ok:
    sys.stdout.write("REJECT unsafe fake contract\\n")
    raise SystemExit(0)
sys.stdout.write("OKAY fake review passed\\n")
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    env = wrapper_env(fake_bin)
    env["FAKE_CODEX_REPORT"] = str(fake_report_path)
    receipt_path = tmp_path / "fake-exec-receipt.json"

    # When: wrapper 走 spawned 路径, 但实际执行的是 fake codex.
    result = run_wrapper(common_args(receipt_path), env=env)

    # Then: spawned receipt 与 fake 报告共同证明 prompt/stdin、argv/env/workspace 契约.
    assert result.returncode == 0
    assert result.stderr == ""
    fake_report_text = fake_report_path.read_text(encoding="utf-8")
    assert receipt_string(receipt_path, "status") == (
        contract.ReceiptStatus.EXECUTED.value
    )
    assert receipt_string(receipt_path, "execution_mode") == (
        contract.ExecutionMode.SPAWNED.value
    )
    assert receipt_string(receipt_path, "review_decision") == (
        contract.ReviewDecision.OKAY.value
    )
    assert '  "codex_exit_code": 0' in receipt_text(receipt_path)
    assert receipt_string(receipt_path, "codex_binary_path") == str(fake_codex)
    assert "has_forbidden_model_flag=False" in fake_report_text
    assert "env_points_to_home=True" in fake_report_text
    assert "stdin_mode=True" in fake_report_text
    assert "workspace_has_inputs=True" in fake_report_text
    assert (
        f"codex_home={receipt_string(receipt_path, 'disposable_codex_home')}"
        in fake_report_text
    )
    assert '    "-m"' not in receipt_text(receipt_path)
    assert_safe_receipt(receipt_path)
    assert_staging_cleaned(receipt_path)


def test_fake_codex_malformed_decision_fails_closed(tmp_path: Path) -> None:
    # Given: fake codex 输出无法解析的最终决策行.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    _ = fake_codex.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.stdout.write('MAYBE ambiguous\\n')\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    receipt_path = tmp_path / "malformed-receipt.json"

    # When: wrapper 解析 fake stdout.
    result = run_wrapper(common_args(receipt_path), env=wrapper_env(fake_bin))

    # Then: wrapper fail-closed 为 malformed/3, 且 receipt 不保存 stdout 正文.
    assert result.returncode == 3
    assert receipt_string(receipt_path, "status") == (
        contract.ReceiptStatus.EXECUTED.value
    )
    assert receipt_string(receipt_path, "review_decision") == (
        contract.ReviewDecision.MALFORMED.value
    )
    assert "MAYBE ambiguous" not in receipt_path.read_text(encoding="utf-8")
    assert_staging_cleaned(receipt_path)

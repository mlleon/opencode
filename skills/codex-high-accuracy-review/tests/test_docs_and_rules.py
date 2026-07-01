from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from codex_high_accuracy_review import contract

SKILL_PATH: Final = Path(contract.SOURCE_TREE_ROOT) / "SKILL.md"
GLOBAL_RULE_PATH: Final = Path.home() / ".claude" / "CLAUDE.md"
WRAPPER_NAME: Final = "codex-ha-review"
CONFIG_SOURCE: Final = "${CODEX_HOME:-~/.codex}/config.toml"
HISTORICAL_BAD_MODEL_PREFIX: Final = "vsllm-openai/"

PERMISSIVE_MANUAL_SNIPPETS: Final[tuple[str, ...]] = (
    "you may run codex exec manually",
    "may run codex exec manually",
    "can run codex exec manually",
    "freehand codex exec review commands are allowed",
    "or equivalent",
)
PERMISSIVE_MODEL_PATTERNS: Final[tuple[str, ...]] = (
    r"(?:may|can|choose|guess|pass|set)\s+[^\n.]{0,80}vsllm-openai/",
    r"vsllm-openai/[^\n.]{0,80}(?:allowed|acceptable|ok|okay)",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.lower().split())


def test_skill_doc_requires_wrapper_only_review_when_read() -> None:
    # Given: Todo 4 exposes high-accuracy Codex review through one user skill doc.
    # When: the skill document is read.
    skill_text = read_text(SKILL_PATH)
    skill_text_lower = normalized(skill_text)

    # Then: the doc names the fixed wrapper and config source, not a freehand path.
    assert "name: codex-high-accuracy-review" in skill_text
    assert WRAPPER_NAME in skill_text
    assert CONFIG_SOURCE in skill_text
    assert "must use `codex-ha-review`" in skill_text_lower
    assert (
        "must read `${codex_home:-~/.codex}/config.toml` first" in skill_text_lower
    )
    assert "must not freehand `codex exec` review commands" in skill_text_lower


def test_global_rule_requires_config_first_wrapper_when_read() -> None:
    # Given: future projects inherit only the global CLAUDE rule.
    # When: the global rule file is read.
    global_text = read_text(GLOBAL_RULE_PATH)
    global_text_lower = normalized(global_text)

    # Then: the rule stays global and requires the wrapper/config-driven flow.
    assert "codex high-accuracy review" in global_text_lower
    assert WRAPPER_NAME in global_text
    assert CONFIG_SOURCE in global_text
    assert (
        "must read `${codex_home:-~/.codex}/config.toml` first" in global_text_lower
    )
    assert "must not freehand `codex exec` review commands" in global_text_lower


def test_docs_reject_manual_command_and_model_allowance_when_scanned() -> None:
    # Given: the historical failure came from manual Codex commands and guessed models.
    # When: both user-facing docs are scanned as plain text.
    combined_text = "\n".join((read_text(SKILL_PATH), read_text(GLOBAL_RULE_PATH)))
    combined_lower = normalized(combined_text)

    # Then: permissive manual-command wording and model allowances are absent.
    for snippet in PERMISSIVE_MANUAL_SNIPPETS:
        assert snippet not in combined_lower
    for pattern in PERMISSIVE_MODEL_PATTERNS:
        assert re.search(pattern, combined_lower) is None
    assert HISTORICAL_BAD_MODEL_PREFIX in combined_text
    assert "never rely on opencode session model strings" in combined_lower

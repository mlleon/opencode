"""解析 Codex config.toml 中允许持久化的模型元数据."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class CodexConfigError(Exception):
    """Codex config 缺少 wrapper 需要的安全模型字段."""

    field_name: str

    @override
    def __str__(self) -> str:
        """返回 metadata-only 字段名, 不包含 config 原文."""
        return f"missing_or_invalid_config_field:{self.field_name}"


@dataclass(frozen=True, slots=True)
class ResolvedCodexConfig:
    """receipt 允许记录的 Codex 模型解析结果."""

    model_provider: str
    model: str
    reasoning_effort: str


def parse_codex_config(config_toml: str) -> ResolvedCodexConfig:
    """从已 staging 的 config.toml 文本解析 provider/model/reasoning."""
    parsed: Mapping[str, object] = tomllib.loads(config_toml)
    return ResolvedCodexConfig(
        model_provider=_required_str(parsed, "model_provider"),
        model=_required_str(parsed, "model"),
        reasoning_effort=_required_str(parsed, "model_reasoning_effort"),
    )


def _required_str(parsed: Mapping[str, object], field_name: str) -> str:
    value = parsed.get(field_name)
    if not isinstance(value, str) or not value:
        raise CodexConfigError(field_name)
    return value


__all__ = (
    "CodexConfigError",
    "ResolvedCodexConfig",
    "parse_codex_config",
)

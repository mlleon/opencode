---
name: codex-high-accuracy-review
description: Use this skill whenever a user asks for a high-accuracy Codex review, Codex plan review, or extra-strict Codex verification. The review must be wrapper-only through codex-ha-review and config-driven from the user's Codex config.
---

# Codex High-Accuracy Review

High-accuracy Codex review must use `codex-ha-review`.

Before starting, agents must read `${CODEX_HOME:-~/.codex}/config.toml` first. The Codex model and provider come from that config; do not derive them from the current OpenCode session.

Agents must not freehand `codex exec` review commands. Do not add `-m`, `--model`, or manual model/provider overrides.

Never rely on OpenCode session model strings, including `vsllm-openai/gpt-5.5-pro20x`.

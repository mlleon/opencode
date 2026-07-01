# codex-ha-review 迁移文档

## 适用范围

本文只覆盖全局 Codex 高精度复审 guardrail 的迁移：

- `~/.config/opencode/skills/codex-high-accuracy-review/`
- `~/.local/bin/codex-ha-review`
- `~/.claude/CLAUDE.md` 中的 Codex high-accuracy review 规则
- `${CODEX_HOME:-~/.codex}/config.toml` 与 `auth.json` 的目标机准备方式

不覆盖 `llm-broker` 业务仓库迁移，也不覆盖其他 opencode 技能、keys、memory-source 或个人资料目录迁移。

## 当前兼容性事实

- skill 代码已不再把 `/home/mleon` 写成运行契约。
- `contract.py` 通过 `Path(__file__).resolve().parents[2]` 推导 skill 根目录。
- 用户级路径通过 `Path.home()` 推导。
- `bin/codex-ha-review` 只负责 bootstrap，然后调用 `src/codex_high_accuracy_review/cli.py`。
- `codex-ha-review` 的模型来源仍固定为 `${CODEX_HOME:-~/.codex}/config.toml`。
- prompt 仍走 stdin；receipt/manifest 只记录 metadata/hash/path/status，不记录 prompt/output/auth 原文。

## 目标机器前置条件

目标机器建议为 Linux、macOS 或 WSL。Windows 原生路径未作为首要兼容目标。

目标机器需要具备：

1. `python3`
2. `uv`
3. `codex` CLI
4. `rg`，用于迁移后扫描旧路径残留
5. 可写目录：
   - `~/.config/opencode/skills/`
   - `~/.local/bin/`
   - `~/.claude/`
   - `${CODEX_HOME:-~/.codex}/`
   - `/tmp/opencode/`

创建基础目录：

```bash
mkdir -p \
  "$HOME/.config/opencode/skills" \
  "$HOME/.local/bin" \
  "$HOME/.claude" \
  "${CODEX_HOME:-$HOME/.codex}" \
  "/tmp/opencode"
```

## 需要迁移的文件

### 1. skill 目录

从源机器复制：

```text
~/.config/opencode/skills/codex-high-accuracy-review/
```

建议使用 `rsync`，排除运行缓存和虚拟环境：

```bash
rsync -a --delete \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '.pytest-source-roots/' \
  "$SOURCE_HOST:$SOURCE_HOME/.config/opencode/skills/codex-high-accuracy-review/" \
  "$HOME/.config/opencode/skills/codex-high-accuracy-review/"
```

如果是在源机器上先打包再传输，可用：

```bash
tar \
  --exclude='.venv' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='.mypy_cache' \
  --exclude='.pytest-source-roots' \
  -czf codex-high-accuracy-review.tar.gz \
  -C "$HOME/.config/opencode/skills" \
  codex-high-accuracy-review
```

目标机器解包：

```bash
tar -xzf codex-high-accuracy-review.tar.gz -C "$HOME/.config/opencode/skills"
```

### 2. 全局命令 shim

不要原样复制源机器的 `~/.local/bin/codex-ha-review` symlink。源机器 symlink 可能包含旧 home 绝对路径。

目标机器必须重新创建：

```bash
chmod +x "$HOME/.config/opencode/skills/codex-high-accuracy-review/bin/codex-ha-review"
ln -sfn \
  "$HOME/.config/opencode/skills/codex-high-accuracy-review/bin/codex-ha-review" \
  "$HOME/.local/bin/codex-ha-review"
```

确认 PATH 包含 `~/.local/bin`：

```bash
command -v codex-ha-review
```

期望输出类似：

```text
/home/<target-user>/.local/bin/codex-ha-review
```

### 3. 全局规则

目标机器的 `~/.claude/CLAUDE.md` 需要包含这条规则。不要盲目覆盖已有 `CLAUDE.md`；如果目标机器已有内容，只合并这一段：

```markdown
# Codex high-accuracy review
- Codex high-accuracy review must use `codex-ha-review`; agents must read `${CODEX_HOME:-~/.codex}/config.toml` first and must not freehand `codex exec` review commands.
```

### 4. Codex 配置与认证

必须在目标机器准备：

```text
${CODEX_HOME:-~/.codex}/config.toml
${CODEX_HOME:-~/.codex}/auth.json
```

推荐优先在目标机器重新登录或重新配置 Codex，而不是直接复制认证文件。

如果确实需要复制同一身份的 Codex 配置，必须走安全通道，且迁移后修正权限：

```bash
chmod 700 "${CODEX_HOME:-$HOME/.codex}"
chmod 600 "${CODEX_HOME:-$HOME/.codex}/config.toml"
chmod 600 "${CODEX_HOME:-$HOME/.codex}/auth.json"
```

禁止把 `auth.json`、API key、token、Authorization header 粘贴到聊天、文档、日志或 issue 中。

## 不要迁移的内容

不要迁移这些运行产物：

- `~/.config/opencode/skills/codex-high-accuracy-review/.venv/`
- `~/.config/opencode/skills/codex-high-accuracy-review/.pytest_cache/`
- `~/.config/opencode/skills/codex-high-accuracy-review/.ruff_cache/`
- `~/.config/opencode/skills/codex-high-accuracy-review/.mypy_cache/`
- `~/.config/opencode/skills/codex-high-accuracy-review/.pytest-source-roots/`
- `/tmp/opencode/codex-ha-review-*`
- `/tmp/opencode/codex-ha-home-*`
- 任何 receipt、manifest、临时 smoke-test 文件

## 迁移后验证

以下命令都在目标机器执行。

### 1. 扫描旧机器路径残留

如果源机器是当前这台，扫描 `/home/mleon`：

```bash
rg -n "/home/mleon" \
  "$HOME/.config/opencode/skills/codex-high-accuracy-review" \
  "$HOME/.local/bin/codex-ha-review"
```

期望：无输出。

如果源机器不是 `/home/mleon`，把扫描字符串替换成源机器旧 home 路径。

### 2. 跑测试、lint、类型检查

```bash
uv run \
  --project "$HOME/.config/opencode/skills/codex-high-accuracy-review" \
  --group dev \
  pytest -q
```

```bash
uv run \
  --project "$HOME/.config/opencode/skills/codex-high-accuracy-review" \
  --group dev \
  ruff check .
```

```bash
uv run \
  --project "$HOME/.config/opencode/skills/codex-high-accuracy-review" \
  --group dev \
  basedpyright .
```

```bash
uv run \
  --project "$HOME/.config/opencode/skills/codex-high-accuracy-review" \
  --group dev \
  basedpyright bin/codex-ha-review
```

期望：pytest 全部通过，ruff 通过，两个 basedpyright 都是 `0 errors`。

### 3. 验证 CLI help

```bash
codex-ha-review --help
```

期望输出包含：

```text
Usage: codex-ha-review
Model source: ${CODEX_HOME:-~/.codex}/config.toml
Prompt mode: stdin
Source script: <target-home>/.config/opencode/skills/codex-high-accuracy-review/bin/codex-ha-review
```

### 4. 做一次 dry-run smoke test

创建临时 smoke 项目。不要放在 `/tmp` 下，因为 wrapper 会拒绝临时 source 输入：

```bash
SMOKE_ROOT="$HOME/codex-ha-review-smoke"
mkdir -p "$SMOKE_ROOT/.omo/plans" "$SMOKE_ROOT/.omo/drafts" "$SMOKE_ROOT/.omo/evidence"
printf '# Smoke plan\n' > "$SMOKE_ROOT/.omo/plans/smoke.md"
printf '# Smoke draft\n' > "$SMOKE_ROOT/.omo/drafts/smoke.md"
```

运行 dry-run：

```bash
codex-ha-review \
  --dry-run \
  --project-root "$SMOKE_ROOT" \
  --plan "$SMOKE_ROOT/.omo/plans/smoke.md" \
  --draft "$SMOKE_ROOT/.omo/drafts/smoke.md" \
  --receipt-out "/tmp/opencode/codex-ha-migration-smoke.json"
```

期望输出：

```text
status=dry_run receipt=/tmp/opencode/codex-ha-migration-smoke.json manifest=/tmp/opencode/codex-ha-migration-smoke-global-manifest.json
```

### 5. 验证坏输入 fail-closed

```bash
python3 - <<'PY'
from __future__ import annotations

import subprocess
from pathlib import Path

home = Path.home()
smoke_root = home / "codex-ha-review-smoke"
result = subprocess.run(
    [
        "codex-ha-review",
        "--dry-run",
        "--project-root",
        str(smoke_root),
        "--plan",
        str(smoke_root / ".omo/plans/missing.md"),
        "--receipt-out",
        "/tmp/opencode/codex-ha-migration-bad.json",
    ],
    text=True,
    capture_output=True,
    check=False,
)
print(result.stdout.strip())
print(f"exit_code={result.returncode}")
PY
```

期望输出包含：

```text
status=preflight_rejected
exit_code=4
```

### 6. 清理 smoke 文件

```bash
rm -rf "$HOME/codex-ha-review-smoke"
rm -f \
  "/tmp/opencode/codex-ha-migration-smoke.json" \
  "/tmp/opencode/codex-ha-migration-smoke-global-manifest.json" \
  "/tmp/opencode/codex-ha-migration-bad.json"
```

## 常见故障

### `codex-ha-review: command not found`

检查：

```bash
command -v codex-ha-review
printf '%s\n' "$PATH"
```

修复：确认 `~/.local/bin` 在 PATH 中，并重新创建 symlink。

### `ModuleNotFoundError: No module named 'codex_high_accuracy_review'`

通常是 `~/.local/bin/codex-ha-review` 指向了错误位置，或 skill 目录没有复制完整。

检查：

```bash
ls -l "$HOME/.local/bin/codex-ha-review"
ls "$HOME/.config/opencode/skills/codex-high-accuracy-review/src/codex_high_accuracy_review"
```

修复：重新创建 symlink，不要复用源机器 symlink。

### `missing_config` 或 `missing_auth`

目标机器缺少 `${CODEX_HOME:-~/.codex}/config.toml` 或 `auth.json`。

修复：在目标机器重新登录 Codex，或通过安全通道迁移配置和认证文件，并设置 `600` 权限。

### dry-run 被 `TEMP_SOURCE_PATH` 拒绝

说明 `--project-root`、`--plan` 或 `--draft` 位于 `/tmp`、`/var/tmp`、`/private/tmp`、`/tmp/opencode` 等临时目录下。

修复：把 smoke 项目或真实项目放到 `$HOME` 下的非临时目录。

### 测试在别的项目目录误收集其他 tests

必须在 skill 项目目录运行测试，或显式指定 `--project` 并把工作目录切到 skill 根：

```bash
cd "$HOME/.config/opencode/skills/codex-high-accuracy-review"
uv run --project . --group dev pytest -q
```

## 迁移完成判定

同时满足以下条件才算迁移完成：

1. `rg` 扫描旧 home 路径无输出。
2. `codex-ha-review --help` 显示目标机器路径。
3. `pytest`、`ruff`、`basedpyright .`、`basedpyright bin/codex-ha-review` 全部通过。
4. smoke dry-run 返回 `status=dry_run`。
5. 坏输入返回 `status=preflight_rejected` 且退出码为 `4`。
6. receipt/manifest 中没有 prompt/output/auth 原文，只包含 metadata/hash/path/status。

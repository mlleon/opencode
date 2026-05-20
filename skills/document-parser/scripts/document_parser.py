from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path
from typing import List, Optional
import sys

_orchestrator = import_module("scripts.orchestrator")


def main(argv: Optional[List[str]] = None) -> int:
  parser = argparse.ArgumentParser(prog="document-parser")
  parser.add_argument("inputs", nargs="+", help="本地文件路径或 URL（不可混用）")
  parser.add_argument(
    "--output-dir",
    dest="outputDir",
    default=None,
    help="输出根目录；不传则使用 CWD",
  )
  try:
    args = parser.parse_args(argv)
  except SystemExit as e:
    code = e.code
    if code is None:
      return 0
    if isinstance(code, int):
      return code
    return 2

  inputs: List[str] = list(args.inputs)
  hasUrl = any(item.startswith("http") for item in inputs)
  hasLocal = any(not item.startswith("http") for item in inputs)
  if hasUrl and hasLocal:
    print("错误：不支持 URL 与本地文件混用", file=sys.stderr)
    return 2

  outputDir = Path(args.outputDir) if args.outputDir else Path.cwd()
  try:
    results = _orchestrator.parseMany(sources=inputs, outputDir=outputDir)
  except Exception as e:
    print(f"错误：{e}", file=sys.stderr)
    return 1

  for result in results:
    print(result.paths.normalizedMarkdownPath)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

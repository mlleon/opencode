#!/usr/bin/env python3
import sys
import time
from pathlib import Path


def _wait_for_file(path: Path, timeout_sec: float) -> bool:
  """等待文件出现且大小>0。"""
  deadline = time.monotonic() + max(0.0, float(timeout_sec))
  while True:
    try:
      if path.exists() and path.stat().st_size > 0:
        return True
    except FileNotFoundError:
      pass

    if time.monotonic() >= deadline:
      return False
    time.sleep(0.1)


def main() -> None:
  if len(sys.argv) < 2:
    print("Usage: run.py <video_path> [language_code]", file=sys.stderr)
    raise SystemExit(1)

  video_path = Path(sys.argv[1]).resolve()
  language = sys.argv[2] if len(sys.argv) >= 3 else "zh-CN"

  scripts_dir = Path(__file__).resolve().parent
  if str(scripts_dir) not in sys.path:
    # 兼容被 importlib 加载/从任意 cwd 执行时，仍能 import 同目录模块。
    sys.path.insert(0, str(scripts_dir))

  # 运行顺序：先转录生成 txt/json，再基于 json 结构化成 md。
  from transcribe import transcribe_to_files
  from structure import structure_transcript_json

  outputs = transcribe_to_files(video_path, language)

  transcript_json_path = Path(outputs["json"]).resolve()
  if not transcript_json_path.exists():
    # 可能出现：转录进程还在落盘/被中断导致文件暂不存在。优先等一小会儿；仍不存在则重跑一次转录。
    if not _wait_for_file(transcript_json_path, timeout_sec=10.0):
      outputs = transcribe_to_files(video_path, language)
      transcript_json_path = Path(outputs["json"]).resolve()

  if not transcript_json_path.exists():
    partial = transcript_json_path.with_suffix(transcript_json_path.suffix + ".partial")
    if partial.exists():
      raise RuntimeError(
        "Transcript json not found, but partial output exists (likely interrupted by timeout).\n"
        f"Partial: {partial}\n"
        "你可以重新运行同一条 run.py 命令继续；partial 文件可用于排查。"
      )
    raise RuntimeError(f"Transcript json not found: {transcript_json_path}")

  structure_transcript_json(outputs["json"], outputs["md"])
  print(f"Saved transcript: {outputs['txt']}")
  print(f"Saved transcript json: {outputs['json']}")
  print(f"Saved notes: {outputs['md']}")


if __name__ == "__main__":
  main()

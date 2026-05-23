#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
from pathlib import Path

from .analyze import analyze_segments_file
from .assist import run_assist, write_deterministic_assist_placeholder
from .classify import classify_segments_file
from .normalize import normalize_transcript_file
from .paths import get_project_paths, get_transcript_paths
from .postprocess import postprocess_to_memory_source
from .segment import segment_normalized_file
from .structure import structure_pipeline_outputs
from .transcribe import transcribe_to_files
from .validate import validate_or_raise, validate_project_structure


def _copy_transcribe_outputs(outputs: dict[str, Path], transcript_paths) -> None:
  transcript_paths.rawDir.mkdir(parents=True, exist_ok=True)
  mapping = {
    "txt": transcript_paths.transcriptTxt,
    "json": transcript_paths.transcriptJson,
  }
  for key, target in mapping.items():
    source = Path(outputs[key])
    shutil.copy2(source, target)
  source_srt = Path(outputs["json"]).with_suffix(".srt")
  if source_srt.exists():
    shutil.copy2(source_srt, transcript_paths.transcriptSrt)


def _write_review_artifacts(analysis: dict[str, object], review_dir: Path) -> None:
  suggested_hints = analysis.get("suggestedNewHints", [])
  if not isinstance(suggested_hints, list):
    suggested_hints = []
  suggested_tests = analysis.get("suggestedGoldenTests", [])
  if not isinstance(suggested_tests, list):
    suggested_tests = []
  review_dir.mkdir(parents=True, exist_ok=True)
  (review_dir / "analysis.json").write_text(
    json.dumps(analysis, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )
  (review_dir / "taxonomy-candidates.json").write_text(
    json.dumps({"suggestedNewHints": suggested_hints}, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )
  (review_dir / "golden-test-candidates.json").write_text(
    json.dumps({"suggestedGoldenTests": suggested_tests}, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )
  report_lines = [
    "# transcribe-video analysis review",
    "",
    f"- decision: {analysis.get('decision', 'unknown')}",
    f"- suggestedNewHints: {len(suggested_hints)}",
    f"- suggestedGoldenTests: {len(suggested_tests)}",
    "",
    "该报告为流程候选产物，不应写入 memory-source/raw。",
  ]
  (review_dir / "analysis-report.md").write_text("\n".join(report_lines), encoding="utf-8")


def run_pipeline(
  project_root: Path,
  input_path: Path,
  language: str,
  structure_mode: str,
  final_stem: str | None = None,
  taxonomy_review: str = "auto",
) -> dict[str, str]:
  project_errors = validate_project_structure(project_root)
  if project_errors:
    raise ValueError("\n".join(project_errors))

  transcript_paths = get_transcript_paths(project_root, input_path)
  transcript_paths.workRoot.mkdir(parents=True, exist_ok=True)
  outputs = transcribe_to_files(input_path, language)
  _copy_transcribe_outputs(outputs, transcript_paths)

  normalize_transcript_file(
    transcript_paths.transcriptJson,
    transcript_paths.normalizedJson,
    transcript_paths.normalizedMarkdown,
  )
  segment_normalized_file(transcript_paths.normalizedJson, transcript_paths.segmentsJson)
  classify_segments_file(transcript_paths.segmentsJson, transcript_paths.classificationJson)
  analysis: dict[str, object] = {"decision": "skipped"}
  if taxonomy_review != "off":
    analysis = analyze_segments_file(transcript_paths.segmentsJson, transcript_paths.analysisJson)
    if taxonomy_review in {"auto", "always"} and analysis.get("decision") == "stage_and_pause":
      _write_review_artifacts(analysis, transcript_paths.reviewDir)

  actual_mode = structure_mode
  llm_error = ""
  if structure_mode == "assisted":
    try:
      run_assist(transcript_paths.segmentsJson, transcript_paths.classificationJson, transcript_paths.assistJson)
    except Exception as exc:
      actual_mode = "deterministic"
      llm_error = str(exc)
      write_deterministic_assist_placeholder(transcript_paths.assistJson, llm_error)
  else:
    write_deterministic_assist_placeholder(transcript_paths.assistJson, "structure_mode=deterministic")

  structure_pipeline_outputs(
    transcript_paths.normalizedJson,
    transcript_paths.segmentsJson,
    transcript_paths.classificationJson,
    transcript_paths.structuredMarkdown,
    transcript_paths.assistJson if actual_mode == "assisted" else None,
    structure_mode=actual_mode,
    llm_error=llm_error,
  )
  support_files = [
    transcript_paths.transcriptTxt,
    transcript_paths.transcriptJson,
    transcript_paths.transcriptSrt,
    transcript_paths.normalizedJson,
    transcript_paths.segmentsJson,
    transcript_paths.classificationJson,
    transcript_paths.assistJson,
    transcript_paths.analysisJson,
  ]
  result = postprocess_to_memory_source(
    project_root=project_root,
    source_path=input_path,
    structured_markdown_path=transcript_paths.structuredMarkdown,
    support_files=support_files,
    final_stem=final_stem,
  )
  validate_or_raise(project_root)
  result["workRoot"] = str(transcript_paths.workRoot)
  result["structureMode"] = actual_mode
  result["taxonomyReviewDecision"] = str(analysis.get("decision", "skipped"))
  return result


def _require_path(value: str | None, label: str) -> Path:
  if not value:
    raise SystemExit(f"缺少参数: {label}")
  return Path(value).resolve()


def main() -> None:
  parser = argparse.ArgumentParser(description="transcribe-video 入库处理器")
  subparsers = parser.add_subparsers(dest="command")

  dry_run = subparsers.add_parser("dry-run")
  dry_run.add_argument("--project-root", required=True)

  run_cmd = subparsers.add_parser("run")
  run_cmd.add_argument("--project-root", required=True)
  run_cmd.add_argument("--input", required=True)
  run_cmd.add_argument("--language", default="zh-CN")
  run_cmd.add_argument("--structure-mode", choices=["deterministic", "assisted"], default="assisted")
  run_cmd.add_argument("--final-stem")
  run_cmd.add_argument("--taxonomy-review", choices=["off", "auto", "always"], default="auto")

  analyze_cmd = subparsers.add_parser("analyze")
  analyze_cmd.add_argument("--project-root", required=True)
  analyze_cmd.add_argument("--input-transcript", required=True)
  analyze_cmd.add_argument("--output")

  validate_cmd = subparsers.add_parser("validate")
  validate_cmd.add_argument("--project-root", required=True)

  args = parser.parse_args()
  if args.command == "dry-run":
    project_root = _require_path(args.project_root, "--project-root")
    errors = validate_project_structure(project_root)
    if errors:
      print("\n".join(errors), file=sys.stderr)
      raise SystemExit(3)
    paths = get_project_paths(project_root)
    print(json.dumps({
      "projectRoot": str(paths.projectRoot),
      "memorySourceRoot": str(paths.memorySourceRoot),
      "stagingRoot": str(paths.stagingRoot),
      "rawTranscriptRoot": str(paths.rawRoot / "03-transcripts"),
      "assetsTranscriptRoot": str(paths.assetsRoot / "raw" / "transcripts"),
    }, ensure_ascii=False))
    return
  if args.command == "validate":
    validate_or_raise(_require_path(args.project_root, "--project-root"))
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return
  if args.command == "analyze":
    project_root = _require_path(args.project_root, "--project-root")
    project_errors = validate_project_structure(project_root)
    if project_errors:
      print("\n".join(project_errors), file=sys.stderr)
      raise SystemExit(3)
    input_transcript = _require_path(args.input_transcript, "--input-transcript")
    output_path = Path(args.output).resolve() if args.output else input_transcript.with_name("analysis.json")
    result = analyze_segments_file(input_transcript, output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return
  if args.command == "run":
    result = run_pipeline(
      project_root=_require_path(args.project_root, "--project-root"),
      input_path=_require_path(args.input, "--input"),
      language=args.language,
      structure_mode=args.structure_mode,
      final_stem=args.final_stem,
      taxonomy_review=args.taxonomy_review,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return
  parser.print_help()
  raise SystemExit(1)


if __name__ == "__main__":
  main()

import unittest
import tempfile
from pathlib import Path
import sys
from importlib.util import spec_from_file_location, module_from_spec


_SKILL_ROOT = Path(__file__).resolve().parent.parent

# Dynamically load modules to avoid LSP import resolution issues
_output_contract_spec = spec_from_file_location(
  "scripts.output_contract",
  _SKILL_ROOT / "scripts" / "output_contract.py"
)
assert _output_contract_spec is not None and _output_contract_spec.loader is not None
_output_contract_module = module_from_spec(_output_contract_spec)
sys.modules["scripts.output_contract"] = _output_contract_module
_output_contract_spec.loader.exec_module(_output_contract_module)

DEGRADED_OCR_FALLBACK = _output_contract_module.DEGRADED_OCR_FALLBACK
build_artifacts_manifest = _output_contract_module.build_artifacts_manifest
build_normalized_envelope = _output_contract_module.build_normalized_envelope
get_document_root = _output_contract_module.get_document_root
get_normalized_dir = _output_contract_module.get_normalized_dir
get_normalized_images_dir = _output_contract_module.get_normalized_images_dir
get_normalized_json_path = _output_contract_module.get_normalized_json_path
get_normalized_markdown_path = _output_contract_module.get_normalized_markdown_path
get_raw_mineru_dir = _output_contract_module.get_raw_mineru_dir
get_raw_paddleocr_dir = _output_contract_module.get_raw_paddleocr_dir
validate_offline_reproducible = _output_contract_module.validate_offline_reproducible


class OutputContractTests(unittest.TestCase):
  def test_output_paths_contract(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      stem = "sample"

      self.assertEqual(
        get_document_root(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem,
      )
      self.assertEqual(
        get_normalized_dir(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "normalized",
      )
      self.assertEqual(
        get_normalized_markdown_path(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "normalized" / "document.md",
      )
      self.assertEqual(
        get_normalized_json_path(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "normalized" / "document.json",
      )
      self.assertEqual(
        get_normalized_images_dir(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "normalized" / "images",
      )
      self.assertEqual(
        get_raw_mineru_dir(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "raw" / "mineru",
      )
      self.assertEqual(
        get_raw_paddleocr_dir(output_dir=output_dir, stem=stem),
        output_dir / "document_parser_output" / stem / "raw" / "paddleocr",
      )

  def test_artifacts_manifest_relative_to_output_dir(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      stem = "a"
      artifacts = build_artifacts_manifest(output_dir=output_dir, stem=stem)

      self.assertIn(
        "document_parser_output/a/normalized/document.md",
        artifacts,
      )
      self.assertIn(
        "document_parser_output/a/normalized/document.json",
        artifacts,
      )
      self.assertIn(
        "document_parser_output/a/normalized/images",
        artifacts,
      )
      self.assertIn(
        "document_parser_output/a/raw/mineru",
        artifacts,
      )
      self.assertIn(
        "document_parser_output/a/raw/paddleocr",
        artifacts,
      )

      for item in artifacts:
        self.assertFalse(item.startswith(str(output_dir)))

  def test_envelope_min_fields(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      envelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="s",
        input_source="/tmp/in.pdf",
        backend="mineru",
        markdown="# Hello\n",
        fallback=True,
        warnings=[DEGRADED_OCR_FALLBACK],
        pages=None,
        extras={"vendor": "x"},
      )

      self.assertIn("meta", envelope)
      self.assertIn("markdown", envelope)
      self.assertIn("pages", envelope)
      self.assertIn("artifacts", envelope)
      self.assertIn("extras", envelope)

      meta = envelope["meta"]
      self.assertIn("input", meta)
      self.assertIn("backend", meta)
      self.assertIn("timestamp", meta)
      self.assertIn("fallback", meta)
      self.assertIn("warnings", meta)
      self.assertEqual(meta["warnings"], [DEGRADED_OCR_FALLBACK])

  def test_envelope_records_parse_metadata_without_moving_meta_or_raw_extras(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      envelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="s",
        input_source="/tmp/in.pdf",
        backend="mineru_v4",
        markdown="# Hello\n",
        fallback=False,
        warnings=[],
        pages=None,
        extras={"raw": [{"type": "p"}]},
        parseRequest={
          "requestedPageRange": "2-4",
          "providerPageRange": "2-4",
          "rangeSource": "provider-request",
          "disableFallback": True,
          "modelVersion": "vlm",
          "language": "ch",
          "isOcr": False,
          "enableTable": False,
          "enableFormula": True,
        },
        parseResult={
          "providerPageRange": "2-4",
          "taskId": "t1",
        },
      )

      self.assertEqual(envelope["meta"]["input"], "/tmp/in.pdf")
      self.assertEqual(envelope["meta"]["backend"], "mineru_v4")
      self.assertEqual(envelope["meta"]["fallback"], False)
      self.assertEqual(envelope["meta"]["warnings"], [])
      self.assertNotIn("parseRequest", envelope["meta"])
      self.assertNotIn("parseResult", envelope["meta"])
      self.assertEqual(envelope["extras"]["raw"], [{"type": "p"}])
      self.assertEqual(
        envelope["extras"]["parseRequest"],
        {
          "requestedPageRange": "2-4",
          "providerPageRange": "2-4",
          "rangeSource": "provider-request",
          "disableFallback": True,
          "modelVersion": "vlm",
          "language": "ch",
          "isOcr": False,
          "enableTable": False,
          "enableFormula": True,
        },
      )
      self.assertEqual(
        envelope["extras"]["parseResult"],
        {
          "providerPageRange": "2-4",
          "taskId": "t1",
        },
      )

  def test_degraded_ocr_fallback_warning_requires_real_fallback_flag(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      mineruEnvelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="mineru",
        input_source="/tmp/in.pdf",
        backend="mineru_v4",
        markdown="# MinerU\n",
        fallback=False,
        warnings=[],
        pages=None,
        extras={"raw": []},
        parseRequest={"disableFallback": True},
      )
      fallbackEnvelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="paddle",
        input_source="/tmp/in.pdf",
        backend="paddleocr_jobs",
        markdown="# Paddle\n",
        fallback=True,
        warnings=[DEGRADED_OCR_FALLBACK],
        pages=None,
        extras={"jobId": "j1"},
      )

      self.assertFalse(mineruEnvelope["meta"]["fallback"])
      self.assertNotIn(DEGRADED_OCR_FALLBACK, mineruEnvelope["meta"]["warnings"])
      self.assertEqual(mineruEnvelope["extras"]["parseRequest"], {"disableFallback": True})
      self.assertTrue(fallbackEnvelope["meta"]["fallback"])
      self.assertEqual(fallbackEnvelope["meta"]["warnings"], [DEGRADED_OCR_FALLBACK])

  def test_envelope_without_parse_metadata_preserves_extras_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      envelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="s",
        input_source="/tmp/in.pdf",
        backend="mineru_v4",
        markdown="# Hello\n",
        fallback=False,
        warnings=[],
        pages=None,
        extras={"raw": [{"type": "p"}]},
        parseRequest=None,
        parseResult=None,
      )

      self.assertNotIn("parseRequest", envelope["extras"])
      self.assertNotIn("parseResult", envelope["extras"])
      self.assertEqual(envelope["extras"]["raw"], [{"type": "p"}])

  def test_envelope_empty_parse_metadata_dicts_not_written(self):
    with tempfile.TemporaryDirectory() as tmp:
      output_dir = Path(tmp)
      envelope = build_normalized_envelope(
        output_dir=output_dir,
        stem="s",
        input_source="/tmp/in.pdf",
        backend="mineru_v4",
        markdown="# Hello\n",
        fallback=False,
        warnings=[],
        pages=None,
        extras={"raw": "x"},
        parseRequest={},
        parseResult={},
      )

      self.assertNotIn("parseRequest", envelope["extras"])
      self.assertNotIn("parseResult", envelope["extras"])
      self.assertEqual(envelope["extras"]["raw"], "x")

  def test_offline_reproducible_rejects_remote_images(self):
    with self.assertRaises(ValueError):
      validate_offline_reproducible("![x](https://example.com/a.png)")

    with self.assertRaises(ValueError):
      validate_offline_reproducible("![x](http://example.com/a.png)")

    validate_offline_reproducible("![x](images/a.png)")
    validate_offline_reproducible("[x](https://example.com/a.png)")


if __name__ == "__main__":
  unittest.main()

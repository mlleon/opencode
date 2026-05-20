import unittest
import tempfile
from pathlib import Path


from scripts.output_contract import (
  DEGRADED_OCR_FALLBACK,
  build_artifacts_manifest,
  build_normalized_envelope,
  get_document_root,
  get_normalized_dir,
  get_normalized_images_dir,
  get_normalized_json_path,
  get_normalized_markdown_path,
  get_raw_mineru_dir,
  get_raw_paddleocr_dir,
  validate_offline_reproducible,
)


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

  def test_offline_reproducible_rejects_remote_images(self):
    with self.assertRaises(ValueError):
      validate_offline_reproducible("![x](https://example.com/a.png)")

    with self.assertRaises(ValueError):
      validate_offline_reproducible("![x](http://example.com/a.png)")

    validate_offline_reproducible("![x](images/a.png)")
    validate_offline_reproducible("[x](https://example.com/a.png)")


if __name__ == "__main__":
  unittest.main()

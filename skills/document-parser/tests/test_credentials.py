import os
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import patch


class _CredentialsModule(Protocol):
  def getMinerUToken(self) -> str: ...

  def getPaddleOcrToken(self) -> str: ...


credentials = cast(_CredentialsModule, cast(object, import_module("scripts.credentials")))


class CredentialTests(unittest.TestCase):
  def test_mineru_uses_keys_file_even_when_env_is_set(self):
    with tempfile.TemporaryDirectory() as tmp:
      keysDir = Path(tmp) / ".config" / "opencode" / "keys"
      keysDir.mkdir(parents=True)
      _ = (keysDir / "mineru.key").write_text("file-token\n", encoding="utf-8")

      with patch.dict(os.environ, {"MINERU_TOKEN": "env-token"}, clear=False):
        with patch("scripts.credentials.Path.home", return_value=Path(tmp)):
          self.assertEqual(credentials.getMinerUToken(), "file-token")

  def test_reads_keys_file_and_strips_newline(self):
    with tempfile.TemporaryDirectory() as tmp:
      keysDir = Path(tmp) / ".config" / "opencode" / "keys"
      keysDir.mkdir(parents=True)
      _ = (keysDir / "paddleocr.key").write_text("paddle-token\n", encoding="utf-8")

      with patch.dict(os.environ, {}, clear=True):
        with patch("scripts.credentials.Path.home", return_value=Path(tmp)):
          self.assertEqual(credentials.getPaddleOcrToken(), "paddle-token")

  def test_missing_keys_file_raises_helpful_error(self):
    with tempfile.TemporaryDirectory() as tmp:
      with patch.dict(os.environ, {}, clear=True):
        with patch("scripts.credentials.Path.home", return_value=Path(tmp)):
          with self.assertRaises(ValueError) as context:
            _ = credentials.getMinerUToken()

      message = str(context.exception)
      self.assertIn(str(Path(tmp) / ".config" / "opencode" / "keys" / "mineru.key"), message)
      self.assertIn("MinerU 仅支持 keys 文件", message)

  def test_exception_message_does_not_leak_token(self):
    with tempfile.TemporaryDirectory() as tmp:
      keysDir = Path(tmp) / ".config" / "opencode" / "keys"
      keysDir.mkdir(parents=True)
      _ = (keysDir / "mineru.key").write_text("secret-token\n", encoding="utf-8")

      with patch.dict(os.environ, {}, clear=True):
        with patch("scripts.credentials.Path.home", return_value=Path(tmp)):
          self.assertEqual(credentials.getMinerUToken(), "secret-token")

      with patch.dict(os.environ, {}, clear=True):
        with patch("scripts.credentials.Path.home", return_value=Path(tmp)):
          with self.assertRaises(ValueError) as context:
            _ = credentials.getPaddleOcrToken()

      self.assertNotIn("secret-token", str(context.exception))


if __name__ == "__main__":
  _ = unittest.main()

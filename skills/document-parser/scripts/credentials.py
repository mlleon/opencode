from __future__ import annotations

import os
from pathlib import Path


PADDLEOCR_TOKEN_ENV = "PADDLEOCR_TOKEN"

MINERU_TOKEN_FILE_NAME = "mineru.key"
PADDLEOCR_TOKEN_FILE_NAME = "paddleocr.key"


def getMinerUToken() -> str:
  return _getTokenFromKeyFileOnly(
    keyFilePath=_getKeyFilePath(MINERU_TOKEN_FILE_NAME),
    providerName="MinerU",
  )


def getPaddleOcrToken() -> str:
  return _getToken(
    envName=PADDLEOCR_TOKEN_ENV,
    keyFilePath=_getKeyFilePath(PADDLEOCR_TOKEN_FILE_NAME),
  )


def _getToken(*, envName: str, keyFilePath: Path) -> str:
  envToken = os.environ.get(envName)
  if envToken:
    return envToken

  fileToken = _readTokenFromFile(keyFilePath)
  if fileToken:
    return fileToken

  raise ValueError(f"缺失凭据文件: {keyFilePath}，仅支持 env + keys 文件")


def _getTokenFromKeyFileOnly(*, keyFilePath: Path, providerName: str) -> str:
  fileToken = _readTokenFromFile(keyFilePath)
  if fileToken:
    return fileToken

  raise ValueError(f"缺失凭据文件: {keyFilePath}，{providerName} 仅支持 keys 文件")


def _readTokenFromFile(keyFilePath: Path) -> str | None:
  if not keyFilePath.exists() or not keyFilePath.is_file():
    return None

  token = keyFilePath.read_text(encoding="utf-8").strip()
  return token or None


def _getKeyFilePath(fileName: str) -> Path:
  return Path.home() / ".config" / "opencode" / "keys" / fileName

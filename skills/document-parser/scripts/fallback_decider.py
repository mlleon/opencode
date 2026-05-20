from __future__ import annotations

from importlib import import_module
from typing import Optional


errors = import_module("scripts.errors")


_MINERU_QUOTA_CODES = {-60018, -60019}
_MINERU_URL_ONLY_QUOTA_CODES = {-60022}
_AUTH_HTTP_STATUSES = {401, 403}


def isMinerUQuotaLikeError(err: object, source: str, stage: Optional[str] = "mineru") -> bool:
  normalized = errors.normalizeError(err, stage=stage)

  if normalized.httpStatus in _AUTH_HTTP_STATUSES:
    return False

  if normalized.code in _MINERU_QUOTA_CODES:
    return True

  if normalized.code in _MINERU_URL_ONLY_QUOTA_CODES:
    return _isUrlSource(source)

  return False


def _isUrlSource(source: str) -> bool:
  return isinstance(source, str) and source.startswith("http")

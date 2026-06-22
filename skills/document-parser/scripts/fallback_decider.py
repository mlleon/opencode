from __future__ import annotations

from importlib import import_module
from typing import Optional
import re


errors = import_module("scripts.errors")


_MINERU_QUOTA_CODES = {-60018, -60019}
_MINERU_URL_ONLY_QUOTA_CODES = {-60022}
_MINERU_PAGE_LIMIT_CODE = -60006
_AUTH_HTTP_STATUSES = {401, 403}
_PAGE_LIMIT_RE = re.compile(
  r"\bpages?\b.*\bexceed(?:s|ed)?\b.*\blimit\b|\bpage\s*count\b.*\bexceed(?:s|ed)?\b.*\blimit\b",
  re.IGNORECASE,
)


def isMinerUQuotaLikeError(err: object, source: str, stage: Optional[str] = "mineru") -> bool:
  normalized = errors.normalizeError(err, stage=stage)

  if normalized.httpStatus in _AUTH_HTTP_STATUSES:
    return False

  if isMinerUPageLimitError(normalized):
    return False

  if normalized.code in _MINERU_QUOTA_CODES:
    return True

  if normalized.code in _MINERU_URL_ONLY_QUOTA_CODES:
    return _isUrlSource(source)

  return False


def isMinerUPageLimitError(err: object, stage: Optional[str] = "mineru") -> bool:
  normalized = errors.normalizeError(err, stage=stage)
  if normalized.code == _MINERU_PAGE_LIMIT_CODE:
    return True

  messageParts = [normalized.msg, normalized.errMsg]
  message = " ".join(part for part in messageParts if part)
  if not message:
    return False
  return bool(_PAGE_LIMIT_RE.search(message))


def _isUrlSource(source: str) -> bool:
  return isinstance(source, str) and source.startswith("http")

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class NormalizedError:
  stage: Optional[str]
  httpStatus: Optional[int]
  code: Optional[int]
  msg: Optional[str]
  errMsg: Optional[str]


def normalizeError(err: object, stage: Optional[str] = None) -> NormalizedError:
  if isinstance(err, NormalizedError):
    if stage is None:
      return err
    return NormalizedError(
      stage=stage,
      httpStatus=err.httpStatus,
      code=err.code,
      msg=err.msg,
      errMsg=err.errMsg,
    )

  if isinstance(err, dict):
    http_status = _extractInt(err, ["httpStatus", "http_status", "status_code", "statusCode"])
    code = _extractInt(err, ["code", "errorCode", "err_code", "errCode"])
    msg = _extractStr(err, ["msg", "message"])
    err_msg = _extractStr(err, ["errMsg", "err_msg", "error", "detail", "raw"])
    return NormalizedError(
      stage=stage or _extractStr(err, ["stage"]),
      httpStatus=http_status,
      code=code,
      msg=msg,
      errMsg=err_msg,
    )

  if isinstance(err, BaseException):
    text = str(err)
    http_status = _extractHttpStatus(text)
    code = _extractCode(text)
    msg = _extractMsg(text)
    return NormalizedError(
      stage=stage,
      httpStatus=http_status,
      code=code,
      msg=msg,
      errMsg=text or None,
    )

  text = str(err)
  return NormalizedError(
    stage=stage,
    httpStatus=_extractHttpStatus(text),
    code=_extractCode(text),
    msg=_extractMsg(text),
    errMsg=text or None,
  )


def _extractInt(data: dict, keys: list[str]) -> Optional[int]:
  for key in keys:
    if key not in data:
      continue
    value = data.get(key)
    if isinstance(value, bool):
      continue
    if isinstance(value, int):
      return value
    if isinstance(value, str):
      value = value.strip()
      if value and re.fullmatch(r"[+-]?\d+", value):
        return int(value)
  return None


def _extractStr(data: dict, keys: list[str]) -> Optional[str]:
  for key in keys:
    if key not in data:
      continue
    value = data.get(key)
    if isinstance(value, str):
      stripped = value.strip()
      return stripped or None
  return None


def _extractHttpStatus(text: str) -> Optional[int]:
  if not text:
    return None
  match = re.search(r"\bHTTP\s+(\d{3})\b", text)
  if not match:
    return None
  return int(match.group(1))


def _extractCode(text: str) -> Optional[int]:
  if not text:
    return None
  match = re.search(r"\bcode=([+-]?\d+)\b", text)
  if not match:
    return None
  return int(match.group(1))


def _extractMsg(text: str) -> Optional[str]:
  if not text:
    return None
  match = re.search(r"\bmsg=([^,]+)", text)
  if not match:
    return None
  msg = match.group(1).strip()
  return msg or None

#!/usr/bin/env python3
import re
from pathlib import Path


def require_dict(value: object, label: str) -> dict[str, object]:
  if not isinstance(value, dict):
    raise ValueError(f"{label} 必须是对象")
  return value


def require_list(value: object, label: str) -> list[object]:
  if not isinstance(value, list):
    raise ValueError(f"{label} 必须是数组")
  return value


def _validate_evidence_items(
  value: object,
  label: str,
  source_text: str,
  valid_block_ids: set[str] | None,
) -> None:
  evidence_items = require_list(value, label)
  if not evidence_items:
    raise ValueError(f"{label} 缺少 evidence")
  for evidence in evidence_items:
    evidence_data = require_dict(evidence, label)
    text = evidence_data.get("text")
    start = evidence_data.get("start")
    end = evidence_data.get("end")
    block_id = evidence_data.get("blockId")
    if not isinstance(text, str) or not text.strip():
      raise ValueError(f"{label} evidence 缺少 text")
    if text.strip() not in source_text:
      raise ValueError(f"{label} evidence 不在原文中")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or float(end) < float(start):
      raise ValueError(f"{label} evidence 时间戳非法")
    if valid_block_ids is not None and (not isinstance(block_id, str) or block_id not in valid_block_ids):
      raise ValueError(f"{label} evidence blockId 非法")


def _validate_secondary_categories(value: object) -> None:
  categories = require_list(value, "assist.secondaryCategories")
  if len(categories) > 6:
    raise ValueError("assist.secondaryCategories 不能超过 6 个")
  seen: set[str] = set()
  for category in categories:
    if not isinstance(category, str) or not re.fullmatch(r"[a-z0-9_]{1,48}", category):
      raise ValueError(f"assist.secondaryCategories 格式非法: {category}")
    if category in seen:
      raise ValueError(f"assist.secondaryCategories 重复: {category}")
    seen.add(category)


def _validate_harness_payload(
  data: dict[str, object],
  valid_domain_ids: set[str],
  source_text: str,
  valid_block_ids: set[str] | None,
) -> None:
  primary = data.get("primaryCategory")
  if not isinstance(primary, str) or primary not in valid_domain_ids:
    raise ValueError(f"assist.primaryCategory 非法: {primary}")
  _validate_secondary_categories(data.get("secondaryCategories"))
  content_type = data.get("contentType")
  if not isinstance(content_type, str) or not content_type.strip():
    raise ValueError("assist.contentType 缺失")
  confidence = data.get("confidence")
  if not isinstance(confidence, (int, float)) or float(confidence) < 0 or float(confidence) > 1:
    raise ValueError("assist.confidence 必须在 0 到 1 之间")
  for field_name in ["topics", "keyPoints", "concepts", "quotes", "actionableInsights"]:
    items = require_list(data.get(field_name), f"assist.{field_name}")
    for index, item in enumerate(items):
      item_data = require_dict(item, f"assist.{field_name}[]")
      _validate_evidence_items(item_data.get("evidence"), f"assist.{field_name}[{index}]", source_text, valid_block_ids)
  require_list(data.get("openQuestions"), "assist.openQuestions")
  require_list(data.get("warnings"), "assist.warnings")
  if not isinstance(data.get("reviewRequired"), bool):
    raise ValueError("assist.reviewRequired 缺失")


def validate_assist_payload(
  payload: object,
  valid_domain_ids: set[str],
  source_text: str,
  valid_block_ids: set[str] | None = None,
) -> None:
  data = require_dict(payload, "assist")
  if "primaryCategory" in data:
    _validate_harness_payload(data, valid_domain_ids, source_text, valid_block_ids)
    return
  blocks = require_list(data.get("blocks"), "assist.blocks")
  for block in blocks:
    block_data = require_dict(block, "assist.blocks[]")
    block_id = block_data.get("blockId")
    if not isinstance(block_id, str) or not block_id.strip():
      raise ValueError("assist block 缺少 blockId")
    title = block_data.get("title")
    if not isinstance(title, str) or not title.strip():
      raise ValueError(f"assist block 缺少 title: {block_id}")
    domains = require_list(block_data.get("domains"), f"assist block domains: {block_id}")
    for domain in domains:
      if not isinstance(domain, str) or domain not in valid_domain_ids:
        raise ValueError(f"assist block 存在非法 domain: {domain}")
    evidence_items = require_list(block_data.get("evidence"), f"assist block evidence: {block_id}")
    if not evidence_items:
      raise ValueError(f"assist block 缺少 evidence: {block_id}")
    _validate_evidence_items(evidence_items, f"assist block evidence: {block_id}", source_text, None)
    review_required = block_data.get("reviewRequired")
    if not isinstance(review_required, bool):
      raise ValueError(f"assist block 缺少 reviewRequired: {block_id}")


def read_text_if_exists(path: Path) -> str:
  if not path.exists():
    return ""
  return path.read_text(encoding="utf-8")

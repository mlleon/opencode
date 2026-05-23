#!/usr/bin/env python3
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Domain:
  id: str
  name: str
  keywords: list[str]
  sections: list[str]
  description: str = ""
  secondaryHints: list[str] | None = None


@dataclass(frozen=True)
class Taxonomy:
  version: int
  domains: dict[str, Domain]
  creatorProfile: dict[str, object]

  @property
  def primaryCategories(self) -> dict[str, Domain]:
    return self.domains


def get_default_taxonomy_path() -> Path:
  return Path(__file__).resolve().parents[1] / "config" / "content_taxonomy.json"


def load_taxonomy(path: Path | None = None) -> Taxonomy:
  taxonomy_path = path or get_default_taxonomy_path()
  data = json.loads(taxonomy_path.read_text(encoding="utf-8"))
  version = int(data.get("version", 1))
  creator_profile = data.get("creatorProfile")
  raw_domains = data.get("primaryCategories") or data.get("domains")
  if not isinstance(raw_domains, dict):
    raise ValueError("taxonomy 配置缺少 primaryCategories")

  domains: dict[str, Domain] = {}
  for domain_id, item in raw_domains.items():
    if not isinstance(domain_id, str) or not domain_id:
      raise ValueError("taxonomy domain id 非法")
    if not isinstance(item, dict):
      raise ValueError(f"taxonomy domain 非法: {domain_id}")
    name = str(item.get("name", "")).strip()
    keywords = item.get("keywords", [])
    secondary_hints = item.get("secondaryHints", [])
    sections = item.get("sections", [])
    if not sections:
      sections = ["主题结构", "关键观点", "概念 / 术语", "重要原文摘录", "可行动洞察候选", "待确认问题"]
    if not name:
      raise ValueError(f"taxonomy domain 缺少 name: {domain_id}")
    if not isinstance(keywords, list) or not all(isinstance(value, str) for value in keywords):
      raise ValueError(f"taxonomy domain keywords 非法: {domain_id}")
    if not isinstance(secondary_hints, list) or not all(isinstance(value, str) for value in secondary_hints):
      raise ValueError(f"taxonomy domain secondaryHints 非法: {domain_id}")
    if not isinstance(sections, list) or not all(isinstance(value, str) for value in sections):
      raise ValueError(f"taxonomy domain sections 非法: {domain_id}")
    domains[domain_id] = Domain(
      id=domain_id,
      name=name,
      keywords=[value for value in keywords if value.strip()],
      sections=[value for value in sections if value.strip()],
      description=str(item.get("description", "")).strip(),
      secondaryHints=[value for value in secondary_hints if value.strip()],
    )

  if "generic" not in domains:
    raise ValueError("taxonomy 必须包含 generic 兜底领域")
  return Taxonomy(
    version=version,
    domains=domains,
    creatorProfile=creator_profile if isinstance(creator_profile, dict) else {},
  )


def require_domain_ids(taxonomy: Taxonomy, domain_ids: list[str]) -> None:
  for domain_id in domain_ids:
    if domain_id not in taxonomy.domains:
      raise ValueError(f"未知内容领域: {domain_id}")

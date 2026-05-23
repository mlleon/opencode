#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
  name: str
  provider: str
  baseUrl: str
  apiKeyFile: str
  model: str
  temperature: float
  timeoutSec: int


def get_default_llm_config_path() -> Path:
  return Path(__file__).resolve().parents[1] / "config" / "llm.json"


def load_llm_config(path: Path | None = None) -> dict[str, object]:
  config_path = path or get_default_llm_config_path()
  data = json.loads(config_path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError("llm 配置必须是对象")
  return data


def get_model_config(config: dict[str, object], name: str) -> ModelConfig:
  models = config.get("models")
  if not isinstance(models, dict):
    raise ValueError("llm 配置缺少 models")
  raw_model = models.get(name)
  if not isinstance(raw_model, dict):
    raise ValueError(f"llm 配置缺少模型: {name}")
  return ModelConfig(
    name=name,
    provider=str(raw_model.get("provider", "")),
    baseUrl=str(raw_model.get("baseUrl", "")).rstrip("/"),
    apiKeyFile=str(raw_model.get("apiKeyFile", "")),
    model=str(raw_model.get("model", "")),
    temperature=float(raw_model.get("temperature", 0.2)),
    timeoutSec=int(raw_model.get("timeoutSec", 90)),
  )


def read_api_key(config: ModelConfig) -> str | None:
  env_key = os.environ.get("TRANSCRIBE_VIDEO_LLM_API_KEY")
  if env_key:
    return env_key.strip()
  if not config.apiKeyFile:
    return None
  key_path = Path(config.apiKeyFile).expanduser()
  if not key_path.exists():
    return None
  content = key_path.read_text(encoding="utf-8").strip()
  if not content:
    return None
  if "=" in content:
    key, value = content.split("=", 1)
    if key.strip() in {"TRANSCRIBE_VIDEO_LLM_API_KEY", "OPENAI_API_KEY", "NVIDIA_API_KEY"}:
      return value.strip()
  return content


def call_openai_compatible(config: ModelConfig, system_prompt: str, user_prompt: str) -> str:
  api_key = read_api_key(config)
  if not api_key:
    raise RuntimeError(f"缺少 LLM API key: {config.apiKeyFile}")
  if not config.baseUrl or not config.model:
    raise RuntimeError(f"LLM 模型配置不完整: {config.name}")

  payload = {
    "model": config.model,
    "temperature": config.temperature,
    "messages": [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": user_prompt},
    ],
  }
  request = urllib.request.Request(
    f"{config.baseUrl}/chat/completions",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={
      "Authorization": f"Bearer {api_key}",
      "Content-Type": "application/json",
    },
    method="POST",
  )
  try:
    with urllib.request.urlopen(request, timeout=config.timeoutSec) as response:
      response_data = json.loads(response.read().decode("utf-8"))
  except urllib.error.URLError as exc:
    raise RuntimeError(f"LLM 调用失败: {exc}") from exc
  if not isinstance(response_data, dict):
    raise RuntimeError("LLM 返回非对象响应")
  choices = response_data.get("choices")
  if not isinstance(choices, list) or not choices:
    raise RuntimeError("LLM 返回缺少 choices")
  first = choices[0]
  if not isinstance(first, dict):
    raise RuntimeError("LLM choices 格式非法")
  message = first.get("message")
  if not isinstance(message, dict):
    raise RuntimeError("LLM message 格式非法")
  content = message.get("content")
  if not isinstance(content, str) or not content.strip():
    raise RuntimeError("LLM 返回空内容")
  return content.strip()


def extract_json_object(content: str) -> dict[str, object]:
  stripped = content.strip()
  if stripped.startswith("```"):
    stripped = stripped.strip("`")
    if stripped.startswith("json"):
      stripped = stripped[4:].strip()
  start = stripped.find("{")
  end = stripped.rfind("}")
  if start < 0 or end < start:
    raise ValueError("LLM 输出中未找到 JSON 对象")
  data = json.loads(stripped[start:end + 1])
  if not isinstance(data, dict):
    raise ValueError("LLM JSON 输出必须是对象")
  return data

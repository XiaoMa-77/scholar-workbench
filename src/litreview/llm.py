"""Optional OpenAI-compatible LLM client; entirely off unless configured.

Config file: ``~/.litreview/config.json``::

    {"base_url": "https://api.example.com/v1",
     "api_key": "sk-...",
     "model": "gpt-4o-mini"}

All survey features work without this file.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".litreview" / "config.json"


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        import httpx
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def llm_from_config(path: str | Path | None = None) -> LLMClient | None:
    if path is None:
        from arxiv_digest.llm import load_credentials
        credentials = load_credentials()
        if credentials is None:
            return None
        return LLMClient(credentials.base_url, credentials.api_key, credentials.model)
    config = load_config(path)
    if not all(config.get(key) for key in ("base_url", "api_key", "model")):
        return None
    return LLMClient(config["base_url"], config["api_key"], config["model"])

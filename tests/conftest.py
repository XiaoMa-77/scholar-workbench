"""Prevent offline tests from reading real local credentials."""

import pytest


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch, tmp_path):
    from arxiv_digest import llm
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    monkeypatch.setattr(llm, "LEGACY_CONFIG_PATH", tmp_path / "legacy-llm.json")

"""桌面桥接层测试：行数据组装、多来源参数与 LLM 配置，全部离线。"""

import json
from datetime import datetime

from arxiv_digest.desktop import DesktopAPI, build_rows
from arxiv_digest.fetcher import Paper, parse_atom
from arxiv_digest.impact import ImpactInfo

from fixtures_atom import ATOM_FIXTURE


def _papers():
    return parse_atom(ATOM_FIXTURE)


def test_build_rows_merges_relevance_and_impact():
    """行数据应包含规则分、影响力字段；无影响力数据时为 None 而非报错。"""
    lookup = {"2610.10001": ImpactInfo(citations=57, influential=8,
                                       venue="CVPR 2025", year=2025)}
    rows = build_rows(_papers(), ["vision-language", "diffusion"],
                      use_llm=False, limit=10, impact_lookup=lookup)
    assert len(rows) == 3
    top = rows[0]
    assert top["title"].startswith("Vision-Language")
    assert top["citations"] == 57
    assert top["venue"] == "CVPR 2025"
    assert top["impact_score"] is not None
    assert top["matched"]  # 命中关键词非空
    assert top["source"] == "arxiv" and top["source_label"] == "arXiv 预印本"
    # 无 S2 记录的论文：影响力字段优雅降级
    assert rows[1]["citations"] is None
    assert rows[1]["impact_score"] is None


def test_build_rows_uses_inline_openalex_impact():
    """OpenAlex 论文自带引用数：无需外部查询即可构造影响力。"""
    journal = Paper("", "Journal Paper", ["A"], "about robot navigation", [],
                    datetime(2026, 5, 1), "https://doi.org/10.1000/x",
                    source="openalex", doi="10.1000/x", citations=123,
                    venue="IEEE Transactions on Robotics")
    rows = build_rows([journal], ["robot"], use_llm=False, limit=5,
                      impact_lookup={})
    assert rows[0]["source"] == "openalex"
    assert rows[0]["source_label"] == "期刊/会议"
    assert rows[0]["citations"] == 123
    assert rows[0]["venue"] == "IEEE Transactions on Robotics"
    assert rows[0]["impact_score"] is not None


def test_build_rows_sorts_mixed_sources():
    """arXiv（带时区）与 OpenAlex 时间混排排序不应抛 offset 比较异常。"""
    from datetime import timezone

    journal = Paper("", "Journal Paper", ["A"], "about vision", [],
                    datetime(2026, 5, 1, tzinfo=timezone.utc),
                    "https://doi.org/10.1000/x", source="openalex",
                    citations=5, venue="Nature")
    mixed = _papers() + [journal]  # ATOM fixture 解析出的都是带 UTC 时区的时间
    rows = build_rows(mixed, ["vision"], use_llm=False, limit=10, impact_lookup={})
    assert len(rows) == len(mixed)


def test_build_rows_respects_limit():
    rows = build_rows(_papers(), ["translation"], use_llm=False, limit=1, impact_lookup={})
    assert len(rows) == 1


def test_api_search_end_to_end(monkeypatch):
    """DesktopAPI.search 全流程（mock 网络层）：正常返回 JSON 行数据与来源计数。"""
    from arxiv_digest import desktop

    monkeypatch.setattr(desktop, "search_all",
                        lambda q, cats, limit, days, source, venues_only: _papers())
    monkeypatch.setattr(desktop, "fetch_impact", lambda ids: {})
    monkeypatch.setattr(desktop, "load_credentials", lambda: None)
    api = DesktopAPI()
    data = json.loads(api.search("vision-language", '["cs.CV"]', 3, "0", False))
    assert data["ok"] is True
    assert len(data["rows"]) == 3
    assert data["impact_available"] is False
    assert data["counts"] == {"arxiv": 3, "openalex": 0}

    # 新签名：source / venues_only 透传
    captured = {}
    monkeypatch.setattr(
        desktop, "search_all",
        lambda q, cats, limit, days, source, venues_only:
            captured.update(source=source, venues_only=venues_only) or _papers())
    api.search("x", "[]", 5, "0", False, "openalex", True)
    assert captured == {"source": "openalex", "venues_only": True}


def test_api_search_error_is_readable(monkeypatch):
    """网络异常应返回 ok=False 与可读错误，而不是抛栈。"""
    from arxiv_digest import desktop

    def boom(*a, **k):
        raise OSError("connection reset")

    monkeypatch.setattr(desktop, "search_all", boom)
    api = DesktopAPI()
    data = json.loads(api.search("x", "[]", 5, "0", False))
    assert data["ok"] is False
    assert "connection reset" in data["error"]


def test_llm_config_roundtrip(monkeypatch, tmp_path):
    """设置弹窗：保存 → 回显（脱敏）→ 可用性刷新。"""
    from arxiv_digest import desktop
    from arxiv_digest import llm

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    monkeypatch.setattr(desktop, "load_credentials", llm.load_credentials)

    api = DesktopAPI()
    assert json.loads(api.llm_config())["configured"] is False
    assert json.loads(api.llm_available())["available"] is False

    saved = json.loads(api.save_llm_config("sk-1234567890abcdef",
                                           "https://api.example.com/v1/", "m1"))
    assert saved["ok"] is True
    cfg = json.loads(api.llm_config())
    assert cfg["configured"] is True
    assert cfg["base_url"] == "https://api.example.com/v1"
    assert cfg["model"] == "m1"
    assert "sk-1234567890abcdef" not in cfg["api_key_masked"]  # 不回显完整 Key
    assert json.loads(api.llm_available())["available"] is True


def test_export_csv_includes_source_column():
    api = DesktopAPI()
    rows = [{
        "title": "T", "authors": ["A", "..."], "published": "2026-10-01",
        "categories": ["cs.CV"], "source_label": "期刊/会议", "score": 3.0,
        "llm_score": None, "citations": 5, "influential": None, "venue": "Nature",
        "impact_score": 2.0, "link": "https://doi.org/10.1/x",
    }]
    csv_text = api.export_csv(json.dumps(rows))
    assert "来源" in csv_text.splitlines()[0]
    assert "期刊/会议" in csv_text
    assert "Nature" in csv_text

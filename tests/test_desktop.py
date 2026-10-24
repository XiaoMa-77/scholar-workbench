"""桌面桥接层测试：行数据组装（相关度 + 影响力合并）与降级路径。"""

import json

from arxiv_digest.desktop import DesktopAPI, build_rows
from arxiv_digest.impact import ImpactInfo

from fixtures_atom import ATOM_FIXTURE

from arxiv_digest.fetcher import parse_atom


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
    # 无 S2 记录的论文：影响力字段优雅降级
    assert rows[1]["citations"] is None
    assert rows[1]["impact_score"] is None


def test_build_rows_respects_limit():
    rows = build_rows(_papers(), ["translation"], use_llm=False, limit=1, impact_lookup={})
    assert len(rows) == 1


def test_api_search_end_to_end(monkeypatch, tmp_path):
    """DesktopAPI.search 全流程（mock 网络层）：正常返回 JSON 行数据。"""
    from arxiv_digest import desktop

    monkeypatch.setattr(desktop, "search_papers",
                        lambda q, cats, limit, days, **kw: _papers())
    monkeypatch.setattr(desktop, "fetch_impact", lambda ids: {})
    monkeypatch.setattr(desktop, "load_credentials", lambda: None)
    api = DesktopAPI()
    data = json.loads(api.search("vision-language", '["cs.CV"]', 3, "0", False))
    assert data["ok"] is True
    assert len(data["rows"]) == 3
    assert data["impact_available"] is False


def test_api_search_error_is_readable(monkeypatch):
    """网络异常应返回 ok=False 与可读错误，而不是抛栈。"""
    from arxiv_digest import desktop

    def boom(*a, **k):
        raise OSError("connection reset")

    monkeypatch.setattr(desktop, "search_papers", boom)
    api = DesktopAPI()
    data = json.loads(api.search("x", "[]", 5, "0", False))
    assert data["ok"] is False
    assert "connection reset" in data["error"]

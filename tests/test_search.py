"""检索层测试：查询串构造、检索词解析与日期过滤。"""

import io
from datetime import date, datetime


from arxiv_digest.fetcher import Paper
from arxiv_digest.search import build_query, parse_terms, search_papers


def test_parse_terms_supports_phrases_and_separators():
    """引号短语保持完整，其余按空格/逗号/中文逗号切分。"""
    terms = parse_terms('vision-language "embodied ai"，导航; 3D')
    assert terms == ["vision-language", "embodied ai", "导航", "3D"]


def test_build_query_and_semantics():
    """多词取 AND、多分类取 OR，并用括号分组。"""
    q = build_query(["nav", "llm"], ["cs.CV", "cs.RO"])
    assert q == '(cat:cs.CV OR cat:cs.RO) AND (all:"nav" AND all:"llm")'
    assert build_query(["nav"], []) == 'all:"nav"'
    assert build_query([], ["cs.CV"]) == "cat:cs.CV"


def _fake_papers():
    return [
        Paper("2610.1v1", "Old", ["A"], "abs", ["cs.CV"], datetime(2026, 8, 1), "l1"),
        Paper("2610.2v1", "New", ["B"], "abs", ["cs.CV"], datetime(2026, 10, 20), "l2"),
    ]


def test_search_filters_by_days(monkeypatch):
    """days 窗口只保留最近发表的论文。"""
    captured = {}

    class FakeResponse(io.BytesIO):
        pass

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(b"<feed/>")

    monkeypatch.setattr("arxiv_digest.search.urllib.request.urlopen", fake_urlopen)
    papers = search_papers("nav", ["cs.CV"], limit=5, days=30,
                           today=date(2026, 10, 24))
    # feed 无 entry，仅验证请求参数与过滤路径不报错
    assert papers == []
    assert "sortBy=relevance" in captured["url"]

    # 直接验证过滤逻辑：注入 parse_atom 结果
    monkeypatch.setattr("arxiv_digest.search.parse_atom", lambda _t: _fake_papers())
    papers = search_papers("nav", [], limit=5, days=30, today=date(2026, 10, 24))
    assert [p.arxiv_id for p in papers] == ["2610.2v1"]
    # days=None 表示不限时间
    papers = search_papers("nav", [], limit=5, days=None, today=date(2026, 10, 24))
    assert len(papers) == 2


def test_search_limit_clamped(monkeypatch):
    """limit 被夹在 1~300。"""

    def fake_urlopen(request, timeout=None):
        assert "max_results=300" in request.full_url
        return io.BytesIO(b"<feed/>")

    monkeypatch.setattr("arxiv_digest.search.urllib.request.urlopen", fake_urlopen)
    search_papers("x", [], limit=9999)

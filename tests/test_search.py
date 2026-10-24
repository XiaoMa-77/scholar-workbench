"""检索层测试：查询串构造、检索词解析、日期过滤与多源合并去重。"""

import io
from datetime import date, datetime

from arxiv_digest.fetcher import Paper
from arxiv_digest.search import (
    _merge_sources,
    build_query,
    parse_terms,
    search_all,
    search_papers,
)


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


def _arxiv_paper(arxiv_id="2610.1v1", title="Robot Navigation Study"):
    return Paper(arxiv_id, title, ["A"], "abs robot navigation", ["cs.RO"],
                 datetime(2026, 10, 1), f"http://arxiv.org/abs/{arxiv_id}")


def _oa_paper(title, venue="ICRA", cited=10, doi="10.1100/x"):
    return Paper("", title, ["B"], "abs", [], datetime(2026, 9, 1),
                 f"https://doi.org/{doi}", source="openalex", doi=doi,
                 citations=cited, venue=venue)


def test_merge_sources_dedupes_by_arxiv_doi():
    """OpenAlex 的 arXiv DOI 记录与 arXiv 记录同文：合并引用/venue 后丢弃重复。"""
    arxiv_p = _arxiv_paper("2610.1v1", "Attention Is All You Need")
    twin = _oa_paper("Attention Is All You Need", venue="NeurIPS", cited=90000,
                     doi="10.48550/arxiv.2610.1")
    unique = _oa_paper("A Journal Paper", venue="Nature", cited=5, doi="10.1000/a")
    merged = _merge_sources([arxiv_p, twin, unique])
    assert merged == [arxiv_p, unique]
    assert arxiv_p.citations == 90000
    assert arxiv_p.venue == "NeurIPS"


def test_merge_sources_dedupes_by_normalized_title():
    """无 DOI 对应时按归一化标题去重（大小写/标点差异不敏感）。"""
    arxiv_p = _arxiv_paper("2610.2v1", "VLA Robots: A Survey!")
    twin = _oa_paper("vla robots a survey", venue="IJRR", cited=3, doi="10.1000/b")
    merged = _merge_sources([arxiv_p, twin])
    assert merged == [arxiv_p]
    assert arxiv_p.venue == "IJRR"


def test_search_all_dispatches_by_source(monkeypatch):
    """source 决定调用哪些来源；venues_only 只传给 OpenAlex。"""
    calls = {}

    def fake_arxiv(query, categories, limit, days, **kw):
        calls["arxiv"] = (query, categories, limit, days)
        return [_arxiv_paper()]

    def fake_openalex(terms, limit, days, today, venues_only, timeout):
        calls["openalex"] = (terms, limit, days, venues_only)
        return [_oa_paper("Journal Version")]

    from arxiv_digest import search as search_mod
    monkeypatch.setattr(search_mod, "search_papers", fake_arxiv)
    monkeypatch.setattr(search_mod, "search_openalex", fake_openalex)

    papers = search_all("robot navigation", ["cs.RO"], limit=10, source="all",
                        venues_only=True)
    assert len(papers) == 2
    assert set(calls) == {"arxiv", "openalex"}
    assert calls["openalex"][3] is True

    calls.clear()
    papers = search_all("robot navigation", ["cs.RO"], limit=10, source="arxiv")
    assert list(calls) == ["arxiv"]
    assert len(papers) == 1 and papers[0].source == "arxiv"

    calls.clear()
    papers = search_all("robot navigation", [], limit=10, source="openalex")
    assert list(calls) == ["openalex"]
    assert papers[0].source == "openalex"


def test_search_all_tolerates_single_source_failure(monkeypatch):
    """合并模式下单个来源失败（如 arXiv 偶发 503）不拖垮整个检索。"""
    from arxiv_digest import search as search_mod

    def boom(query, categories, limit, days, **kw):
        raise OSError("arXiv 503")

    monkeypatch.setattr(search_mod, "search_papers", boom)
    monkeypatch.setattr(search_mod, "search_openalex",
                        lambda terms, limit, days, today, venues_only, timeout:
                            [_oa_paper("Journal Paper")])
    papers = search_all("robot", [], limit=10, source="all")
    assert len(papers) == 1 and papers[0].source == "openalex"

    # 单来源模式失败则原样抛出（由桌面层转成可读错误）
    import pytest
    with pytest.raises(OSError):
        search_all("robot", [], limit=10, source="arxiv")

    # 两个来源都失败时抛出汇总错误
    monkeypatch.setattr(search_mod, "search_openalex",
                        lambda terms, limit, days, today, venues_only, timeout:
                            (_ for _ in ()).throw(OSError("oa down")))
    with pytest.raises(OSError, match="全部检索来源失败"):
        search_all("robot", [], limit=10, source="all")

"""Atom XML 解析测试：用内嵌 fixture 验证字段解析与日期过滤。"""

import io
from datetime import date

from arxiv_digest import fetcher
from arxiv_digest.fetcher import build_search_query, parse_atom

from fixtures_atom import ATOM_FIXTURE


def test_parse_atom_entry_count_and_fields():
    """解析 3 篇假论文，逐字段核对 id、标题、作者、分类、日期与链接。"""
    papers = parse_atom(ATOM_FIXTURE)
    assert len(papers) == 3

    first = papers[0]
    assert first.arxiv_id == "2610.10001v1"
    # 标题中的换行与缩进应被压成单行
    assert first.title == "Vision-Language Diffusion Models for 3D Scene Understanding"
    assert first.abstract.startswith("We propose a diffusion framework")
    assert first.abstract.endswith("3D scene understanding.")
    assert first.authors == ["Alice Chen", "Bob Wang", "Carol Li", "David Zhang"]
    assert first.categories == ["cs.CV", "cs.CL"]
    assert first.published.date() == date(2026, 10, 23)
    assert first.link == "http://arxiv.org/abs/2610.10001v1"

    second = papers[1]
    assert second.arxiv_id == "2610.10002v1"
    assert second.categories == ["cs.CL"]
    assert second.published.date() == date(2026, 10, 22)

    third = papers[2]
    # 5 位作者，验证多作者条目
    assert len(third.authors) == 5
    assert third.categories == ["cs.RO", "cs.CV"]


def test_build_search_query():
    """分类列表应拼成 cat:xxx OR cat:yyy 查询串。"""
    assert build_search_query(["cs.CV", "cs.CL"]) == "cat:cs.CV OR cat:cs.CL"
    assert build_search_query([" cs.RO "]) == "cat:cs.RO"


def test_fetch_papers_filters_by_date(monkeypatch):
    """fetch_papers 应只保留发表日期落在窗口内的论文（网络用假响应替代）。"""
    monkeypatch.setattr(
        fetcher.urllib.request,
        "urlopen",
        lambda req, timeout=None: io.BytesIO(ATOM_FIXTURE.encode("utf-8")),
    )
    papers = fetcher.fetch_papers(["cs.CV"], date(2026, 10, 23), date(2026, 10, 23))
    assert [p.arxiv_id for p in papers] == ["2610.10001v1", "2610.10003v1"]

    papers_all = fetcher.fetch_papers(["cs.CV"], date(2026, 10, 22), date(2026, 10, 23))
    assert len(papers_all) == 3

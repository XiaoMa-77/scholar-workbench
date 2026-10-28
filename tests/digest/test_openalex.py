"""OpenAlex 层测试：响应解析、AND 过滤、顶刊过滤与批量影响力，全部离线。"""

from datetime import date

from arxiv_digest import openalex
from arxiv_digest.openalex import (
    _abstract_from_inverted,
    _to_paper,
    fetch_impact_openalex,
    search_openalex,
)


def _work(title="Sample Paper", venue="Nature", cited=42, abstract_words=None,
          doi="10.1000/demo", pub_date="2026-05-01"):
    inverted = {}
    default_words = ["robot", "learning"]
    for i, word in enumerate(abstract_words if abstract_words is not None else default_words):
        inverted[word] = [i]
    return {
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/{doi}",
        "display_name": title,
        "authorships": [{"author": {"display_name": "Alice"}}, {"author": {"display_name": "Bob"}}],
        "publication_year": int(pub_date[:4]),
        "publication_date": pub_date,
        "primary_location": {"source": {"display_name": venue} if venue else None},
        "cited_by_count": cited,
        "abstract_inverted_index": inverted,
    }


def test_abstract_reconstruction():
    text = _abstract_from_inverted({"world": [1], "hello": [0]})
    assert text == "hello world"
    assert _abstract_from_inverted(None) == ""
    assert _abstract_from_inverted({}) == ""


def test_to_paper_maps_fields():
    paper = _to_paper(_work(venue="IEEE Transactions on Robotics", doi="10.1100/tro"))
    assert paper.source == "openalex"
    assert paper.arxiv_id == ""
    assert paper.title == "Sample Paper"
    assert paper.authors == ["Alice", "Bob"]
    assert paper.venue == "IEEE Transactions on Robotics"
    assert paper.doi == "10.1100/tro"
    assert paper.link == "https://doi.org/10.1100/tro"
    assert paper.citations == 42
    assert paper.abstract == "robot learning"
    assert paper.published.year == 2026


def test_search_filters_terms_and_venues(monkeypatch):
    """arXiv 预印本条目剔除 + 多词 AND 过滤 + 顶刊过滤。"""
    captured = {}

    def fake_get_json(params, timeout=None):
        captured["params"] = params
        return {"results": [
            _work(title="Robot Grasping with Language Models",  # 命中两词
                  abstract_words=["robot", "grasping", "language"], venue="ICRA"),
            _work(title="Only Robot Paper",  # 缺 language → 被 AND 过滤
                  abstract_words=["robot"], venue="ICRA"),
            _work(title="Language Robot Survey but not top venue",  # 顶刊过滤应剔除
                  abstract_words=["language", "robot"], venue="IEEE Access"),
            _work(title="Robot Language Preprint",  # venue 是 arXiv 本身 → 剔除
                  abstract_words=["robot", "language"], venue="arXiv (Cornell University)"),
        ]}

    monkeypatch.setattr(openalex, "_get_json", fake_get_json)
    papers = search_openalex(["robot", "language"], limit=10, venues_only=True,
                             days=None)
    assert len(papers) == 1
    assert papers[0].venue == "ICRA"
    assert "search" in captured["params"]


def test_search_skips_arxiv_venue_without_top_filter(monkeypatch):
    """即便不开顶刊过滤，venue 为 arXiv 的预印本条目也不算期刊/会议论文。"""
    monkeypatch.setattr(openalex, "_get_json", lambda params, timeout=None: {"results": [
        _work(title="Journal Robot", venue="Advanced Robotics"),
        _work(title="Preprint Robot", venue="arXiv (Cornell University)"),
    ]})
    papers = search_openalex(["robot"], limit=10)
    assert [p.title for p in papers] == ["Journal Robot"]


def test_search_applies_from_publication_date(monkeypatch):
    captured = {}

    def fake_get_json(params, timeout=None):
        captured["params"] = params
        return {"results": []}

    monkeypatch.setattr(openalex, "_get_json", fake_get_json)
    search_openalex(["nav"], limit=5, days=30, today=date(2026, 10, 24))
    assert captured["params"]["filter"] == "from_publication_date:2026-09-24"


def test_fetch_impact_openalex_chunks_and_maps(monkeypatch):
    """DOI 过滤分片批量查询，结果按 arXiv 编号映射。"""
    chunks = []

    def fake_get_json(params, timeout=None):
        dois = params["filter"].split("doi:", 1)[1].split("|")
        chunks.append(len(dois))
        return {"results": [
            {"doi": f"https://doi.org/{d}",
             "cited_by_count": 7 * (i + 1),
             "publication_year": 2025,
             "primary_location": {"source": {"display_name": "CVPR"}}}
            for i, d in enumerate(dois)
        ]}

    monkeypatch.setattr(openalex, "_get_json", fake_get_json)
    ids = [f"2610.{i}" for i in range(45)]  # 超过单片上限，验证分片
    result = fetch_impact_openalex(ids)
    assert sum(chunks) == 45
    assert all(n <= openalex.FILTER_CHUNK for n in chunks)
    assert len(result) == 45
    assert result["2610.0"] == {"citations": 7, "venue": "CVPR", "year": 2025}
    assert result["2610.44"]["citations"] == 35  # 第三片第 5 条（7×5）

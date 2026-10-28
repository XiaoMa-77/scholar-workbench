"""End-to-end agent test with mocked HTTP and a synthetic cached PDF."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from litreview.agent import LitReviewAgent
from litreview.sources import ArxivSource, OpenAlexSource

FIXTURES = Path(__file__).parent / "fixtures"


def arxiv_fixture_client() -> httpx.Client:
    atom = (FIXTURES / "arxiv_atom.xml").read_bytes()
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=atom)))


def openalex_fixture_client() -> httpx.Client:
    payload = (FIXTURES / "openalex_works.json").read_bytes()
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=payload,
                                       headers={"content-type": "application/json"})))


def make_agent(tmp_path: Path, *, openalex: bool) -> LitReviewAgent:
    return LitReviewAgent(
        cache_dir=tmp_path / "cache",
        arxiv=ArxivSource(client=arxiv_fixture_client()),
        openalex=OpenAlexSource(client=openalex_fixture_client()) if openalex else None,
        use_openalex=openalex,
        use_llm=False)


def test_run_offline_with_cached_pdf(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, openalex=True)
    papers = agent.search("vision transformer", limit=2)
    assert len(papers) == 2
    merged = {p.id: p for p in papers}
    assert merged["2010.11929"].citations == 30111  # enriched by openalex fixture

    # Drop a synthetic PDF into the cache, then run fully offline.
    import zlib
    import struct

    width, height = 200, 120
    raw = b"".join(b"\x20\x80\x40" * width for _ in range(height))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Attention paper full text about transformers.")
    page.insert_image(fitz.Rect(72, 120, 272, 240), stream=png)
    page.insert_text((72, 255), "Figure 2: Model architecture diagram.")
    doc.save(tmp_path / "cache" / "1706.03762.pdf")
    doc.close()

    result = agent.run("vision transformer", limit=2, out_dir=tmp_path / "out",
                       offline=True)
    assert result.source_errors == []
    assert len(result.papers) == 2
    assert "1706.03762" in result.contents
    assert result.contents["1706.03762"].figure_count == 1
    assert "## 横向对比" in result.survey_md
    report = Path(result.report_path)
    assert report.is_file() and report.stat().st_size > 500
    papers_json = json.loads((tmp_path / "out" / "papers.json").read_text("utf-8"))
    assert {p["id"] for p in papers_json} == {"2010.11929", "1706.03762"}


def test_run_offline_without_cache_reports_pdf_errors(tmp_path):
    agent = make_agent(tmp_path, openalex=False)
    agent.search("vision transformer", limit=2)  # cache metadata before disconnecting
    result = agent.run("vision transformer", limit=2, out_dir=tmp_path / "out2",
                       offline=True)
    assert len(result.papers) == 2
    assert result.contents == {}
    assert len(result.pdf_errors) == 2
    assert "not cached" in result.pdf_errors[0]
    assert "## 论文卡片" in result.survey_md


def test_search_openalex_failure_degrades(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(429)

    monkeypatch.setattr("litreview.sources.time.sleep", lambda s: None)
    failing = OpenAlexSource(client=httpx.Client(
        transport=httpx.MockTransport(handler)), retries=1)
    agent = LitReviewAgent(cache_dir=tmp_path / "cache2",
                           arxiv=ArxivSource(client=arxiv_fixture_client()),
                           openalex=failing, use_openalex=True, use_llm=False)
    papers = agent.search("vision transformer", limit=2)
    assert len(papers) == 2  # arxiv-only result

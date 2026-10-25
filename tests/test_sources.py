"""Offline source tests via httpx.MockTransport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from litreview.models import Paper
from litreview.sources import (ArxivSource, OpenAlexSource, SourceError,
                               invert_abstract, merge_papers,
                               normalize_arxiv_id)

FIXTURES = Path(__file__).parent / "fixtures"


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), headers={})


class TestArxiv:
    def test_parse_fixture(self):
        xml = (FIXTURES / "arxiv_atom.xml").read_text(encoding="utf-8")
        papers = ArxivSource._parse(xml)
        assert len(papers) == 2
        first = papers[0]
        assert first.id == "2010.11929"
        assert first.year == 2020
        assert first.pdf_url == "https://arxiv.org/pdf/2010.11929"
        assert first.primary_category == "cs.CV"
        assert "ViT" in first.abstract or "Vision Transformer" in first.abstract
        assert first.authors == ["Alexey Dosovitskiy", "Lucas Beyer"]

    def test_search_retries_then_raises(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(500)

        with mock_client(handler) as client, pytest.raises(SourceError):
            ArxivSource(client=client, retries=1).search("transformer", 5)
        assert calls["n"] == 2

    def test_normalize_arxiv_id(self):
        assert normalize_arxiv_id("http://arxiv.org/abs/1706.03762v7") == "1706.03762"
        assert normalize_arxiv_id("arxiv:2010.11929v2") == "2010.11929"


class TestOpenAlex:
    def test_parse_fixture(self):
        payload = json.loads((FIXTURES / "openalex_works.json").read_text("utf-8"))
        papers = OpenAlexSource._parse(payload)
        assert len(papers) == 3
        vit = papers[0]
        assert vit.id == "2010.11929"
        assert vit.citations == 30111
        assert vit.doi == "10.48550/arXiv.2010.11929"
        assert vit.pdf_url == "https://arxiv.org/pdf/2010.11929"
        assert vit.abstract.startswith("The Transformer architecture dominates")

    def test_empty_paper_without_title_is_dropped(self):
        payload = {"results": [{"display_name": "", "id": "https://openalex.org/W1"}]}
        assert OpenAlexSource._parse(payload) == []

    def test_429_retries_with_backoff(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr("litreview.sources.time.sleep", sleeps.append)
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429)
            return httpx.Response(200, json={"results": []})

        with mock_client(handler) as client:
            papers = OpenAlexSource(client=client, retries=3).search("x", 3)
        assert papers == []
        assert calls["n"] == 3
        assert len(sleeps) == 2


def test_invert_abstract():
    text = invert_abstract({"world": [1], "hello": [0], "!": [2]})
    assert text == "hello world !"


class TestMerge:
    def test_merge_enriches_primary_and_dedupes(self):
        primary = [Paper(id="2010.11929", title="An Image is Worth 16x16 Words",
                         source="arxiv", citations=None, venue=None)]
        secondary = [
            Paper(id="2010.11929", title="An Image is Worth 16x16 Words",
                  source="openalex", citations=30111, venue="arXiv (Cornell)"),
            Paper(id="other-paper", title="Different topic entirely",
                  source="openalex"),
        ]
        merged = merge_papers(primary, secondary)
        assert len(merged) == 2
        by_id = {p.id: p for p in merged}
        assert by_id["2010.11929"].citations == 30111
        assert by_id["2010.11929"].venue == "arXiv (Cornell)"
        assert by_id["2010.11929"].source == "arxiv"  # primary wins on conflicts

    def test_fingerprint_dedupes_by_title_when_no_ids(self):
        a = Paper(id="x", title="Attention is all you need")
        b = Paper(id="y", title="attention is all you need")
        assert a.fingerprint() == b.fingerprint()

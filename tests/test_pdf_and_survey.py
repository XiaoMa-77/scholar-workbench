"""PDF extraction on a synthetic in-test PDF, compare and survey logic."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from litreview.compare import (cluster_papers, comparison_rows, markdown_table,
                               similarity, tag_papers)
from litreview.models import FigureCard, Paper, PaperContent
from litreview.pdf import PdfError, download_pdf, extract_content
from litreview.survey import build_survey, polish_survey

pymupdf = pytest.importorskip("fitz", reason="pdf extra not installed")


def make_synthetic_pdf(path: Path) -> None:
    """Two pages: title/abstract text plus one embedded chart image + caption."""
    import zlib
    import struct

    width, height = 220, 140
    raw = b"".join(b"\x30\x70\xa0" * width for _ in range(height))
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Synthetic Vision Paper")
    page.insert_text((72, 100), "We study vision transformers on conveyor belts.")
    page.insert_image(pymupdf.Rect(72, 120, 292, 260), stream=png)
    page.insert_text((72, 275), "Figure 1: Detection overview on the belt dataset.")
    doc.save(path)
    doc.close()


@pytest.fixture(scope="module")
def synthetic_pdf(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("pdf") / "paper.pdf"
    make_synthetic_pdf(path)
    return path


class TestExtract:
    def test_extracts_text_and_figure_with_caption(self, synthetic_pdf):
        content = extract_content(synthetic_pdf, "2099.00001")
        assert content.pages == 1
        assert "Synthetic Vision Paper" in content.text
        assert content.figure_count == 1
        figure = content.figures[0]
        assert figure.kind == "figure"
        assert figure.page == 1
        assert "Detection overview" in figure.caption
        assert figure.is_likely_real

    def test_caption_kind_detection_for_tables(self):
        card = FigureCard(paper_id="x", kind="table", page=2,
                          caption="Table 3: Ablation results", width_px=300,
                          height_px=200)
        assert card.to_dict()["kind"] == "table"
        assert "image_bytes" not in card.to_dict()


class TestDownload:
    def test_download_rejects_non_pdf(self, tmp_path):
        import httpx

        def handler(request):
            return httpx.Response(200, content=b"<!doctype html>short")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(PdfError):
            download_pdf("https://example.com/x.pdf", tmp_path / "x.pdf",
                         client=client)
        assert not (tmp_path / "x.pdf").exists()

    def test_download_rejects_oversize(self, tmp_path):
        import httpx

        def handler(request):
            return httpx.Response(200, content=b"0" * 2048,
                                  headers={"content-length": str(40 << 20)})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(PdfError):
            download_pdf("https://example.com/big.pdf", tmp_path / "big.pdf",
                         client=client, max_mb=1)


def sample_papers() -> list[Paper]:
    return [
        Paper(id="a", title="Contrastive pretraining for vision transformers",
              abstract="We pretrain vision transformers with contrastive "
                       "learning on unlabeled images and finetune on detection.",
              year=2021, venue="CVPR", citations=800),
        Paper(id="b", title="Contrastive learning for medical image segmentation",
              abstract="Contrastive pretraining improves medical image "
                       "segmentation with limited labels.",
              year=2022, venue="MICCAI", citations=120),
        Paper(id="c", title="Robot arm control with reinforcement learning",
              abstract="We train a robot arm to grasp objects with reinforcement "
                       "learning and sim-to-real transfer.",
              year=2023, venue=None, citations=15),
    ]


class TestCompare:
    def test_tags_are_discriminative(self):
        papers = sample_papers()
        tags = tag_papers(papers, top=4)
        assert set(tags) == {"a", "b", "c"}
        assert any("contrastive" in t for t in tags["a"] + tags["b"])
        assert any("reinforcement" in t or "robot" in t for t in tags["c"])

    def test_similarity_and_clusters(self):
        papers = sample_papers()
        sim = similarity(papers)
        pair_ab = sim[("a", "b")]
        pair_ac = sim[("a", "c")]
        assert pair_ab > pair_ac
        clusters = cluster_papers(papers, tag_papers(papers))
        assert 1 < len(clusters) < 4
        ids = {frozenset(p.id for p in cluster) for cluster in clusters}
        assert frozenset({"a", "b"}) in ids or any(
            {"a", "b"} <= c for c in ids)

    def test_comparison_table_rows(self):
        papers = sample_papers()
        contents = {"a": PaperContent(paper_id="a", pages=14, text_chars=40000,
                                      figures=[FigureCard("a", "figure", 3,
                                                          "Figure 1: x", 400, 300)])}
        rows = comparison_rows(papers, contents, tag_papers(papers))
        assert rows[0][0] == "#"
        assert len(rows) == 4
        assert rows[1][6] == "1"  # paper a has one real figure
        assert rows[2][6] == "—"  # no content for paper b


class TestSurvey:
    def test_build_survey_structure(self):
        papers = sample_papers()
        markdown = build_survey("contrastive learning", papers, {})
        for section in ("# 文献综述：contrastive learning", "## 主题分组",
                        "## 论文卡片", "## 横向对比", "## 综述叙述", "## 参考"):
            assert section in markdown
        assert "Attention" not in markdown
        assert "CVPR" in markdown
        assert "| #" in markdown  # table present

    def test_empty_survey(self):
        markdown = build_survey("nothing", [], {})
        assert "未检索到论文" in markdown or "论文数：0" in markdown

    def test_polish_without_llm_is_identity(self, tmp_path, monkeypatch):
        monkeypatch.setattr("litreview.survey.llm_from_config", lambda *a: None)
        markdown = build_survey("x", sample_papers()[:1], {})
        assert polish_survey(markdown) == markdown

    def test_polish_with_llm_rewrites_narrative(self, monkeypatch):
        class FakeClient:
            def complete(self, prompt):
                assert "结构化事实" in prompt
                return "重写后的综述叙述。"

        monkeypatch.setattr("litreview.survey.llm_from_config", lambda *a: FakeClient())
        markdown = build_survey("x", sample_papers()[:1], {})
        polished = polish_survey(markdown)
        assert "## 综述叙述（LLM 润色）" in polished
        assert "重写后的综述叙述。" in polished
        assert "## 参考" in polished

    def test_polish_with_llm_failure_keeps_rule_baseline(self):
        """润色调用抛异常时保留规则基线并给出提示，事实表格不受影响。"""
        class FailingClient:
            def complete(self, prompt):
                raise RuntimeError("endpoint down")

        markdown = build_survey("x", sample_papers()[:1], {})
        result = polish_survey(markdown, FailingClient())
        assert result.startswith(markdown)
        assert "LLM 润色失败" in result and "endpoint down" in result
        assert "## 横向对比" in result

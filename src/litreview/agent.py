"""Pipeline orchestration: search -> select -> download -> extract -> survey.

Every stage degrades gracefully: OpenAlex enrichment failures are logged, PDF
downloads that fail keep the paper (metadata-only), and the survey is always
produced. Results are cached under ``~/.litreview/cache``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .compare import similarity, tag_papers
from .models import Paper, PaperContent
from .pdf import PdfError, download_pdf, extract_content
from .sources import ArxivSource, OpenAlexSource, SourceError, merge_papers
from .survey import build_survey, polish_survey

logger = logging.getLogger("litreview")

DEFAULT_CACHE = Path.home() / ".litreview" / "cache"


@dataclass
class SurveyResult:
    query: str
    papers: list[Paper]
    contents: dict[str, PaperContent] = field(default_factory=dict)
    survey_md: str = ""
    report_path: str | None = None
    pdf_errors: list[str] = field(default_factory=list)
    source_errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"query={self.query!r} papers={len(self.papers)} "
                f"pdfs={len(self.contents)} figures="
                f"{sum(c.figure_count for c in self.contents.values())} "
                f"pdf_errors={len(self.pdf_errors)} "
                f"source_errors={len(self.source_errors)}")


class LitReviewAgent:
    def __init__(self, *, cache_dir: str | Path = DEFAULT_CACHE,
                 arxiv: ArxivSource | None = None,
                 openalex: OpenAlexSource | None = None,
                 use_openalex: bool = True, use_llm: bool = True):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.arxiv = arxiv or ArxivSource()
        self.openalex = openalex or OpenAlexSource()
        self.use_openalex = use_openalex
        self.use_llm = use_llm

    def search(self, query: str, limit: int = 8) -> list[Paper]:
        papers = self.arxiv.search(query, limit)
        if self.use_openalex:
            try:
                papers = merge_papers(papers, self.openalex.search(query, limit))
            except SourceError as error:
                logger.warning("OpenAlex 降级: %s", error)
        return papers[:limit]

    def fetch_pdfs(self, papers: list[Paper], *, offline: bool = False
                   ) -> tuple[dict[str, PaperContent], list[str]]:
        contents: dict[str, PaperContent] = {}
        errors: list[str] = []
        for paper in papers:
            if not paper.pdf_url:
                errors.append(f"{paper.id}: no pdf_url")
                continue
            cached = self.cache_dir / f"{paper.id.replace('/', '_')}.pdf"
            if not cached.is_file():
                if offline:
                    errors.append(f"{paper.id}: not cached (offline)")
                    continue
                try:
                    download_pdf(paper.pdf_url, cached)
                except PdfError as error:
                    errors.append(str(error))
                    continue
            try:
                contents[paper.id] = extract_content(cached, paper.id)
            except (PdfError, RuntimeError, ValueError) as error:
                errors.append(f"{paper.id}: extract failed ({error})")
        return contents, errors

    def run(self, query: str, *, limit: int = 8, out_dir: str | Path = ".",
            offline: bool = False, pdf: bool = True) -> SurveyResult:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        result = SurveyResult(query=query, papers=[])
        try:
            papers = self.search(query, limit)
        except SourceError as error:
            result.source_errors.append(str(error))
            papers = []
        result.papers = papers
        contents, pdf_errors = (self.fetch_pdfs(papers, offline=offline)
                                if pdf else ({}, []))
        result.contents = contents
        result.pdf_errors = pdf_errors
        if not papers:
            result.survey_md = build_survey(query, [], {})
        else:
            result.survey_md = build_survey(query, papers, contents)
            if self.use_llm and not offline:
                result.survey_md = polish_survey(result.survey_md)
        report = out / f"survey_{_slug(query)}.md"
        report.write_text(result.survey_md, encoding="utf-8")
        result.report_path = str(report)
        (out / "papers.json").write_text(
            json.dumps([p.to_dict() for p in papers], ensure_ascii=False, indent=1),
            encoding="utf-8")
        return result


def similarity_report(papers: list[Paper]) -> str:
    """Human-readable pairwise similarity (kept out of the survey body)."""
    sim = similarity(papers)
    if not sim:
        return "not enough papers"
    return "\n".join(f"{a} <-> {b}: {score:.2f}"
                     for (a, b), score in sorted(sim.items(), key=lambda kv: -kv[1])[:8])


def _slug(text: str) -> str:
    kept = "".join(c if c.isalnum() else "-" for c in text.lower())
    return "".join(ch for ch in kept.split("-") if ch)[:40] or "query"

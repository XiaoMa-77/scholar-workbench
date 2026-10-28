"""Shared discovery for CLI, MCP and the desktop survey pipeline."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from arxiv_digest.fetcher import Paper as SearchPaper
from arxiv_digest.scorer import normalize_keywords, score_papers
from arxiv_digest.search import parse_terms, search_all

from .models import Paper
from .sources import SourceError


def to_review_paper(paper: SearchPaper) -> Paper:
    """Keep full search metadata when handing a result to PDF/survey analysis."""
    arxiv_id = re.sub(r"v\d+$", "", paper.arxiv_id)
    return Paper(
        id=arxiv_id or paper.doi or "openalex-" + paper.link.rstrip("/").rsplit("/", 1)[-1],
        title=paper.title,
        authors=list(paper.authors),
        year=paper.published.year,
        venue=paper.venue or None,
        abstract=paper.abstract,
        url=paper.link,
        pdf_url=paper.pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None),
        citations=paper.citations,
        source=paper.source,
        primary_category=paper.categories[0] if paper.categories else None,
        published=paper.published.date().isoformat(),
        doi=paper.doi or None,
    )


@dataclass
class DiscoverySource:
    """Reuse the desktop's multi-source search, deduplication and rule ranking."""

    source: str = "all"
    categories: list[str] = field(default_factory=list)
    days: int | None = None
    venues_only: bool = False

    def cache_key(self) -> dict:
        return {"source": self.source, "categories": self.categories,
                "days": self.days, "venues_only": self.venues_only}

    def search(self, query: str, limit: int = 8) -> list[Paper]:
        if self.source not in {"arxiv", "openalex", "all"}:
            raise ValueError("source must be arxiv, openalex or all")
        if limit < 1:
            raise ValueError("limit must be positive")
        try:
            papers = search_all(query, self.categories, limit=limit, days=self.days,
                                source=self.source, venues_only=self.venues_only)
        except (OSError, ValueError, ET.ParseError) as error:
            raise SourceError(str(error)) from error
        scored = score_papers(papers, normalize_keywords(parse_terms(query)))
        return [to_review_paper(item.paper) for item in scored[:limit]]

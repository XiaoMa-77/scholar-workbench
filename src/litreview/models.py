"""Shared paper model independent of any specific source API."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?$", re.IGNORECASE)


@dataclass
class Paper:
    """Normalized metadata for one paper across arXiv / OpenAlex sources."""

    id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str = ""
    url: str | None = None
    pdf_url: str | None = None
    citations: int | None = None
    source: str = "arxiv"
    primary_category: str | None = None
    published: str | None = None
    doi: str | None = None

    def fingerprint(self) -> str:
        """Identity for cross-source dedup: arXiv id, then DOI, then title.

        OpenAlex stores arXiv papers under DOIs like ``10.48550/arXiv.2010.11929``,
        so any identifier containing an arXiv id normalizes to ``arxiv:<id>``.
        """
        for key in filter(None, (self.doi or "", self.id, self.url or "")):
            if "arxiv" in key.lower():
                match = ARXIV_ID_RE.search(
                    key.split("/abs/")[-1].split("/pdf/")[-1].split("?")[0])
                if match:
                    return f"arxiv:{match.group(1).lower()}"
        match = ARXIV_ID_RE.fullmatch((self.id or "").strip())
        if match:
            return f"arxiv:{match.group(1).lower()}"
        if self.doi:
            return "doi:" + self.doi.lower().removeprefix("https://doi.org/")
        words = [w for w in self.title.lower().split() if len(w) > 3]
        return "title:" + "-".join(sorted(words)[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    def with_updates(self, **changes) -> "Paper":
        return replace(self, **changes)


@dataclass
class FigureCard:
    """One extracted figure/table candidate with its bound caption."""

    paper_id: str
    kind: str  # figure | table
    page: int  # 1-based
    caption: str
    width_px: int
    height_px: int
    image_bytes: bytes | None = None  # populated only for in-memory galleries

    @property
    def is_likely_real(self) -> bool:
        return self.width_px >= 120 and self.height_px >= 90

    def to_dict(self) -> dict:
        data = self.to_dict_raw()
        data.pop("image_bytes")
        return data

    def to_dict_raw(self) -> dict:
        return {
            "paper_id": self.paper_id, "kind": self.kind, "page": self.page,
            "caption": self.caption, "width_px": self.width_px,
            "height_px": self.height_px, "image_bytes": self.image_bytes,
        }


@dataclass
class PaperContent:
    """Extraction result for one downloaded PDF."""

    paper_id: str
    pages: int = 0
    text_chars: int = 0
    text: str = ""
    figures: list[FigureCard] = field(default_factory=list)

    @property
    def figure_count(self) -> int:
        return len([f for f in self.figures if f.is_likely_real])

"""Paper search sources: arXiv Atom API (primary) and OpenAlex (enrichment).

Both clients accept an injected ``httpx.Client`` so tests can use
``httpx.MockTransport`` without any network access.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import httpx

from .models import Paper

ARXIV_API = "https://export.arxiv.org/api/query"
OPENALEX_API = "https://api.openalex.org/works"
UA = "lit-review-agent/0.1 (https://github.com/XiaoMa-77/lit-review-agent)"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class SourceError(RuntimeError):
    """A source failed after retries; callers degrade instead of crashing."""


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=20.0, headers={"User-Agent": UA},
                                  follow_redirects=True)


def normalize_arxiv_id(entry_id: str) -> str:
    """``arxiv:1706.03762v7`` / abs URL -> ``1706.03762``."""
    tail = entry_id.rstrip("/").split("/abs/")[-1]
    tail = tail.removeprefix("arxiv:")
    return re.sub(r"v\d+$", "", tail)


class ArxivSource:
    name = "arxiv"

    def __init__(self, client: httpx.Client | None = None, retries: int = 2):
        self.client = _client(client)
        self.retries = retries

    def search(self, query: str, limit: int = 10) -> list[Paper]:
        params = {"search_query": f"all:{query}", "max_results": limit,
                  "sortBy": "relevance"}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(ARXIV_API, params=params)
                response.raise_for_status()
                return self._parse(response.text)
            except (httpx.HTTPError, ET.ParseError) as error:
                last_error = error
                time.sleep(1.5 * (attempt + 1))
        raise SourceError(f"arXiv search failed: {last_error}")

    @staticmethod
    def _parse(atom_xml: str) -> list[Paper]:
        root = ET.fromstring(atom_xml)
        papers = []
        for entry in root.findall(f"{ATOM}entry"):
            arxiv_id = normalize_arxiv_id(
                entry.findtext(f"{ATOM}id", default="").strip())
            if not arxiv_id:
                continue
            published = entry.findtext(f"{ATOM}published", default="")
            authors = [a.findtext(f"{ATOM}name", default="").strip()
                       for a in entry.findall(f"{ATOM}author")]
            category_el = entry.find(f"{ATOM}category")
            primary_category = None
            if category_el is not None:
                primary_category = category_el.get("term") or None
            papers.append(Paper(
                id=arxiv_id,
                title=" ".join(entry.findtext(f"{ATOM}title", "").split()),
                authors=[a for a in authors if a],
                year=int(published[:4]) if published[:4].isdigit() else None,
                abstract=" ".join(entry.findtext(f"{ATOM}summary", "").split()),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                source="arxiv",
                primary_category=primary_category,
                published=published[:10] or None,
            ))
        return papers


def invert_abstract(index: dict[str, list[int]]) -> str:
    """Rebuild text from an OpenAlex ``abstract_inverted_index``."""
    positions: list[tuple[int, str]] = []
    for word, slots in index.items():
        positions.extend((slot, word) for slot in slots)
    return " ".join(word for _, word in sorted(positions))


class OpenAlexSource:
    name = "openalex"

    def __init__(self, client: httpx.Client | None = None, retries: int = 3,
                 mailto: str = "researcher@example.com"):
        self.client = _client(client)
        self.retries = retries
        self.mailto = mailto

    def search(self, query: str, limit: int = 10) -> list[Paper]:
        params = {"search": query, "per-page": limit, "mailto": self.mailto}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(OPENALEX_API, params=params)
                if response.status_code in (429, 500, 502, 503):
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=response.request,
                        response=response)
                response.raise_for_status()
                return self._parse(response.json())
            except (httpx.HTTPError, ValueError, KeyError) as error:
                last_error = error
                time.sleep(2.0 * (attempt + 1))
        raise SourceError(f"OpenAlex search failed: {last_error}")

    @staticmethod
    def _parse(payload: dict) -> list[Paper]:
        papers = []
        for work in payload.get("results", []):
            location = (work.get("primary_location") or {})
            source_info = (location.get("source") or {})
            landing = location.get("landing_page_url") or ""
            pdf = location.get("pdf_url")
            arxiv_id = ""
            for repo in ((location.get("oa_repo") or {}).get("id", ""), landing):
                match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+v?\d*)", str(repo))
                if match:
                    arxiv_id = re.sub(r"v\d+$", "", match.group(1))
                    break
            doi = (work.get("doi") or "").removeprefix("https://doi.org/") or None
            papers.append(Paper(
                id=arxiv_id or doi or f"openalex-{work.get('id', '').split('/')[-1]}",
                title=" ".join((work.get("display_name") or "").split()),
                authors=[(a.get("author") or {}).get("display_name", "")
                         for a in work.get("authorships", [])][:12],
                year=work.get("publication_year"),
                venue=source_info.get("display_name"),
                abstract=invert_abstract(work.get("abstract_inverted_index") or {}),
                url=landing or None,
                pdf_url=pdf or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None),
                citations=work.get("cited_by_count"),
                source="openalex",
                doi=doi,
            ))
        return [p for p in papers if p.title]


def merge_papers(primary: list[Paper], secondary: list[Paper]) -> list[Paper]:
    """Merge by fingerprint; primary wins, secondary fills missing fields."""
    by_key = {p.fingerprint(): p for p in primary}
    for paper in secondary:
        key = paper.fingerprint()
        if key in by_key:
            base = by_key[key]
            updates = {f: v for f, v in paper.to_dict().items()
                       if v not in (None, "", []) and
                       getattr(base, f, None) in (None, "", [])}
            if updates:
                by_key[key] = base.with_updates(**updates)
        else:
            by_key[key] = paper
    return list(by_key.values())

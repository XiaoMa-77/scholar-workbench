"""OpenAlex 层：正式期刊/会议论文检索 + arXiv 论文影响力兜底。

OpenAlex 收录 2.5 亿+ 篇学术文献（Nature、IEEE、Springer、ACM 等出版社的
期刊与会议论文），免 Key、无严格限流，是 arXiv 之外覆盖"顶刊顶会"的检索来源。

两个职责：
- search_openalex：按检索词（AND 语义与 arXiv 检索对齐）检索正式发表论文，
  自带 cited_by_count / venue，可按顶刊顶会清单过滤。
- fetch_impact_openalex：按 arXiv DOI 批量查引用数，作为 Semantic Scholar
  限流（429）时的影响力兜底，返回原始 dict，由 impact 层包装成 ImpactInfo。
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .fetcher import USER_AGENT, Paper
from .venues import is_top_venue, normalize_venue

WORKS_URL = "https://api.openalex.org/works"
TIMEOUT_SECONDS = 30
PER_PAGE_MAX = 200
# filter 值 OR 列表的稳妥分片大小（官方上限 50，取保守值）
FILTER_CHUNK = 20

SELECT_FIELDS = (
    "id,doi,display_name,authorships,publication_year,publication_date,"
    "primary_location,cited_by_count,abstract_inverted_index"
)


def _base_params(extra: dict) -> dict:
    """公共查询参数；设置 OPENALEX_EMAIL 可进入礼貌池，提升限额。"""
    params = dict(extra)
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if email:
        params["mailto"] = email
    return params


def _get_json(params: dict, timeout: int = TIMEOUT_SECONDS) -> dict:
    url = f"{WORKS_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _abstract_from_inverted(index: dict | None) -> str:
    """OpenAlex 摘要是倒排索引（词 → 位置列表），还原成正文。"""
    if not isinstance(index, dict):
        return ""
    positions: dict[int, str] = {}
    for word, slots in index.items():
        for slot in slots or []:
            positions[int(slot)] = str(word)
    return " ".join(positions[slot] for slot in sorted(positions))


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_paper(item: dict) -> Paper | None:
    title = str(item.get("display_name") or "").strip()
    if not title:
        return None
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    venue = str(source.get("display_name") or "")
    doi = str(item.get("doi") or "").replace("https://doi.org/", "")
    link = f"https://doi.org/{doi}" if doi else str(
        location.get("landing_page_url") or item.get("id") or ""
    )
    published_day = str(item.get("publication_date") or "")
    year = _int_or_none(item.get("publication_year"))
    # 与 arXiv 侧一致统一为 UTC 带时区时间，两源混排时才可比较
    if published_day[:2] in ("19", "20"):
        try:
            published = datetime.strptime(published_day, "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
        except ValueError:
            published = datetime(year or 1970, 1, 1, tzinfo=timezone.utc)
    else:
        published = datetime(year or 1970, 1, 1, tzinfo=timezone.utc)
    authors = [
        str((a.get("author") or {}).get("display_name") or "")
        for a in item.get("authorships") or []
    ]
    return Paper(
        arxiv_id="",
        title=title,
        authors=[a for a in authors if a],
        abstract=_abstract_from_inverted(item.get("abstract_inverted_index")),
        categories=[],
        published=published,
        link=link,
        source="openalex",
        doi=doi,
        citations=max(0, _int_or_none(item.get("cited_by_count")) or 0),
        venue=venue,
    )


def search_openalex(
    terms: list[str],
    limit: int = 30,
    days: int | None = None,
    today: date | None = None,
    venues_only: bool = False,
    timeout: int = TIMEOUT_SECONDS,
) -> list[Paper]:
    """按 OpenAlex 相关度检索正式发表论文。

    terms 多词取 AND（与 arXiv 检索语义对齐，本地二次过滤保证）；
    venues_only 为 True 时只保留顶刊顶会清单内的结果。
    """
    query = " ".join(terms)
    if not query:
        return []
    params = _base_params({
        "search": query,
        "per-page": str(min(PER_PAGE_MAX, max(limit * 2, 40))),
        "select": SELECT_FIELDS,
    })
    if days is not None:
        now = today or date.today()
        params["filter"] = f"from_publication_date:{(now - timedelta(days=days)).isoformat()}"
    data = _get_json(params, timeout=timeout)
    papers = [p for p in (_to_paper(w) for w in data.get("results", [])) if p]
    # OpenAlex 也会收录 arXiv 预印本本身（venue 为 "arXiv (Cornell University)"）。
    # 它们不是正式发表的期刊/会议论文，跳过；预印本由 arXiv 来源负责。
    papers = [p for p in papers if not normalize_venue(p.venue).startswith("arxiv")]
    lowered = [(p.title + " " + p.abstract).lower() for p in papers]
    papers = [p for p, text in zip(papers, lowered, strict=True)
              if all(t.lower() in text for t in terms)]
    if venues_only:
        papers = [p for p in papers if is_top_venue(p.venue)]
    return papers


def fetch_impact_openalex(
    arxiv_ids: list[str], timeout: int = TIMEOUT_SECONDS
) -> dict[str, dict]:
    """按 arXiv DOI（10.48550/arxiv.<id>）批量查引用与 venue。

    返回 {去版本号 arxiv_id: {"citations": int, "venue": str, "year": int|None}}；
    任何失败抛异常，由调用方（impact 层）决定降级方式。
    """
    result: dict[str, dict] = {}
    for start in range(0, len(arxiv_ids), FILTER_CHUNK):
        chunk = arxiv_ids[start : start + FILTER_CHUNK]
        dois = "|".join(f"10.48550/arxiv.{i}" for i in chunk)
        data = _get_json(
            _base_params({
                "filter": f"doi:{dois}",
                "select": "doi,cited_by_count,publication_year,primary_location",
            }),
            timeout=timeout,
        )
        for work in data.get("results", []):
            arxiv_id = str(work.get("doi") or "").rsplit("10.48550/arxiv.", 1)[-1]
            source = (work.get("primary_location") or {}).get("source") or {}
            result[arxiv_id] = {
                "citations": max(0, _int_or_none(work.get("cited_by_count")) or 0),
                "venue": str(source.get("display_name") or ""),
                "year": _int_or_none(work.get("publication_year")),
            }
    return result

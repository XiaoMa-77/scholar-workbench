"""论文检索：arXiv 预印本 + OpenAlex 正式期刊/会议论文，可单源或合并。

与每日摘要用的 fetch_papers 区别：
- 查询：用户关键词 / 研究方向 + 分类过滤，而不是固定分类全集
- 排序：sortBy=relevance（数据库相关度），而不是提交时间
- 数量：用户指定 limit，而不是固定 max_results
- 来源：source 选 "arxiv" / "openalex" / "all"（合并去重）
"""

import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .fetcher import Paper, parse_atom, USER_AGENT
from .openalex import search_openalex

API_URL = "http://export.arxiv.org/api/query"
TIMEOUT_SECONDS = 30


def parse_terms(query: str) -> list[str]:
    """把用户输入拆成检索词：支持引号短语，其余按空格/逗号/分号切分。"""
    terms: list[str] = []
    for part in re.findall(r'"[^"]+"|[^\s,;，；]+', query):
        term = part.strip('"\u201c\u201d ').strip()
        if term:
            terms.append(term)
    return terms


def build_query(terms: list[str], categories: list[str]) -> str:
    """构造 `(cat:A OR cat:B) AND (all:x AND all:y)` 形式的查询串。

    多个检索词之间取 AND（精确检索的专业默认）；单分类时省略括号。
    """
    parts: list[str] = []
    if categories:
        cat = " OR ".join(f"cat:{c.strip()}" for c in categories if c.strip())
        parts.append(f"({cat})" if len([c for c in categories if c.strip()]) > 1 else cat)
    if terms:
        joined = " AND ".join(f'all:"{t}"' for t in terms)
        parts.append(f"({joined})" if len(terms) > 1 else joined)
    return " AND ".join(parts)


def search_papers(
    query: str,
    categories: list[str] | None = None,
    limit: int = 30,
    days: int | None = None,
    today: date | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> list[Paper]:
    """按相关度检索论文。

    days 为 None 表示不限时间；否则只保留最近 days 天发表的论文。
    """
    terms = parse_terms(query)
    params = {
        "search_query": build_query(terms, categories or []),
        "sortBy": "relevance",
        "sortByOrder": "descending",
        "start": "0",
        "max_results": str(max(1, min(limit, 300))),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        papers = parse_atom(response.read().decode("utf-8"))
    if days is not None:
        now = today or date.today()
        date_from = now - timedelta(days=days)
        papers = [p for p in papers if date_from <= p.published.date() <= now]
    return papers


def _normalize_title(title: str) -> str:
    """标题归一化（小写、去非字母数字）用于跨来源去重比对。"""
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _arxiv_id_of(paper: Paper) -> str:
    """去版本号的 arXiv 编号；非 arXiv 来源返回空串。"""
    if paper.source != "arxiv" or not paper.arxiv_id:
        return ""
    return paper.arxiv_id.rsplit("v", 1)[0] if paper.arxiv_id[-1].isdigit() else paper.arxiv_id


def _merge_sources(papers: list[Paper]) -> list[Paper]:
    """合并去重：同一论文常同时存在于 arXiv 与 OpenAlex。

    OpenAlex 记录若与某篇 arXiv 记录同文（arXiv DOI 或标题一致），
    把它的引用数 / venue 补给 arXiv 记录后丢弃，保留信息更全的一条。
    """
    by_id = {_arxiv_id_of(p): p for p in papers if p.source == "arxiv" and p.arxiv_id}
    by_title = {_normalize_title(p.title): p for p in papers if p.source == "arxiv"}
    merged: list[Paper] = []
    for paper in papers:
        if paper.source == "openalex":
            doi_id = paper.doi.rsplit("10.48550/arxiv.", 1)[-1] \
                if paper.doi.startswith("10.48550/arxiv.") else ""
            twin = by_id.get(doi_id) or by_title.get(_normalize_title(paper.title))
            if twin is not None:
                if twin.citations is None and paper.citations is not None:
                    twin.citations = paper.citations
                if not twin.venue and paper.venue:
                    twin.venue = paper.venue
                continue
        merged.append(paper)
    return merged


def search_all(
    query: str,
    categories: list[str] | None = None,
    limit: int = 30,
    days: int | None = None,
    today: date | None = None,
    timeout: int = TIMEOUT_SECONDS,
    source: str = "arxiv",
    venues_only: bool = False,
) -> list[Paper]:
    """多来源检索入口。

    source："arxiv"（预印本）/"openalex"（正式期刊与会议）/"all"（合并去重）。
    venues_only 仅作用于 OpenAlex 部分（arXiv 全部是预印本，无正式 venue）。
    最终排序由打分层按关键词规则分统一处理。

    合并模式下单个来源失败（如 arXiv 偶发 503）不拖垮整个检索，
    只要还有任一来源返回结果就继续；单来源模式失败则原样抛出。
    """
    papers: list[Paper] = []
    failures: list[str] = []
    if source in ("arxiv", "all"):
        try:
            papers += search_papers(query, categories, limit=limit, days=days,
                                    today=today, timeout=timeout)
        except Exception:
            if source == "arxiv":
                raise
            failures.append("arXiv")
    if source in ("openalex", "all"):
        try:
            papers += search_openalex(parse_terms(query), limit=limit, days=days,
                                      today=today, venues_only=venues_only,
                                      timeout=timeout)
        except Exception:
            if source == "openalex":
                raise
            failures.append("OpenAlex")
    if source == "all" and papers:
        papers = _merge_sources(papers)
    if failures and not papers:
        raise OSError(f"全部检索来源失败：{'、'.join(failures)}")
    return papers

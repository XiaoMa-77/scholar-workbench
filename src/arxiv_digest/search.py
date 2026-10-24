"""按用户输入检索：关键词（AND 精确）或研究方向描述，按相关度排序。

与每日摘要用的 fetch_papers 区别：
- 查询：用户关键词 / 研究方向 + 分类过滤，而不是固定分类全集
- 排序：sortBy=relevance（arXiv 相关度），而不是提交时间
- 数量：用户指定 limit，而不是固定 max_results
"""

import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .fetcher import Paper, parse_atom, USER_AGENT

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

"""arXiv API 抓取与 Atom XML 解析（urllib 实现，不引入重依赖）。"""

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

from . import __version__
from .http import get_text

# Atom 主命名空间与 arXiv 扩展命名空间
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = (
    f"arxiv-digest-agent/{__version__} "
    "(https://github.com/XiaoMa-77/lit-review-agent)"
)


@dataclass
class Paper:
    """一篇论文的全部关注字段。

    source 为 "arxiv" 时 arxiv_id/link 为 arXiv 编号与页面；
    source 为 "openalex"（正式期刊/会议论文）时 arxiv_id 为空，
    doi/citations/venue 记录 OpenAlex 返回的正式发表信息。
    """

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published: datetime
    link: str
    source: str = "arxiv"
    doi: str = ""
    citations: int | None = None
    venue: str = ""
    pdf_url: str | None = None


def _squash(text: str) -> str:
    """把 XML 里带换行的标题/摘要压成单行，便于阅读与关键词匹配。"""
    return re.sub(r"\s+", " ", text).strip()


def build_search_query(categories: list[str]) -> str:
    """把分类列表拼成 `cat:cs.CV OR cat:cs.CL` 形式的查询串。"""
    return " OR ".join(f"cat:{c.strip()}" for c in categories if c.strip())


def parse_atom(xml_text: str) -> list[Paper]:
    """解析 Atom 响应文本，返回论文列表（不做日期过滤）。"""
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = entry.findtext(f"{ATOM_NS}id", default="")
        # id 形如 http://arxiv.org/abs/2610.10001v1，取 /abs/ 之后的部分作为编号
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1] if "/abs/" in raw_id else raw_id
        published = datetime.fromisoformat(
            entry.findtext(f"{ATOM_NS}published", default="1970-01-01T00:00:00Z")
        )
        # 主分类（arxiv:primary_category）与其余分类合并去重，保持出现顺序
        primary = entry.find(f"{ARXIV_NS}primary_category")
        categories = [primary.get("term", "")] if primary is not None else []
        categories += [c.get("term", "") for c in entry.findall(f"{ATOM_NS}category")]
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_squash(entry.findtext(f"{ATOM_NS}title", default="")),
                authors=[
                    author.findtext(f"{ATOM_NS}name", default="")
                    for author in entry.findall(f"{ATOM_NS}author")
                ],
                abstract=_squash(entry.findtext(f"{ATOM_NS}summary", default="")),
                categories=list(dict.fromkeys(t for t in categories if t)),
                published=published,
                link=raw_id,
            )
        )
    return papers


def fetch_papers(
    categories: list[str],
    date_from: date,
    date_to: date,
    max_results: int = 300,
    timeout: int = 30,
) -> list[Paper]:
    """抓取指定分类的最新论文，并按发表日期（UTC）过滤到 [date_from, date_to]。

    查询按提交时间降序取回 max_results 篇，再在本地按 published 日期筛选。
    """
    params = {
        "search_query": build_search_query(categories),
        "sortBy": "submittedDate",
        "sortByOrder": "descending",
        "start": "0",
        "max_results": str(max_results),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    body = get_text(request, timeout)
    papers = parse_atom(body)
    return [paper for paper in papers if date_from <= paper.published.date() <= date_to]

"""学术影响力层：Semantic Scholar 批量查询引用数与发表信息。

arXiv 预印本没有期刊影响因子，本模块用真实的引用数据作为影响力代理：
- citationCount：总引用数
- influentialCitationCount：高影响力引用数（S2 计算，引用该文且自身被引较多的文献）
- venue / year：正式发表去处与年份

接口失败（限流、断网、无该论文记录）一律优雅降级为"无数据"，
绝不让影响力查询阻塞检索主流程。
"""

import json
import math
import urllib.request
from dataclasses import dataclass

BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "citationCount,influentialCitationCount,venue,year,publicationVenue"
TIMEOUT_SECONDS = 20
USER_AGENT = "arxiv-digest-agent (desktop search)"


@dataclass
class ImpactInfo:
    """一篇论文的学术影响力数据（字段缺失为 None，前端展示为 —）。"""

    citations: int | None = None
    influential: int | None = None
    venue: str = ""
    year: int | None = None

    @property
    def score(self) -> float | None:
        """0-10 的对数综合分；无引用数据时返回 None（区别于 0 分）。"""
        if self.citations is None:
            return None
        raw = math.log10(1 + self.citations) * 2.5
        if self.influential is not None:
            raw += math.log10(1 + self.influential) * 2.0
        return round(min(10.0, raw), 1)


def fetch_impact(arxiv_ids: list[str], timeout: int = TIMEOUT_SECONDS) -> dict[str, ImpactInfo]:
    """批量查询影响力，一次 POST 取回全部（S2 batch 接口，免 Key 限量内可用）。

    返回 {去版本号 arxiv_id: ImpactInfo}；任何失败返回空 dict。
    """
    if not arxiv_ids:
        return {}
    payload = json.dumps({"ids": [f"arXiv:{i}" for i in arxiv_ids]}).encode("utf-8")
    request = urllib.request.Request(
        f"{BATCH_URL}?fields={FIELDS}",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            records = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}
    result: dict[str, ImpactInfo] = {}
    for arxiv_id, record in zip(arxiv_ids, records, strict=False):
        if not isinstance(record, dict):
            continue  # S2 对无记录的论文返回 null
        venue = str(record.get("venue") or "")
        if not venue:
            pub = record.get("publicationVenue") or {}
            venue = str(pub.get("name") or "") if isinstance(pub, dict) else ""
        result[arxiv_id] = ImpactInfo(
            citations=_int_or_none(record.get("citationCount")),
            influential=_int_or_none(record.get("influentialCitationCount")),
            venue=venue,
            year=_int_or_none(record.get("year")),
        )
    return result


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

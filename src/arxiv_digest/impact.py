"""学术影响力层：引用数与正式发表信息，Semantic Scholar 优先、OpenAlex 兜底。

arXiv 预印本没有期刊影响因子，本模块用真实的引用数据作为影响力代理：
- citationCount：总引用数
- influentialCitationCount：高影响力引用数（仅 S2 提供，兜底来源为 None）
- venue / year：正式发表去处与年份

S2 免 Key 共享池经常整体限流（HTTP 429），因此：
1. S2 batch 带 2 次指数退避重试；
2. 仍失败时自动切换 OpenAlex 批量 DOI 查询（免 Key、无严格限流）；
3. 两者都失败才降级为"无数据"，绝不阻塞检索主流程。
"""

import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .openalex import fetch_impact_openalex

BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "citationCount,influentialCitationCount,venue,year,publicationVenue"
TIMEOUT_SECONDS = 20
RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5
USER_AGENT = "arxiv-digest-agent (desktop search)"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


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


def _s2_batch(arxiv_ids: list[str], timeout: int) -> list | None:
    """调用 S2 batch 接口；网络/限流/5xx 返回 None（可重试）。"""
    payload = json.dumps({"ids": [f"arXiv:{i}" for i in arxiv_ids]}).encode("utf-8")
    request = urllib.request.Request(
        f"{BATCH_URL}?fields={FIELDS}",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_s2(arxiv_ids: list[str], records: list) -> dict[str, ImpactInfo]:
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


def fetch_impact(arxiv_ids: list[str], timeout: int = TIMEOUT_SECONDS) -> dict[str, ImpactInfo]:
    """批量查询影响力：S2（带重试）→ OpenAlex 兜底。

    返回 {去版本号 arxiv_id: ImpactInfo}；两个来源都失败返回空 dict。
    """
    if not arxiv_ids:
        return {}
    result: dict[str, ImpactInfo] = {}
    for attempt in range(RETRIES + 1):
        try:
            records = _s2_batch(arxiv_ids, timeout)
            if isinstance(records, list):
                result = _parse_s2(arxiv_ids, records)
                break
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_STATUS:
                break  # 4xx（鉴权/参数类）重试无意义
        except Exception:
            pass  # 超时/断网等，继续重试
        if attempt < RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    if result:
        return result
    # 兜底：OpenAlex 批量 DOI 查询（无高影响力引用数，但引用数/venue 真实可用）
    try:
        raw = fetch_impact_openalex(arxiv_ids, timeout=timeout)
    except Exception:
        return {}
    return {
        arxiv_id: ImpactInfo(
            citations=item["citations"],
            influential=None,
            venue=item["venue"],
            year=item["year"],
        )
        for arxiv_id, item in raw.items()
    }


def probe_providers(timeout: int = 8) -> dict[str, bool]:
    """探测两个引用数据源的可用性（前端状态胶囊点击时调用）。"""
    s2_ok = False
    try:
        records = _s2_batch(["1706.03762"], timeout)
        s2_ok = isinstance(records, list) and bool(records)
    except Exception:
        s2_ok = False
    oa_ok = False
    try:
        oa_ok = bool(fetch_impact_openalex(["1706.03762"], timeout=timeout))
    except Exception:
        oa_ok = False
    return {"semantic_scholar": s2_ok, "openalex": oa_ok}


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

"""可选 LLM 精排层：OpenAI 兼容 chat/completions 协议，纯 urllib 实现。

设置环境变量 LLM_API_KEY 后启用（可配 LLM_BASE_URL / LLM_MODEL）；
未设置 Key 或调用失败时优雅降级，只使用规则分，不阻塞日报生成。
"""

import json
import os
import re
import urllib.request
from dataclasses import dataclass

from .fetcher import Paper
from .scorer import ScoredPaper

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 60


@dataclass
class Credentials:
    """从环境变量读取的 LLM 接口凭据。"""

    api_key: str
    base_url: str
    model: str


@dataclass
class LLMResult:
    """单篇论文的 LLM 评审结果。"""

    score: float
    reason: str
    abstract_zh: str | None = None


def load_credentials() -> Credentials | None:
    """读取环境变量凭据，未设置或为空时返回 None 表示跳过 LLM。"""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    return Credentials(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        model=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
    )


def _extract_json(content: str) -> dict | None:
    """从模型回复中提取 JSON 对象，容忍 ```json 代码块包裹或前后噪声。"""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    candidate = fenced.group(1) if fenced else content
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _chat(creds: Credentials, messages: list[dict]) -> str:
    """调用 chat/completions 接口并返回首条回复文本。"""
    payload = json.dumps(
        {"model": creds.model, "messages": messages, "temperature": 0.2}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{creds.base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {creds.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def review_paper(
    paper: Paper, keywords: list[tuple[str, float]], creds: Credentials
) -> LLMResult | None:
    """让 LLM 给单篇论文打 0-10 相关性分、写一句话理由并中译摘要。

    网络、超时、JSON 解析等任何失败都返回 None，降级为只用规则分。
    """
    keyword_text = "、".join(name for name, _ in keywords) or "（无）"
    messages = [
        {
            "role": "system",
            "content": (
                "你是 arXiv 论文筛选助手。只输出一个 JSON 对象，不要输出其他内容，"
                '格式：{"score": 0到10的整数, "reason": "一句话中文理由", '
                '"abstract_zh": "摘要的中文翻译"}。score 表示该论文与用户研究兴趣的相关程度。'
            ),
        },
        {
            "role": "user",
            "content": (
                f"我的关注关键词：{keyword_text}\n\n"
                f"标题：{paper.title}\n"
                f"作者：{', '.join(paper.authors[:5])}\n"
                f"摘要：{paper.abstract}"
            ),
        },
    ]
    try:
        content = _chat(creds, messages)
    except Exception:  # 网络不通、超时、接口异常等一律降级
        return None
    data = _extract_json(content)
    if data is None:
        return None
    try:
        score = max(0.0, min(10.0, float(data["score"])))
        reason = str(data.get("reason", "")).strip()
    except (KeyError, TypeError, ValueError):
        return None
    abstract_zh = data.get("abstract_zh")
    return LLMResult(
        score=score,
        reason=reason,
        abstract_zh=str(abstract_zh).strip() if abstract_zh else None,
    )


def rerank(
    scored: list[ScoredPaper],
    keywords: list[tuple[str, float]],
    creds: Credentials | None,
    top_n: int,
) -> None:
    """对规则分 Top N 的论文就地补充 LLM 评分，结果写入各条目的 llm_* 字段。"""
    if creds is None:
        return
    for item in sorted(scored, key=lambda s: s.score, reverse=True)[:top_n]:
        result = review_paper(item.paper, keywords, creds)
        if result is not None:
            item.llm_score = result.score
            item.llm_reason = result.reason
            item.abstract_zh = result.abstract_zh

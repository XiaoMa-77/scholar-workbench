"""关键词规则打分：标题命中记 3×权重，摘要命中记 1×权重，关键词可自带权重。"""

from dataclasses import dataclass, field

from .fetcher import Paper

TITLE_HIT_WEIGHT = 3
ABSTRACT_HIT_WEIGHT = 1
DEFAULT_KEYWORD_WEIGHT = 1


@dataclass
class ScoredPaper:
    """带分数与命中信息的论文，LLM 结果由 CLI 层按需回填。"""

    paper: Paper
    score: float = 0.0
    matched: list[str] = field(default_factory=list)
    llm_score: float = 0.0
    llm_reason: str = ""
    abstract_zh: str | None = None

    @property
    def final_score(self) -> float:
        """最终排序分：规则分 + LLM 相关性分（无 LLM 时即规则分）。"""
        return self.score + self.llm_score


def normalize_keywords(raw) -> list[tuple[str, float]]:
    """把配置中的关键词归一成 (关键词, 权重) 列表。

    支持三种写法：纯字符串列表、{"name": .., "weight": ..} 字典列表、{关键词: 权重} 映射。
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [(str(k).strip(), float(w)) for k, w in raw.items() if str(k).strip()]
    result = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                result.append((name, float(item.get("weight", DEFAULT_KEYWORD_WEIGHT))))
        else:
            name = str(item).strip()
            if name:
                result.append((name, DEFAULT_KEYWORD_WEIGHT))
    return result


def score_paper(paper: Paper, keywords: list[tuple[str, float]]) -> ScoredPaper:
    """按关键词命中计分，并逐条记录命中位置与权重。"""
    scored = ScoredPaper(paper=paper)
    title = paper.title.lower()
    abstract = paper.abstract.lower()
    for keyword, weight in keywords:
        lowered = keyword.lower()
        if lowered in title:
            scored.score += weight * TITLE_HIT_WEIGHT
            scored.matched.append(f"{keyword}（标题 ×{weight:g}）")
        if lowered in abstract:
            scored.score += weight * ABSTRACT_HIT_WEIGHT
            scored.matched.append(f"{keyword}（摘要 ×{weight:g}）")
    return scored


def score_papers(papers: list[Paper], keywords: list[tuple[str, float]]) -> list[ScoredPaper]:
    """为全部论文打规则分，按分数降序排序，同分者发表时间新的在前。"""
    scored = [score_paper(paper, keywords) for paper in papers]
    scored.sort(key=lambda item: (item.score, item.paper.published), reverse=True)
    return scored

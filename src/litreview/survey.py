"""Survey (literature review) generation: rule-based core, optional LLM polish.

The rule-based core always runs and is fully offline. When an OpenAI-compatible
endpoint is configured (``~/.litreview/config.json``), ``polish_survey`` rewrites
the narrative sections without touching the factual tables.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from .compare import comparison_rows, markdown_table, similarity, tag_papers, cluster_papers
from .llm import LLMClient, llm_from_config
from .models import Paper, PaperContent

PROMPT_TEMPLATE = """你是一名科研文献综述助手。基于下面由工具提取的结构化事实（不可编造新事实、
不可新增论文、数字必须与事实一致），用中文重写"综述叙述"一节：约 300 字，说明研究脉络、
共性方法与分歧点。直接输出正文，不要标题。

结构化事实：
{facts}
"""


def _paper_card(paper: Paper, tags: list[str], content: PaperContent | None) -> str:
    authors = ", ".join(paper.authors[:4]) + (" 等" if len(paper.authors) > 4 else "")
    lines = [f"### {paper.title}",
             f"- 作者：{authors or '—'}　年份：{paper.year or '—'}　"
             f"发表处：{paper.venue or 'arXiv 预印本'}　引用：{paper.citations if paper.citations is not None else '—'}",
             f"- 链接：{paper.url or '—'}　arXiv ID：`{paper.id}`",
             f"- 方法标签：{', '.join(tags) or '—'}"]
    if content:
        figures = [f for f in content.figures if f.is_likely_real]
        lines.append(f"- 图表：{len(figures)} 个候选"
                     + (f"；代表性图表：{figures[0].caption[:80]}" if figures else ""))
        first_sentence = content.text.strip().split(". ")[0][:160]
        if first_sentence:
            lines.append(f"- 正文首句：{first_sentence}")
    return "\n".join(lines)


def build_survey(query: str, papers: list[Paper],
                 contents: dict[str, PaperContent]) -> str:
    """Offline, deterministic survey markdown for the collected papers."""
    tags = tag_papers(papers)
    clusters = cluster_papers(papers, tags)
    sim = similarity(papers)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    years = Counter(p.year for p in papers if p.year)
    venues = Counter(p.venue or "arXiv preprint" for p in papers)
    top_pair = max(sim.items(), key=lambda kv: kv[1], default=((None, None), 0.0))

    lines = [f"# 文献综述：{query}", "",
             f"- 生成时间：{now}　论文数：{len(papers)}",
             f"- 年份分布：{', '.join(f'{y} 年 {c} 篇' for y, c in sorted(years.items(), reverse=True)) or '—'}",
             f"- 来源分布：{', '.join(f'{v} {c} 篇' for v, c in venues.most_common(5))}",
             ""]

    lines += ["## 主题分组", ""]
    for index, cluster in enumerate(clusters, start=1):
        cluster_tags = Counter(t for p in cluster for t in tags.get(p.id, []))
        label = ", ".join(term for term, _ in cluster_tags.most_common(3)) or "其他"
        lines.append(f"{index}. **{label}**（{len(cluster)} 篇）："
                     + "；".join(_short_title(p.title) for p in cluster))
    lines += ["", "## 论文卡片", ""]
    for paper in papers:
        lines += [_paper_card(paper, tags.get(paper.id, []), contents.get(paper.id)), ""]
    lines += ["## 横向对比", "",
              markdown_table(comparison_rows(papers, contents, tags)), ""]
    if top_pair[0][0]:
        a, b = top_pair[0]
        lines += [f"- 摘要最相似的一对：`{a}` ↔ `{b}`（Jaccard {top_pair[1]:.2f}）", ""]

    lines += ["## 综述叙述（规则生成基线）", ""]
    lines.append(_narrative(papers, clusters, tags))
    lines += ["", "## 参考", ""]
    lines += [f"- {p.title}　[{p.id}]({p.url or p.id})" for p in papers]
    return "\n".join(lines) + "\n"


def _narrative(papers: list[Paper], clusters, tags) -> str:
    if not papers:
        return "未检索到论文。"
    year_range = f"{min(p.year for p in papers if p.year)}–{max(p.year for p in papers if p.year)}" if any(p.year for p in papers) else "年份未知"
    all_tags = Counter(t for p in papers for t in tags.get(p.id, [])[:3])
    common = "、".join(term for term, _ in all_tags.most_common(5)) or "多样方法"
    most_cited = max((p for p in papers if p.citations is not None),
                     key=lambda p: p.citations, default=None)
    parts = [f"围绕该主题共分析 {len(papers)} 篇论文（{year_range}），按方法标签可归为 "
             f"{len(clusters)} 个主题组，共性关键词包括 {common}。"]
    if most_cited:
        parts.append(f"其中引用量最高的是《{_short_title(most_cited.title)}》"
                     f"（{most_cited.citations} 次引用）。")
    parts.append("各组内部关注点相近，组间在任务设定或技术路线上存在差异，详见上方的主题分组与横向对比表。")
    return "".join(parts)


def _short_title(title: str, width: int = 40) -> str:
    return title if len(title) <= width else title[:width - 1] + "…"


def polish_survey(survey_md: str, client: LLMClient | None = None) -> str:
    """Replace the rule-based narrative with an LLM rewrite when available."""
    client = client or llm_from_config()
    if client is None:
        return survey_md
    marker = "## 综述叙述（规则生成基线）"
    if marker not in survey_md:
        return survey_md
    head, tail = survey_md.split(marker, 1)
    narrative = tail.split("## 参考", 1)[0]
    facts = narrative.strip()[:1500]
    try:
        rewritten = client.complete(PROMPT_TEMPLATE.format(facts=facts))
    except Exception as error:  # LLM failures degrade to rule-based, never crash
        return survey_md + f"\n\n> LLM 润色失败，保留规则基线（{error}）\n"
    return f"{head}## 综述叙述（LLM 润色）\n\n{rewritten.strip()}\n\n## 参考" + tail.split("## 参考", 1)[1]

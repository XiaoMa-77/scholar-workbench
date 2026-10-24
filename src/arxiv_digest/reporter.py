"""Markdown 日报的渲染与写盘。"""

from datetime import date
from pathlib import Path

from .scorer import ScoredPaper


def _authors_line(item: ScoredPaper) -> str:
    """作者取前三位，超出部分以 et al. 收尾。"""
    authors = item.paper.authors
    shown = ", ".join(authors[:3])
    return f"{shown}, et al." if len(authors) > 3 else shown


def _hit_line(item: ScoredPaper) -> str:
    """命中说明行：关键词命中列表，无命中时如实标注。"""
    return "；".join(item.matched) if item.matched else "无关键词命中"


def render_report(
    day: date, categories: list[str], scored: list[ScoredPaper], top_n: int
) -> str:
    """渲染完整日报 Markdown 文本：统计概览 + 按最终分排序的论文条目。"""
    shown = sorted(scored, key=lambda item: item.final_score, reverse=True)[:top_n]
    top_score = shown[0].final_score if shown else 0.0
    lines = [
        f"# arXiv 每日日报 · {day.isoformat()}",
        "",
        f"- 监控分类：{'、'.join(categories)}",
        f"- 抓取论文：{len(scored)} 篇，按总分排序展示 Top {len(shown)}",
        f"- 最高分：{top_score:g}",
        "",
    ]
    if not shown:
        lines.append("本期时间窗口内未抓取到符合条件的论文。")
        return "\n".join(lines) + "\n"
    for rank, item in enumerate(shown, start=1):
        paper = item.paper
        lines.append(f"## {rank}. {paper.title}（{item.final_score:g} 分）")
        lines.append("")
        lines.append(f"- **作者**：{_authors_line(item)}")
        lines.append(f"- **链接**：{paper.link}")
        lines.append(f"- **分类**：{'、'.join(paper.categories)}")
        lines.append(f"- **命中**：{_hit_line(item)}")
        if item.llm_reason:
            lines.append(f"- **LLM**：{item.llm_reason}（相关性 {item.llm_score:g}/10）")
        abstract = item.abstract_zh or paper.abstract
        lines.append(f"- **摘要**：{abstract}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(report_dir: str | Path, day: date, content: str) -> Path:
    """把日报写入 `report_dir/YYYY-MM-DD.md`，目录不存在时自动创建。"""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{day.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path

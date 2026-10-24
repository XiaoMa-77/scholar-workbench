"""日报渲染测试：从 fixture 数据生成 Markdown 并断言关键内容。"""

from datetime import date

from arxiv_digest.fetcher import parse_atom
from arxiv_digest.reporter import (
    collect_reported_links,
    render_report,
    write_report,
)
from arxiv_digest.scorer import score_papers

from fixtures_atom import ATOM_FIXTURE, KEYWORDS


def scored_fixture():
    """把 fixture 论文按配套关键词打好分，供各用例复用。"""
    return score_papers(parse_atom(ATOM_FIXTURE), KEYWORDS)


def test_report_header_and_statistics():
    """日报头部应包含日期、监控分类与统计概览。"""
    report = render_report(date(2026, 10, 24), ["cs.CV", "cs.CL"], scored_fixture(), top_n=10)
    assert "# arXiv 每日日报 · 2026-10-24" in report
    assert "监控分类：cs.CV、cs.CL" in report
    assert "抓取论文：3 篇" in report
    assert "最高分：20" in report


def test_report_contains_title_score_link_authors():
    """每篇论文应展示标题、分数、链接、作者（前三位 + et al.）与摘要。"""
    report = render_report(date(2026, 10, 24), ["cs.CV", "cs.CL"], scored_fixture(), top_n=10)
    assert "## 1. Vision-Language Diffusion Models for 3D Scene Understanding（20 分）" in report
    assert "http://arxiv.org/abs/2610.10001v1" in report
    assert "http://arxiv.org/abs/2610.10002v1" in report
    # 第一篇 4 位作者：展示前三位并以 et al. 收尾
    assert "Alice Chen, Bob Wang, Carol Li, et al." in report
    assert "vision-language（标题 ×3）" in report
    assert "diffusion（摘要 ×2）" in report
    assert "We propose a diffusion framework" in report


def test_top_n_limits_entries():
    """top_n 应限制展示条数，只保留总分最高的若干篇。"""
    report = render_report(date(2026, 10, 24), ["cs.CV"], scored_fixture(), top_n=1)
    assert "2610.10001" in report
    assert "2610.10002" not in report
    assert "2610.10003" not in report


def test_llm_fields_rendered_when_present():
    """带 LLM 结果的条目应展示相关性理由，且摘要优先用中文翻译。"""
    scored = scored_fixture()
    top = scored[0]
    top.llm_score = 8.0
    top.llm_reason = "与多模态感知方向高度相关"
    top.abstract_zh = "我们提出一个视觉-语言扩散框架。"
    report = render_report(date(2026, 10, 24), ["cs.CV"], scored, top_n=10)
    assert "与多模态感知方向高度相关（相关性 8/10）" in report
    assert "（28 分）" in report  # 20 规则分 + 8 LLM 分
    assert "我们提出一个视觉-语言扩散框架。" in report


def test_empty_report_has_placeholder():
    """无论文时日报应给出占位说明而不是报错。"""
    report = render_report(date(2026, 10, 24), ["cs.CV"], [], top_n=10)
    assert "未抓取到符合条件的论文" in report


def test_write_report_creates_file(tmp_path):
    """日报应写入 report_dir/YYYY-MM-DD.md 并返回路径。"""
    path = write_report(tmp_path, date(2026, 10, 24), "# demo\n")
    assert path.name == "2026-10-24.md"
    assert path.read_text(encoding="utf-8") == "# demo\n"


def test_collect_reported_links_scans_previous_reports(tmp_path):
    """已报告链接应被收集，example.md 与指定日期当天的文件不算重复。"""
    (tmp_path / "2026-10-23.md").write_text(
        "见 http://arxiv.org/abs/2610.10001v1 与 "
        "[另一篇](http://arxiv.org/abs/2610.10002v1)。\n",
        encoding="utf-8",
    )
    (tmp_path / "example.md").write_text(
        "http://arxiv.org/abs/9999.99999v1\n", encoding="utf-8"
    )
    (tmp_path / "2026-10-24.md").write_text(
        "http://arxiv.org/abs/2610.10003v1\n", encoding="utf-8"
    )
    seen = collect_reported_links(tmp_path, date(2026, 10, 24))
    assert "http://arxiv.org/abs/2610.10001v1" in seen
    assert "http://arxiv.org/abs/2610.10002v1" in seen
    assert "http://arxiv.org/abs/9999.99999v1" not in seen  # example 不算
    assert "http://arxiv.org/abs/2610.10003v1" not in seen  # 当天自己不算
    assert collect_reported_links(tmp_path / "nope", date(2026, 10, 24)) == set()

"""规则打分测试：关键词权重计分与排序逻辑。"""

from datetime import datetime

from arxiv_digest.fetcher import Paper
from arxiv_digest.scorer import normalize_keywords, score_paper, score_papers


def make_paper(title, abstract, published="2026-10-23T12:00:00Z"):
    """构造一篇最小可用的假论文。"""
    return Paper(
        arxiv_id="2610.99999v1",
        title=title,
        authors=["Alice", "Bob"],
        abstract=abstract,
        categories=["cs.CV"],
        published=datetime.fromisoformat(published),
        link="http://arxiv.org/abs/2610.99999v1",
    )


def test_normalize_keywords_supports_three_forms():
    """字符串列表、字典列表、映射三种写法都应归一成 (关键词, 权重)。"""
    assert normalize_keywords(["a", {"name": "b", "weight": 2}]) == [("a", 1.0), ("b", 2.0)]
    assert normalize_keywords({"c": 3}) == [("c", 3.0)]
    assert normalize_keywords(None) == []
    assert normalize_keywords(["  ", {"name": "  "}]) == []


def test_title_hit_weights_more_than_abstract():
    """标题命中记 3×权重，摘要命中记 1×权重。"""
    title_hit = score_paper(
        make_paper("Diffusion Models for Image Synthesis", "An unrelated abstract about cats."),
        [("diffusion", 2.0)],
    )
    assert title_hit.score == 6.0  # 2 × 3
    assert title_hit.matched == ["diffusion（标题 ×2）"]

    abstract_hit = score_paper(
        make_paper("A Study of Cats", "We leverage diffusion models extensively."),
        [("diffusion", 2.0)],
    )
    assert abstract_hit.score == 2.0  # 2 × 1


def test_title_and_abstract_both_hit():
    """同一关键词在标题与摘要都出现时分数累加。"""
    scored = score_paper(
        make_paper("Diffusion Study", "This paper applies diffusion to segmentation."),
        [("diffusion", 1.0)],
    )
    assert scored.score == 4.0  # 3 + 1
    assert len(scored.matched) == 2


def test_no_hit_scores_zero():
    scored = score_paper(make_paper("Cats", "Nothing relevant here."), [("diffusion", 5.0)])
    assert scored.score == 0.0
    assert scored.matched == []


def test_sort_by_score_then_published_date():
    """按分数降序排序，同分时发表时间新的在前。"""
    old = make_paper("Diffusion Title One", "x", published="2026-10-20T00:00:00Z")
    new = make_paper("Diffusion Title Two", "x", published="2026-10-23T00:00:00Z")
    low = make_paper("Cats", "nothing")
    ranked = score_papers([low, old, new], [("diffusion", 1.0)])
    assert [item.paper.title for item in ranked] == [
        "Diffusion Title Two",
        "Diffusion Title One",
        "Cats",
    ]


def test_final_score_includes_llm_part():
    """final_score = 规则分 + LLM 分，未启用 LLM 时即规则分。"""
    scored = score_paper(make_paper("Diffusion Study", "x"), [("diffusion", 1.0)])
    assert scored.final_score == 3.0
    scored.llm_score = 8.0
    assert scored.final_score == 11.0

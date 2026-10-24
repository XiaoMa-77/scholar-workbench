"""桌面客户端：pywebview 原生窗口 + 本地 HTML 前端（无需浏览器、无服务器）。

运行：pip install arxiv-digest-agent[desktop] 后执行 arxiv-digest-desktop
桥接层（DesktopAPI）与窗口分离：桥接层可在无 pywebview 的环境下单测。
"""

import csv
import io
import json
import time
from pathlib import Path

from .fetcher import Paper
from .impact import fetch_impact
from .llm import load_credentials, rerank
from .scorer import normalize_keywords, score_papers
from .search import parse_terms, search_papers

WEB_DIR = Path(__file__).parent / "web"
INDEX_HTML = WEB_DIR / "index.html"

# 前端分类选择器使用的常见 arXiv 分类
SUGGESTED_CATEGORIES = ["cs.CV", "cs.CL", "cs.AI", "cs.LG", "cs.RO", "cs.IR", "stat.ML"]


def _strip_version(arxiv_id: str) -> str:
    return arxiv_id.rsplit("v", 1)[0] if arxiv_id and arxiv_id[-1].isdigit() else arxiv_id


def build_rows(
    papers: list[Paper],
    terms: list[str],
    use_llm: bool,
    limit: int,
    impact_lookup=None,
) -> list[dict]:
    """把论文列表组装成前端行数据：规则相关度 + 可选 LLM 分 + 学术影响力。"""
    keywords = normalize_keywords(terms)
    scored = score_papers(papers, keywords)
    if use_llm:
        creds = load_credentials()
        if creds is not None:
            rerank(scored, keywords, creds, top_n=min(len(scored), 20))
    lookup = impact_lookup if impact_lookup is not None else {}
    rows: list[dict] = []
    for item in scored[:limit]:
        paper = item.paper
        impact = lookup.get(_strip_version(paper.arxiv_id))
        rows.append(
            {
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
                "authors": paper.authors[:3] + (["..."] if len(paper.authors) > 3 else []),
                "author_count": len(paper.authors),
                "published": paper.published.strftime("%Y-%m-%d"),
                "categories": paper.categories,
                "abstract": paper.abstract,
                "link": paper.link,
                "score": round(item.score, 1),
                "matched": item.matched,
                "llm_score": round(item.llm_score, 1) if item.llm_reason else None,
                "llm_reason": item.llm_reason,
                "abstract_zh": item.abstract_zh,
                "citations": impact.citations if impact else None,
                "influential": impact.influential if impact else None,
                "venue": impact.venue if impact else "",
                "year": impact.year if impact else None,
                "impact_score": impact.score if impact else None,
            }
        )
    return rows


class DesktopAPI:
    """pywebview js_api 桥接：前端通过 window.pywebview.api.* 调用。"""

    def categories(self) -> str:
        """前端分类选择器选项。"""
        return json.dumps(SUGGESTED_CATEGORIES, ensure_ascii=False)

    def llm_available(self) -> str:
        """是否配置了 LLM（用于前端提示，未配置时隐藏精排选项）。"""
        return json.dumps({"available": load_credentials() is not None})

    def search(self, query: str, categories: str, limit: int, days: str,
               use_llm: bool) -> str:
        """检索主流程：关键词/研究方向 → 相关度 + 学术影响力行数据。"""
        started = time.time()
        try:
            cats = json.loads(categories) if categories else []
            window_days = None if not days or days == "0" else int(days)
            papers = search_papers(query, cats, limit=limit, days=window_days)
            if not papers:
                return json.dumps({"ok": True, "rows": [], "elapsed": 0,
                                   "message": "没有检索到符合条件的论文"}, ensure_ascii=False)
            impact = fetch_impact([_strip_version(p.arxiv_id) for p in papers])
            rows = build_rows(papers, parse_terms(query), use_llm, limit, impact)
            return json.dumps(
                {"ok": True, "rows": rows, "elapsed": round(time.time() - started, 1),
                 "impact_available": bool(impact)}, ensure_ascii=False)
        except Exception as exc:  # 网络/解析异常都要给用户可读信息
            return json.dumps({"ok": False, "error": f"检索失败：{exc}"},
                              ensure_ascii=False)

    def export_csv(self, rows_json: str) -> str:
        """把当前结果导出为 CSV 文本（保存对话框由前端或调用方处理）。"""
        rows = json.loads(rows_json)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["排名外键", "标题", "作者", "发表日期", "分类", "相关度",
                         "LLM 相关性", "引用数", "高影响力引用", "发表 venue",
                         "影响力分", "链接"])
        for row in rows:
            writer.writerow([
                row["title"], "、".join(row["authors"][:-1]) if row["authors"][-1:] == ["..."]
                else "、".join(row["authors"]),
                row["published"], "/".join(row["categories"]), row["score"],
                row["llm_score"] or "", row["citations"] if row["citations"] is not None else "",
                row["influential"] if row["influential"] is not None else "",
                row["venue"], row["impact_score"] if row["impact_score"] is not None else "",
                row["link"],
            ])
        return buffer.getvalue()


def run() -> None:
    """启动桌面窗口（pywebview 为可选依赖，仅在此处导入）。"""
    import webview

    html = INDEX_HTML.read_text(encoding="utf-8")
    webview.create_window(
        "arXiv Scholar Search · 论文检索与影响力分析",
        html=html,
        js_api=DesktopAPI(),
        width=1320,
        height=880,
        min_size=(1024, 680),
    )
    webview.start()


def main() -> None:
    run()


if __name__ == "__main__":
    main()

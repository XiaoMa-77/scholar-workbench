"""桌面客户端：pywebview 原生窗口 + 本地 HTML 前端（无需浏览器、无服务器）。

运行：pip install arxiv-digest-agent[desktop] 后执行 arxiv-digest-desktop
桥接层（DesktopAPI）与窗口分离：桥接层可在无 pywebview 的环境下单测。

检索来源支持 arXiv 预印本与 OpenAlex 正式期刊/会议论文（可合并去重）；
引用数据 Semantic Scholar 优先、OpenAlex 兜底；LLM 凭据支持设置弹窗持久化。
"""

import csv
import io
import json
import time
from pathlib import Path

from .fetcher import Paper
from .impact import ImpactInfo, fetch_impact, probe_providers
from .llm import load_credentials, mask_key, rerank, save_credentials, test_credentials
from .scorer import normalize_keywords, score_papers
from .search import parse_terms, search_all

WEB_DIR = Path(__file__).parent / "web"
INDEX_HTML = WEB_DIR / "index.html"

# 前端分类选择器使用的常见 arXiv 分类
SUGGESTED_CATEGORIES = ["cs.CV", "cs.CL", "cs.AI", "cs.LG", "cs.RO", "cs.IR", "stat.ML"]

SOURCE_LABELS = {"arxiv": "arXiv 预印本", "openalex": "期刊/会议"}


def _strip_version(arxiv_id: str) -> str:
    return arxiv_id.rsplit("v", 1)[0] if arxiv_id and arxiv_id[-1].isdigit() else arxiv_id


def _impact_of(paper: Paper, lookup: dict[str, ImpactInfo]) -> ImpactInfo | None:
    """arXiv 论文用引用数据源查询结果；OpenAlex 论文自带引用数直接构造。"""
    if paper.source == "arxiv" and paper.arxiv_id:
        found = lookup.get(_strip_version(paper.arxiv_id))
        if found is not None:
            return found
    if paper.citations is not None or paper.venue:
        return ImpactInfo(citations=paper.citations, influential=None,
                          venue=paper.venue, year=paper.published.year)
    return None


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
        impact = _impact_of(paper, lookup)
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
                "source": paper.source,
                "source_label": SOURCE_LABELS.get(paper.source, paper.source),
                "doi": paper.doi,
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

    def llm_config(self) -> str:
        """当前 LLM 配置（Key 脱敏），供设置弹窗回显。"""
        creds = load_credentials()
        if creds is None:
            return json.dumps({"configured": False}, ensure_ascii=False)
        return json.dumps(
            {
                "configured": True,
                "api_key_masked": mask_key(creds.api_key),
                "base_url": creds.base_url,
                "model": creds.model,
            },
            ensure_ascii=False,
        )

    def save_llm_config(self, api_key: str, base_url: str, model: str) -> str:
        """保存 LLM 凭据到本地配置文件（环境变量存在时优先级仍更高）。"""
        try:
            save_credentials(api_key or "", base_url or "", model or "")
            return json.dumps({"ok": True, "available": load_credentials() is not None},
                              ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"保存失败：{exc}"},
                              ensure_ascii=False)

    def test_llm(self) -> str:
        """用当前凭据发一条最小消息，验证端点与 Key 可用。"""
        ok, message = test_credentials()
        return json.dumps({"ok": ok, "message": message}, ensure_ascii=False)

    def test_impact_providers(self) -> str:
        """探测引用数据源连通性（顶部状态胶囊点击时调用）。"""
        return json.dumps(probe_providers(), ensure_ascii=False)

    def search(self, query: str, categories: str, limit: int, days: str,
               use_llm: bool, source: str = "arxiv",
               venues_only: bool = False) -> str:
        """检索主流程：关键词/研究方向 → 相关度 + 学术影响力行数据。"""
        started = time.time()
        try:
            cats = json.loads(categories) if categories else []
            window_days = None if not days or days == "0" else int(days)
            papers = search_all(
                query, cats, limit=limit, days=window_days,
                source=source if source in ("arxiv", "openalex", "all") else "arxiv",
                venues_only=bool(venues_only))
            if not papers:
                return json.dumps({"ok": True, "rows": [], "elapsed": 0,
                                   "message": "没有检索到符合条件的论文"}, ensure_ascii=False)
            impact_ids = [_strip_version(p.arxiv_id) for p in papers
                          if p.source == "arxiv" and p.arxiv_id]
            impact = fetch_impact(impact_ids)
            rows = build_rows(papers, parse_terms(query), use_llm, limit, impact)
            counts = {"arxiv": sum(1 for r in rows if r["source"] == "arxiv"),
                      "openalex": sum(1 for r in rows if r["source"] == "openalex")}
            return json.dumps(
                {"ok": True, "rows": rows, "elapsed": round(time.time() - started, 1),
                 "impact_available": any(r["citations"] is not None for r in rows),
                 "counts": counts}, ensure_ascii=False)
        except Exception as exc:  # 网络/解析异常都要给用户可读信息
            return json.dumps({"ok": False, "error": f"检索失败：{exc}"},
                              ensure_ascii=False)

    def export_csv(self, rows_json: str) -> str:
        """把当前结果导出为 CSV 文本（保存对话框由前端或调用方处理）。"""
        rows = json.loads(rows_json)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["标题", "作者", "来源", "发表日期", "分类", "相关度",
                         "LLM 相关性", "引用数", "高影响力引用", "发表 venue",
                         "影响力分", "链接"])
        for row in rows:
            writer.writerow([
                row["title"], "、".join(row["authors"][:-1]) if row["authors"][-1:] == ["..."]
                else "、".join(row["authors"]),
                row.get("source_label", ""), row["published"],
                "/".join(row["categories"]), row["score"],
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
        "Scholar Search · 论文检索与影响力分析（arXiv + 期刊会议）",
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

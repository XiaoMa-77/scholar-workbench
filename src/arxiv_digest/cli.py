"""arxiv-digest 命令行入口：抓取 -> 规则打分 -> （可选）LLM 精排 -> 生成日报。"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import __version__
from .fetcher import fetch_papers
from .llm import load_credentials, rerank
from .reporter import render_report, write_report
from .scorer import normalize_keywords, score_papers

# 未提供配置文件时使用的内置默认值
DEFAULT_CONFIG: dict = {
    "categories": ["cs.CV", "cs.CL"],
    "keywords": [
        {"name": "vision-language", "weight": 3},
        {"name": "diffusion", "weight": 2},
        {"name": "segmentation", "weight": 2},
        {"name": "detection", "weight": 1},
        {"name": "3D", "weight": 1},
        {"name": "self-supervised", "weight": 1},
    ],
    "top_n": 10,
    "report_dir": "reports",
    "max_results": 300,
    "lookback_days": 2,  # 日期窗口：2 表示“昨天 + 今天”
}


def load_config(path: str | None) -> dict:
    """加载 YAML 配置。

    未指定路径时：当前目录存在 config.yaml 则用之，否则使用内置默认值；
    用户配置中缺省的字段也回落到内置默认值。
    """
    if path is None:
        candidate = Path("config.yaml")
        if not candidate.is_file():
            return dict(DEFAULT_CONFIG)
        path = str(candidate)
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULT_CONFIG)
    merged.update({key: value for key, value in data.items() if value is not None})
    return merged


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="arxiv-digest",
        description="抓取指定 arXiv 分类的最新论文，按关键词打分排序并生成 Markdown 日报。",
    )
    parser.add_argument("--config", help="YAML 配置文件路径（默认：config.yaml 或内置默认）")
    parser.add_argument("--date", help="日报日期，格式 YYYY-MM-DD（默认今天）")
    parser.add_argument("--top", type=int, help="日报展示的论文数量上限（覆盖配置中的 top_n）")
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 精排，只使用规则分")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主流程，返回进程退出码。"""
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    day = date.fromisoformat(args.date) if args.date else date.today()
    top_n = args.top if args.top is not None else int(config["top_n"])
    lookback = max(1, int(config.get("lookback_days", 2)))
    date_from = day - timedelta(days=lookback - 1)

    categories = [str(c) for c in config["categories"]]
    keywords = normalize_keywords(config["keywords"])

    print(f"[1/4] 抓取 arXiv：分类 {'、'.join(categories)}，日期范围 {date_from} ~ {day}")
    try:
        papers = fetch_papers(
            categories, date_from, day, max_results=int(config["max_results"])
        )
    except Exception as exc:  # 网络不通、接口异常等
        print(f"[错误] 抓取失败：{exc}", file=sys.stderr)
        return 1

    print(f"[2/4] 规则打分：共 {len(papers)} 篇论文")
    scored = score_papers(papers, keywords)

    if args.no_llm:
        print("[3/4] 跳过 LLM 精排（--no-llm）")
    else:
        creds = load_credentials()
        if creds is None:
            print("[3/4] 未设置 LLM_API_KEY，仅使用规则分")
        else:
            print(f"[3/4] LLM 精排：模型 {creds.model}，处理 Top {top_n}")
            rerank(scored, keywords, creds, top_n)

    content = render_report(day, categories, scored, top_n)
    path = write_report(config["report_dir"], day, content)
    print(f"[4/4] 日报已写入：{path}")
    return 0

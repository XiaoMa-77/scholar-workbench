"""Command line entry point.

    litreview "vision transformer" --limit 6 --out reports
"""

from __future__ import annotations

import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litreview",
        description="Research agent: search -> download -> figures -> compare -> survey",
        epilog="Commands: survey QUERY (default), search QUERY, desktop, digest [options].")
    parser.add_argument("query", help="research topic / keywords")
    parser.add_argument("--limit", type=int, default=8, help="papers to keep (default 8)")
    parser.add_argument("--out", default=".", help="output directory (default cwd)")
    parser.add_argument("--no-pdf", action="store_true", help="skip PDF download/extraction")
    parser.add_argument("--no-openalex", action="store_true", help="arXiv only")
    parser.add_argument("--source", choices=["all", "arxiv", "openalex"], default="all")
    parser.add_argument("--category", action="append", default=[], help="arXiv category; repeatable")
    parser.add_argument("--days", type=int, help="publication date window in days")
    parser.add_argument("--venues-only", action="store_true", help="top venues in OpenAlex results")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip optional LLM polish (rule-based survey only)")
    parser.add_argument("--offline", action="store_true",
                        help="use cache only; never touch the network")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "survey"
    if argv and argv[0] == "digest":
        from arxiv_digest.cli import main as digest_main
        return digest_main(argv[1:])
    if argv and argv[0] == "desktop":
        argparse.ArgumentParser(prog="litreview desktop").parse_args(argv[1:])
        from arxiv_digest.desktop import main as desktop_main
        desktop_main()
        return 0
    if argv and argv[0] in {"survey", "search"}:
        mode = argv.pop(0)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 300:
        parser.error("--limit must be between 1 and 300")
    if args.days is not None and args.days < 1:
        parser.error("--days must be positive")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    from .agent import LitReviewAgent
    from .discovery import DiscoverySource
    from .sources import SourceError

    discovery = DiscoverySource(source="arxiv" if args.no_openalex else args.source,
                                categories=args.category, days=args.days,
                                venues_only=args.venues_only)
    agent = LitReviewAgent(discovery=discovery, use_llm=not args.no_llm)
    try:
        if mode == "search":
            import json
            papers = (agent._cached_search(args.query, args.limit) if args.offline
                      else agent.search(args.query, args.limit))
            print(json.dumps([paper.to_dict() for paper in papers], ensure_ascii=False, indent=2))
            return 0 if papers else 1
        result = agent.run(args.query, limit=args.limit, out_dir=args.out,
                           offline=args.offline, pdf=not args.no_pdf)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except SourceError as error:
        print(f"source warn: {error}", file=sys.stderr)
        return 1
    print(result.summary())
    print(f"survey: {result.report_path}")
    for error in result.pdf_errors[:5]:
        print(f"pdf warn: {error}", file=sys.stderr)
    for error in result.source_errors[:5]:
        print(f"source warn: {error}", file=sys.stderr)
    return 0 if result.papers else 1


if __name__ == "__main__":
    raise SystemExit(main())

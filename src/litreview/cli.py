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
        description="Literature review agent: search -> download -> figures -> compare -> survey")
    parser.add_argument("query", help="research topic / keywords")
    parser.add_argument("--limit", type=int, default=8, help="papers to keep (default 8)")
    parser.add_argument("--out", default=".", help="output directory (default cwd)")
    parser.add_argument("--no-pdf", action="store_true", help="skip PDF download/extraction")
    parser.add_argument("--no-openalex", action="store_true", help="arXiv only")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip optional LLM polish (rule-based survey only)")
    parser.add_argument("--offline", action="store_true",
                        help="use cache only; never touch the network")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    from .agent import LitReviewAgent
    from .sources import ArxivSource, OpenAlexSource

    agent = LitReviewAgent(arxiv=ArxivSource(),
                           openalex=None if args.no_openalex else OpenAlexSource(),
                           use_openalex=not args.no_openalex,
                           use_llm=not args.no_llm)
    try:
        result = agent.run(args.query, limit=args.limit, out_dir=args.out,
                           offline=args.offline, pdf=not args.no_pdf)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    print(result.summary())
    print(f"survey: {result.report_path}")
    for error in result.pdf_errors[:5]:
        print(f"pdf warn: {error}", file=sys.stderr)
    for error in result.source_errors[:5]:
        print(f"source warn: {error}", file=sys.stderr)
    return 0 if result.papers else 1


if __name__ == "__main__":
    raise SystemExit(main())

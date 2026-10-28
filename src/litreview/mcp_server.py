"""MCP stdio tools backed by the shared research pipeline (mcp 1.x)."""

from __future__ import annotations

import json
import sys

from .agent import LitReviewAgent


def register(server, agent: LitReviewAgent) -> None:
    @server.tool(name="litreview_search")
    def search(query: str, limit: int = 8) -> str:
        """Search arXiv and OpenAlex, deduplicate and rank; return paper JSON."""
        if not 1 <= limit <= 300:
            raise ValueError("limit must be between 1 and 300")
        return json.dumps([paper.to_dict() for paper in agent.search(query, limit)],
                          ensure_ascii=False, indent=1)

    @server.tool(name="litreview_survey")
    def survey(query: str, limit: int = 6, out_dir: str = ".") -> str:
        """Search, download PDFs, inventory figures, compare and write a Chinese survey."""
        if not 1 <= limit <= 300:
            raise ValueError("limit must be between 1 and 300")
        result = agent.run(query, limit=limit, out_dir=out_dir)
        text = result.survey_md
        warnings = result.source_errors + result.pdf_errors
        if warnings:
            text += "\n\n> Warnings: " + "; ".join(warnings[:3])
        return text


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        sys.exit('missing dependency: pip install "scholar-workbench[mcp]"')
    server = FastMCP("scholar-workbench")
    register(server, LitReviewAgent())
    server.run()


if __name__ == "__main__":
    main()

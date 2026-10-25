"""MCP stdio server exposing the literature review pipeline as tools.

Requires the ``mcp`` extra. Run directly or configure in an MCP client::

    {"mcpServers": {"litreview": {
        "command": "python", "args": ["-m", "litreview.mcp_server"]}}}

Tools: ``litreview_search``, ``litreview_survey``.
"""

from __future__ import annotations

import sys

from .agent import LitReviewAgent
from .sources import ArxivSource, OpenAlexSource


def register(server, agent: LitReviewAgent) -> None:
    from mcp.types import Tool

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="litreview_search",
                description="Search arXiv (OpenAlex enrichment) for papers; "
                            "returns normalized metadata as JSON.",
                inputSchema={"type": "object", "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8}},
                    "required": ["query"]}),
            Tool(
                name="litreview_survey",
                description="Run the full pipeline (search, PDF figures, "
                            "comparison) and return a Chinese survey in Markdown.",
                inputSchema={"type": "object", "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 6},
                    "out_dir": {"type": "string", "default": "."}},
                    "required": ["query"]}),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        from mcp.types import TextContent
        if name == "litreview_search":
            papers = agent.search(arguments["query"], int(arguments.get("limit", 8)))
            import json
            return [TextContent(type="text", text=json.dumps(
                [p.to_dict() for p in papers], ensure_ascii=False, indent=1))]
        if name == "litreview_survey":
            result = agent.run(arguments["query"],
                               limit=int(arguments.get("limit", 6)),
                               out_dir=arguments.get("out_dir", "."))
            text = result.survey_md
            if result.pdf_errors:
                text += "\n\n> PDF warnings: " + "; ".join(result.pdf_errors[:3])
            return [TextContent(type="text", text=text)]
        raise ValueError(f"unknown tool: {name}")


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        sys.exit('missing dependency: pip install "lit-review-agent[mcp]"')
    server = FastMCP("lit-review-agent")
    register(server, LitReviewAgent(arxiv=ArxivSource(), openalex=OpenAlexSource()))
    server.run()


if __name__ == "__main__":
    main()

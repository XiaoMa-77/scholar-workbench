"""Register and actually invoke both MCP tools; import-only smoke checks miss this."""

import asyncio
import json
from unittest.mock import Mock

from mcp.server.fastmcp import FastMCP

from litreview.agent import SurveyResult
from litreview.mcp_server import register
from litreview.models import Paper


def test_mcp_tools_register_and_invoke(tmp_path):
    agent = Mock()
    agent.search.return_value = [Paper(id="x", title="Tracking paper")]
    agent.run.return_value = SurveyResult(query="tracking", papers=[],
                                         survey_md="# Survey", pdf_errors=["PDF unavailable"])
    server = FastMCP("test")
    register(server, agent)

    async def check():
        assert {tool.name for tool in await server.list_tools()} == {
            "litreview_search", "litreview_survey"}
        results = await server.call_tool("litreview_search", {"query": "tracking", "limit": 2})
        if isinstance(results, tuple):
            results = results[0]
        assert json.loads(results[0].text)[0]["title"] == "Tracking paper"
        results = await server.call_tool("litreview_survey", {"query": "tracking",
                                                             "out_dir": str(tmp_path)})
        if isinstance(results, tuple):
            results = results[0]
        assert "# Survey" in results[0].text and "PDF unavailable" in results[0].text

    asyncio.run(check())
    agent.search.assert_called_once_with("tracking", 2)
    agent.run.assert_called_once_with("tracking", limit=6, out_dir=str(tmp_path))

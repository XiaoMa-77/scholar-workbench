"""Cross-project behavior: one discovery path, saved metadata and survey handoff."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from arxiv_digest.fetcher import Paper as SearchPaper
from litreview.agent import LitReviewAgent
from litreview.discovery import DiscoverySource, to_review_paper
from litreview.models import Paper


def search_paper(title="Transformer tracking", **changes):
    fields = dict(arxiv_id="2610.10001v2", title=title, authors=["Alice", "Bob"],
                  abstract="Tracking with attention", categories=["cs.CV"],
                  published=datetime(2026, 10, 24, tzinfo=timezone.utc),
                  link="https://arxiv.org/abs/2610.10001v2")
    return SearchPaper(**(fields | changes))


def test_conversion_keeps_pdf_citations_and_authors():
    paper = to_review_paper(search_paper(citations=0, venue="CVPR", doi="10.1/a"))
    assert paper.id == "2610.10001"
    assert paper.pdf_url == "https://arxiv.org/pdf/2610.10001"
    assert paper.authors == ["Alice", "Bob"]
    assert paper.citations == 0 and paper.venue == "CVPR"
    assert paper.doi == "10.1/a" and paper.published == "2026-10-24"


def test_openalex_conversion_preserves_open_access_pdf():
    from arxiv_digest.openalex import _to_paper
    raw = _to_paper({"display_name": "Tracking", "doi": "https://doi.org/10.1/a",
                     "publication_year": 2026, "primary_location": {},
                     "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"}})
    paper = to_review_paper(raw)
    assert paper.id == "10.1/a"
    assert paper.pdf_url == "https://example.org/paper.pdf"


def test_discovery_ranks_before_limit_and_passes_filters(monkeypatch):
    search = Mock(return_value=[search_paper(title="Unrelated", abstract="Other"),
                                search_paper()])
    monkeypatch.setattr("litreview.discovery.search_all", search)
    source = DiscoverySource(source="all", categories=["cs.CV"], days=30,
                             venues_only=True)
    papers = source.search("tracking", 1)
    assert len(papers) == 1 and papers[0].title == "Transformer tracking"
    assert search.call_args.kwargs["source"] == "all"
    assert search.call_args.kwargs["venues_only"] is True
    assert search.call_args.kwargs["days"] == 30


def test_default_agent_uses_shared_discovery(tmp_path, monkeypatch):
    search = Mock(return_value=[search_paper()])
    monkeypatch.setattr("litreview.discovery.search_all", search)
    agent = LitReviewAgent(cache_dir=tmp_path / "cache", use_llm=False)
    assert agent.search("tracking", 1)[0].id == "2610.10001"
    search.assert_called_once()


def test_selected_papers_generate_survey_without_search(tmp_path, monkeypatch):
    agent = LitReviewAgent(cache_dir=tmp_path / "cache", use_llm=False)
    monkeypatch.setattr(agent, "search", Mock(side_effect=AssertionError("searched again")))
    papers = [Paper(id="x", title="Selected tracking paper", authors=["Alice"])]
    result = agent.run("tracking", papers=papers, pdf=False, out_dir=tmp_path / "out")
    assert result.papers == papers
    assert "Selected tracking paper" in result.survey_md
    assert json.loads((tmp_path / "out" / "papers.json").read_text("utf-8"))[0]["id"] == "x"


def test_offline_uses_search_cache_and_never_calls_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("litreview.discovery.search_all", Mock(return_value=[search_paper()]))
    agent = LitReviewAgent(cache_dir=tmp_path / "cache", use_llm=False)
    agent.search("tracking", 1)
    monkeypatch.setattr("litreview.discovery.search_all", Mock(side_effect=AssertionError("network")))
    result = agent.run("tracking", limit=1, offline=True, pdf=False, out_dir=tmp_path / "out")
    assert len(result.papers) == 1 and not result.source_errors


def test_offline_cache_miss_reports_error_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr("litreview.discovery.search_all", Mock(side_effect=AssertionError("network")))
    agent = LitReviewAgent(cache_dir=tmp_path / "cache", use_llm=False)
    result = agent.run("uncached", offline=True, pdf=False, out_dir=tmp_path / "out")
    assert result.papers == [] and "offline" in result.source_errors[0]


def test_desktop_handoff_uses_full_metadata_and_does_not_search(tmp_path, monkeypatch):
    from arxiv_digest.desktop import DesktopAPI
    monkeypatch.setattr("arxiv_digest.desktop.search_all", Mock(return_value=[search_paper()]))
    monkeypatch.setattr("arxiv_digest.desktop.fetch_impact", lambda ids: {})
    api = DesktopAPI()
    assert json.loads(api.search("tracking", "[]", 10, "0", False))["ok"]
    monkeypatch.setattr("arxiv_digest.desktop.search_all", Mock(side_effect=AssertionError("network")))
    result = json.loads(api.generate_survey(limit=1, pdf=False, out_dir=str(tmp_path)))
    assert result["ok"] and "Transformer tracking" in result["markdown"]
    assert json.loads((tmp_path / "papers.json").read_text("utf-8"))[0]["authors"] == ["Alice", "Bob"]


def test_empty_desktop_handoff_has_readable_error():
    from arxiv_digest.desktop import DesktopAPI
    assert not json.loads(DesktopAPI().generate_survey())["ok"]


@pytest.mark.parametrize("mode,target", [("digest", "arxiv_digest.cli.main"),
                                          ("desktop", "arxiv_digest.desktop.main")])
def test_unified_cli_dispatches_legacy_modes(monkeypatch, mode, target):
    from litreview.cli import main
    handler = Mock(return_value=0)
    monkeypatch.setattr(target, handler)
    assert main([mode]) == 0
    handler.assert_called_once()


def test_survey_and_desktop_share_llm_credentials(tmp_path, monkeypatch):
    from arxiv_digest import llm
    from litreview.llm import llm_from_config
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(llm, "LEGACY_CONFIG_PATH", tmp_path / "old.json")
    llm.save_credentials("test-key", "https://example.org/v1", "test-model")
    client = llm_from_config()
    assert client.api_key == "test-key" and client.model == "test-model"


@pytest.mark.parametrize("command", ["search", "survey", "legacy"])
def test_cli_runs_shared_pipeline_without_external_calls(tmp_path, monkeypatch, capsys, command):
    from litreview.cli import main
    monkeypatch.setattr("litreview.discovery.search_all", Mock(return_value=[search_paper()]))
    monkeypatch.setattr("litreview.agent.LitReviewAgent", lambda **kw: LitReviewAgent(
        cache_dir=tmp_path / "cache", **kw))
    args = ([] if command == "legacy" else [command]) + [
        "tracking", "--limit", "1", "--no-pdf", "--no-llm", "--out", str(tmp_path / "out")]
    assert main(args) == 0
    output = capsys.readouterr().out
    if command == "search":
        assert json.loads(output)[0]["id"] == "2610.10001"
    else:
        assert "survey:" in output
        assert (tmp_path / "out" / "papers.json").is_file()


@pytest.mark.parametrize("arguments", [["--limit", "0"], ["--days", "0"]])
def test_cli_rejects_invalid_search_options(arguments):
    from litreview.cli import main
    with pytest.raises(SystemExit) as error:
        main(["search", "tracking"] + arguments)
    assert error.value.code == 2


def test_discovery_exposes_source_failure(monkeypatch):
    from litreview.sources import SourceError
    monkeypatch.setattr("litreview.discovery.search_all", Mock(side_effect=OSError("unavailable")))
    with pytest.raises(SourceError, match="unavailable"):
        DiscoverySource().search("tracking")

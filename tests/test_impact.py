"""影响力层测试：Semantic Scholar 批量响应解析、评分与降级。"""

import io
import json

from arxiv_digest.impact import ImpactInfo, fetch_impact


def _respond(monkeypatch, payload):
    body = json.dumps(payload).encode("utf-8")

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        "arxiv_digest.impact.urllib.request.urlopen",
        lambda req, timeout=None: Resp(body),
    )


def test_fetch_impact_parses_batch_response(monkeypatch):
    """逐位对应输入 id；null 记录（S2 无该论文）被跳过。"""
    _respond(monkeypatch, [
        {"citationCount": 57, "influentialCitationCount": 8,
         "venue": "CVPR", "year": 2025, "publicationVenue": None},
        None,
        {"citationCount": 0, "influentialCitationCount": 0, "venue": "",
         "year": None, "publicationVenue": {"name": "ICLR"}},
    ])
    result = fetch_impact(["2610.1", "2610.2", "2610.3"])
    assert set(result) == {"2610.1", "2610.3"}
    assert result["2610.1"].citations == 57
    assert result["2610.1"].venue == "CVPR"
    assert result["2610.3"].venue == "ICLR"  # venue 回落到 publicationVenue.name
    assert result["2610.3"].year is None


def test_fetch_impact_degrades_on_failure(monkeypatch):
    """网络失败返回空 dict，不抛异常。"""
    def boom(req, timeout=None):
        raise OSError("no network")

    monkeypatch.setattr("arxiv_digest.impact.urllib.request.urlopen", boom)
    assert fetch_impact(["2610.1"]) == {}
    assert fetch_impact([]) == {}


def test_impact_score_scale():
    """对数综合分：无数据为 None，有数据落在 0-10。"""
    assert ImpactInfo().score is None
    s0 = ImpactInfo(citations=0).score
    s100 = ImpactInfo(citations=100, influential=10).score
    assert s0 == 0.0
    assert 0 < s100 <= 10
    assert ImpactInfo(citations=10**9, influential=10**9).score == 10.0

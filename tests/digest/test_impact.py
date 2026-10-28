"""影响力层测试：S2 批量解析、限流重试、OpenAlex 兜底与降级，全部离线。"""

import io
import json
import urllib.error

from arxiv_digest.impact import ImpactInfo, fetch_impact, probe_providers


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


def _no_openalex(monkeypatch):
    monkeypatch.setattr("arxiv_digest.impact.fetch_impact_openalex",
                        lambda ids, timeout=None: (_ for _ in ()).throw(OSError("down")))


def _fast_retry(monkeypatch):
    monkeypatch.setattr("arxiv_digest.impact.time.sleep", lambda _s: None)


def test_fetch_impact_parses_batch_response(monkeypatch):
    """逐位对应输入 id；null 记录（S2 无该论文）被跳过。"""
    _respond(monkeypatch, [
        {"citationCount": 57, "influentialCitationCount": 8,
         "venue": "CVPR", "year": 2025, "publicationVenue": None},
        None,
        {"citationCount": 0, "influentialCitationCount": 0, "venue": "",
         "year": None, "publicationVenue": {"name": "ICLR"}},
    ])
    _no_openalex(monkeypatch)
    result = fetch_impact(["2610.1", "2610.2", "2610.3"])
    assert set(result) == {"2610.1", "2610.3"}
    assert result["2610.1"].citations == 57
    assert result["2610.1"].venue == "CVPR"
    assert result["2610.3"].venue == "ICLR"  # venue 回落到 publicationVenue.name
    assert result["2610.3"].year is None


def test_fetch_impact_retries_on_429(monkeypatch):
    """S2 限流（429）时应重试而不是立刻放弃。"""
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests", None, io.BytesIO(b""))
        body = json.dumps([{"citationCount": 9, "influentialCitationCount": 1,
                            "venue": "AAAI", "year": 2026}]).encode("utf-8")

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Resp(body)

    monkeypatch.setattr("arxiv_digest.impact.urllib.request.urlopen", flaky)
    _no_openalex(monkeypatch)
    _fast_retry(monkeypatch)
    result = fetch_impact(["2610.9"])
    assert calls["n"] == 2  # 第一次 429，第二次成功
    assert result["2610.9"].citations == 9


def test_fetch_impact_falls_back_to_openalex(monkeypatch):
    """S2 全部失败时切换 OpenAlex 兜底（无高影响力引用数，但引用/venue 真实）。"""
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", None, io.BytesIO(b""))

    monkeypatch.setattr("arxiv_digest.impact.urllib.request.urlopen", boom)
    _fast_retry(monkeypatch)
    monkeypatch.setattr(
        "arxiv_digest.impact.fetch_impact_openalex",
        lambda ids, timeout=None: {"2610.5": {"citations": 120, "venue": "Nature", "year": 2024}},
    )
    result = fetch_impact(["2610.5"])
    assert result["2610.5"].citations == 120
    assert result["2610.5"].venue == "Nature"
    assert result["2610.5"].influential is None  # OpenAlex 无高影响力引用数


def test_fetch_impact_degrades_on_total_failure(monkeypatch):
    """两个来源都失败返回空 dict，不抛异常。"""
    def boom(req, timeout=None):
        raise OSError("no network")

    monkeypatch.setattr("arxiv_digest.impact.urllib.request.urlopen", boom)
    _fast_retry(monkeypatch)
    monkeypatch.setattr(
        "arxiv_digest.impact.fetch_impact_openalex",
        lambda ids, timeout=None: (_ for _ in ()).throw(OSError("down")),
    )
    assert fetch_impact(["2610.1"]) == {}
    assert fetch_impact([]) == {}


def test_probe_providers_reports_both(monkeypatch):
    """探测接口分别报告 S2 与 OpenAlex 可用性。"""
    body = json.dumps([{"citationCount": 1}]).encode("utf-8")

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("arxiv_digest.impact.urllib.request.urlopen",
                        lambda req, timeout=None: Resp(body))
    monkeypatch.setattr("arxiv_digest.impact.fetch_impact_openalex",
                        lambda ids, timeout=None: {"1706.03762": {"citations": 1,
                                                                 "venue": "", "year": None}})
    result = probe_providers()
    assert result == {"semantic_scholar": True, "openalex": True}


def test_impact_score_scale():
    """对数综合分：无数据为 None，有数据落在 0-10。"""
    assert ImpactInfo().score is None
    s0 = ImpactInfo(citations=0).score
    s100 = ImpactInfo(citations=100, influential=10).score
    assert s0 == 0.0
    assert 0 < s100 <= 10
    assert ImpactInfo(citations=10**9, influential=10**9).score == 10.0

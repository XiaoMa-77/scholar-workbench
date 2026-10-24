"""LLM 层测试：Key 跳过逻辑、JSON 容错解析与失败降级，全部离线。"""

import io
import json

from arxiv_digest import llm
from arxiv_digest.fetcher import parse_atom
from arxiv_digest.llm import Credentials, _extract_json, load_credentials, review_paper

from fixtures_atom import ATOM_FIXTURE, KEYWORDS


def fake_urlopen_with_content(content: str):
    """构造一个返回指定回复文本的假 urlopen。"""

    def fake(req, timeout=None):
        body = json.dumps({"choices": [{"message": {"content": content}}]})
        return io.BytesIO(body.encode("utf-8"))

    return fake


def test_no_key_returns_none(monkeypatch):
    """未设置 LLM_API_KEY 时应返回 None（跳过 LLM）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert load_credentials() is None


def test_blank_key_is_skipped(monkeypatch):
    """Key 为空白字符串时同样跳过。"""
    monkeypatch.setenv("LLM_API_KEY", "   ")
    assert load_credentials() is None


def test_credentials_read_env(monkeypatch):
    """有 Key 时应读全三项配置，base_url 去掉末尾斜杠。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("LLM_MODEL", "demo-model")
    creds = load_credentials()
    assert creds == Credentials(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="demo-model",
    )


def test_extract_json_tolerates_noise():
    """JSON 提取应容忍代码块包裹与前后噪声，非法输入返回 None。"""
    assert _extract_json('```json\n{"score": 8}\n```') == {"score": 8}
    assert _extract_json('前置说明 {"a": 1} 后缀') == {"a": 1}
    assert _extract_json("完全不是 JSON") is None


def test_review_paper_parses_valid_response(monkeypatch):
    """合法回复（含代码块包裹、字符串分数）应被正确解析。"""
    paper = parse_atom(ATOM_FIXTURE)[0]
    creds = Credentials(api_key="fake", base_url="https://api.example.com", model="x")
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        fake_urlopen_with_content(
            '{"score": "8", "reason": "高度相关", "abstract_zh": "中文摘要"}'
        ),
    )
    result = review_paper(paper, KEYWORDS, creds)
    assert result is not None
    assert result.score == 8.0
    assert result.reason == "高度相关"
    assert result.abstract_zh == "中文摘要"


def test_review_paper_degrades_on_bad_json(monkeypatch):
    """回复不含 JSON 时应返回 None 降级，而不是抛异常。"""
    paper = parse_atom(ATOM_FIXTURE)[0]
    creds = Credentials(api_key="fake", base_url="https://api.example.com", model="x")
    monkeypatch.setattr(
        llm.urllib.request, "urlopen", fake_urlopen_with_content("我拒绝用 JSON 回答")
    )
    assert review_paper(paper, KEYWORDS, creds) is None


def test_review_paper_degrades_on_network_error():
    """接口不可达（本地未监听端口）时应返回 None 降级。"""
    paper = parse_atom(ATOM_FIXTURE)[0]
    creds = Credentials(api_key="fake", base_url="http://127.0.0.1:9", model="x")
    assert review_paper(paper, KEYWORDS, creds) is None


def test_rerank_skips_without_credentials():
    """无凭据时 rerank 应直接跳过，不修改任何条目。"""
    scored = []
    llm.rerank(scored, KEYWORDS, None, top_n=5)  # 不应抛异常
    assert scored == []

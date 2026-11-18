"""LLM 层测试：Key 跳过逻辑、JSON 容错解析与失败降级，全部离线。"""

import io
import json

from arxiv_digest import llm
from arxiv_digest.fetcher import parse_atom
from arxiv_digest.llm import (
    Credentials,
    _extract_json,
    load_credentials,
    review_paper,
    save_credentials,
)

from fixtures_atom import ATOM_FIXTURE, KEYWORDS


def fake_urlopen_with_content(content: str):
    """构造一个返回指定回复文本的假 urlopen。"""

    def fake(req, timeout=None):
        body = json.dumps({"choices": [{"message": {"content": content}}]})
        return io.BytesIO(body.encode("utf-8"))

    return fake


def test_no_key_returns_none(monkeypatch, tmp_path):
    """未设置 LLM_API_KEY 且无本地配置时应返回 None（跳过 LLM）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    assert load_credentials() is None


def test_blank_key_is_skipped(monkeypatch, tmp_path):
    """环境变量 Key 为空白时回落到配置文件；两者皆无则跳过。"""
    monkeypatch.setenv("LLM_API_KEY", "   ")
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    assert load_credentials() is None


def test_credentials_read_env(monkeypatch, tmp_path):
    """有 Key 时应读全三项配置，base_url 去掉末尾斜杠；环境变量优先于配置文件。"""
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    save_credentials("sk-from-file", "https://file.example.com/v1", "file-model")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("LLM_MODEL", "demo-model")
    creds = load_credentials()
    assert creds == Credentials(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="demo-model",
    )


def test_credentials_read_config_file(monkeypatch, tmp_path):
    """未设环境变量时读取配置文件；空 base_url/model 回落默认值。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    config_path = tmp_path / "llm.json"
    monkeypatch.setattr(llm, "CONFIG_PATH", config_path)
    assert load_credentials() is None  # 文件尚不存在
    save_credentials("sk-file", "", "")
    creds = load_credentials()
    assert creds == Credentials(
        api_key="sk-file",
        base_url=llm.DEFAULT_BASE_URL,
        model=llm.DEFAULT_MODEL,
    )


def test_mask_key_hides_middle():
    assert llm.mask_key("") == ""
    assert llm.mask_key("short") == "*****"
    masked = llm.mask_key("sk-1234567890abcdef")
    assert masked.startswith("sk-123") and masked.endswith("cdef")
    assert "7890" not in masked


def test_test_credentials_reports_unreachable_endpoint(monkeypatch, tmp_path):
    """端点不可达时 test_credentials 返回 (False, 可读信息)。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "llm.json")
    ok, message = llm.test_credentials()
    assert ok is False
    assert "未配置" in message
    save_credentials("sk-x", "http://127.0.0.1:9/v1", "m")
    ok, message = llm.test_credentials()
    assert ok is False
    assert "调用失败" in message


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


def test_review_paper_degrades_on_invalid_score_fields(monkeypatch):
    """score 缺失或非数值时返回 None 降级，而不是抛 KeyError/TypeError/ValueError。"""
    paper = parse_atom(ATOM_FIXTURE)[0]
    creds = Credentials(api_key="fake", base_url="https://api.example.com", model="x")
    for content in (
        '{"reason": "缺少分数字段"}',
        '{"score": "not-a-number", "reason": "坏分数"}',
        '{"score": null, "reason": "空分数"}',
    ):
        monkeypatch.setattr(
            llm.urllib.request, "urlopen", fake_urlopen_with_content(content)
        )
        assert review_paper(paper, KEYWORDS, creds) is None


def test_rerank_applies_results_only_to_top_n(monkeypatch):
    """LLM 结果只回填到规则分 Top N，其余条目保持纯规则分。"""
    from arxiv_digest.llm import LLMResult
    from arxiv_digest.scorer import score_paper

    paper = parse_atom(ATOM_FIXTURE)[0]
    high = score_paper(paper, [("vision-language", 3.0)])  # 规则分更高
    low = score_paper(paper, [("diffusion", 1.0)])
    scored = [low, high]
    creds = Credentials(api_key="fake", base_url="https://api.example.com", model="x")
    reviewed = []

    def fake_review(p, keywords, creds):
        reviewed.append(p.title)
        return LLMResult(score=7.0, reason="相关", abstract_zh="中译摘要")

    monkeypatch.setattr(llm, "review_paper", fake_review)
    llm.rerank(scored, KEYWORDS, creds, top_n=1)

    assert reviewed == [high.paper.title]  # 只评审规则分最高的一篇
    assert high.llm_score == 7.0 and high.llm_reason == "相关"
    assert high.abstract_zh == "中译摘要"
    assert low.llm_score == 0.0 and low.abstract_zh is None

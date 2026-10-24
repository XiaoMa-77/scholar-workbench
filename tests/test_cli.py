"""CLI 层测试：配置加载与参数解析。"""

import pytest

from arxiv_digest.cli import build_parser, load_config


def test_load_config_defaults_without_file(tmp_path, monkeypatch):
    """未指定配置且当前目录没有 config.yaml 时，使用内置默认值。"""
    monkeypatch.chdir(tmp_path)
    config = load_config(None)
    assert config["categories"] == ["cs.CV", "cs.CL"]
    assert config["top_n"] == 10
    assert config["report_dir"] == "reports"
    assert config["lookback_days"] == 2


def test_load_config_reads_yaml_and_falls_back(tmp_path):
    """显式指定的 YAML 应生效，未覆盖的字段落回内置默认值。"""
    file = tmp_path / "my.yaml"
    file.write_text("categories: [cs.RO]\ntop_n: 5\n", encoding="utf-8")
    config = load_config(str(file))
    assert config["categories"] == ["cs.RO"]
    assert config["top_n"] == 5
    assert config["report_dir"] == "reports"


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nope.yaml"))


def test_parser_flags():
    """--date/--top/--no-llm/--config 均应被正确解析。"""
    args = build_parser().parse_args(
        ["--date", "2026-10-24", "--top", "5", "--no-llm", "--config", "c.yaml"]
    )
    assert args.date == "2026-10-24"
    assert args.top == 5
    assert args.no_llm is True
    assert args.config == "c.yaml"

    defaults = build_parser().parse_args([])
    assert defaults.date is None
    assert defaults.top is None
    assert defaults.no_llm is False

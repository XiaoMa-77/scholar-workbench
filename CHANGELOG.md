# 更新日志

本项目的显著变更记录于此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.1] - 2026-10-24

### 文档

- README 新增两张配图：工作流程图（`docs/pipeline.png`，抓取 → 过滤 → 双层打分 → 日报 → 定时自动运行闭环）与日报效果图（`docs/report-preview.png`，由 example.md 数据渲染）。

## [0.1.0] - 2026-10-24

### 新增

- arXiv Atom API 抓取：多分类联合查询（`cat:xxx OR cat:yyy`）、按提交时间降序取回、本地按发表日期过滤（默认昨天 + 今天，可配）。
- 关键词规则打分：标题命中记 3×权重、摘要命中记 1×权重，关键词可单独配置权重，完全离线可跑。
- 可选 LLM 精排：OpenAI 兼容 `chat/completions` 协议（支持 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`），对规则分 Top N 的论文输出 0-10 相关性分、一句话理由与摘要中译，失败自动降级为规则分。
- Markdown 日报生成：`reports/YYYY-MM-DD.md`，含统计概览与逐篇详情（排名、分数、标题、作者、链接、命中说明、摘要）。
- CLI：`arxiv-digest`，支持 `--config` / `--date` / `--top` / `--no-llm` / `--version`。
- GitHub Actions：每日定时任务（北京时间 08:30，自动提交日报回仓库）与 CI（ruff + pytest）。
- 离线单元测试：内嵌 Atom fixture 覆盖解析、打分、渲染与 LLM 降级逻辑。

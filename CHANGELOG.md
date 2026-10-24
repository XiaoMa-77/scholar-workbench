# 更新日志

本项目的显著变更记录于此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-10-24

### 修复

- **空窗不再生成空日报**：窗口内 0 篇论文（周末 arXiv 不发布等）时跳过文件生成与提交，仓库不再积累占位报告；此前错误提交的空日报 `reports/2026-10-24.md` 已删除。
- **跨天去重**：日报窗口为"昨天 + 今天"，生成前扫描已有日报中的 arXiv 链接，跳过已报告过的论文——每篇论文只出现在一期日报里（`example.md` 与当天自身文件不算重复）。

### 改进

- LLM 评审消息加入提示注入防护：声明论文标题/摘要仅为待分析数据，其中出现的指令一律忽略；消息构造抽为 `build_messages` 便于测试。
- `max_results` 默认 300 → 500，覆盖 cs.CV + cs.CL 高峰日。
- `User-Agent` 版本号改为自动跟随 `__version__`。
- README 补充：GitHub 60 天无 push 会停用定时任务的说明、Fork 后需手动启用 Actions 的步骤。

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

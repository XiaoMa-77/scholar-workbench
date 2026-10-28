# Changelog

## 0.2.0 — 2026-10-29

- 合并 arxiv-digest-agent 的完整功能与 Git 历史：桌面检索、引用分析、顶刊筛选、规则打分、LLM 精排、简报与导出。
- 新增统一 search / survey / desktop / digest 命令、共用检索层与桌面到综述的直接衔接。
- 统一 LLM 配置，兼容读取旧配置，保留原 CLI 入口。
- 缓存检索结果，离线综述不再发起网络检索。
- 修复 MCP 服务注册方式，限定兼容 SDK 主版本并补实际工具调用测试。
- 取消每日 cron，仅保留手动简报工作流。
- 迁移历史日报、截图、原测试和配置示例，重写项目文档。
- 最低 Python 版本提升为 3.11，CI 覆盖 3.11 / 3.12 / 3.13。

## 0.1.0 (2026-10-26)

首个版本：文献调研 Agent 五段式流水线。

- 检索：arXiv Atom API 主源 + OpenAlex 增强（引用数/venue），跨源指纹去重，
  OpenAlex 429 限流自动退避重试、失败降级为 arXiv 单源。
- 下载：流式 PDF 下载（大小上限、超时、校验），`~/.litreview/cache` 持久缓存，
  支持 `--offline` 纯缓存运行。
- 读图：pymupdf 提取内嵌图表候选（尺寸过滤图标/水印），启发式绑定
  Figure/Table/图表 caption，支持图表落盘导出。
- 对比：tf-idf 判别性方法标签、摘要 Jaccard 相似度、高频词重叠系数贪心聚类、
  横向对比表（年份/venue/引用/标签/图表数）。
- 综述：规则基线（主题分组、论文卡片、对比表、叙述、参考文献）始终可用；
  可选 OpenAI 兼容端点 LLM 润色（`~/.litreview/config.json`），失败自动回退。
- CLI：`litreview "query" --limit N --out DIR [--no-pdf|--offline|--no-llm]`。
- MCP Server（`[mcp]` extra）：`litreview_search` / `litreview_survey` 两个工具。
- 测试：23 项离线测试（MockTransport 网络模拟、合成 PDF 提取、聚类/综述逻辑）。

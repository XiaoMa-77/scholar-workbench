# Changelog

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

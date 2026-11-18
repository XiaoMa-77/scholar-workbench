# 🧭 Scholar Workbench · 设计文档

> 版本：v0.2 · 更新：2026-11-18
> 本文描述 `scholar-workbench` 的设计背景、架构、接口、数据流与边界/异常场景。
> 事实性内容均来自仓库现有源码（`src/arxiv_digest/`、`src/litreview/`）、
> `pyproject.toml`、README 与测试；无法从代码确认的部分在文末「假设与待确认」中显式列出。

---

## 1. 背景与目标

### 1.1 问题

科研文献调研被拆成彼此割裂的几步：检索（arXiv / OpenAlex）、相关度排序、引用影响力查询、
PDF 下载与图表清点、跨论文比较，最后还要人工写成中文综述；而每日论文追踪又需要另一套抓取、
打分与去重。原项目由 `arxiv-digest-agent`（日报/桌面检索）与 `lit-review-agent`
（PDF/对比/综述/MCP）两个仓库分别承担，功能、测试与配置各自维护。

### 1.2 目标

- **一体化**：把「检索 → 打分 → 筛选 → PDF 图表 → 跨论文比较 → 中文综述」串成一条流水线，
  同时保留独立的「按需简报」工作流。
- **多入口**：CLI、桌面窗口、MCP stdio 服务共用同一套检索与排序实现；桌面端直接复用本次
  检索结果，不再二次检索。
- **可降级**：任一外部来源（arXiv / OpenAlex / Semantic Scholar / LLM）失败都不阻塞主流程，
  保留可用元数据与规则结果。
- **可复现**：检索结果与 PDF 缓存在本地，`--offline` 可完全离线复现同一份综述。
- **可验证**：网络与 LLM 全部 mock 的离线测试守门，CI 覆盖 Python 3.11 / 3.12 / 3.13。
- **兼容迁移**：保留原 `litreview` / `arxiv-digest` 全套命令、模块名、MCP 工具名与
  `~/.litreview/` 配置缓存路径。

### 1.3 非目标

- 不做账号系统、不做文献管理（Zotero 式库）、不提供付费数据库全文；
- 不保证第三方 API 数据 100% 准确，图表清单是「候选」而非最终人工判读结果；
- LLM 只做可选精排和叙述润色，不负责产生事实（事实一律来自已采集的结构化数据）。

---

## 2. 总体架构

系统由两个子包组成：`arxiv_digest` 负责数据源接入、规则打分、简报与桌面桥接，
`litreview` 负责归一化模型、PDF/图表、比较、综述与 MCP。CLI 与桌面共用前者的检索层。

```
   外部数据源                      arxiv_digest（检索 / 打分 / 简报 / 桌面）
┌───────────────────┐       ┌──────────────────────────────────────────────┐
│ arXiv Atom API    │◄─────►│ search.py / fetcher.py      多源检索与去重     │
│ OpenAlex Works    │◄─────►│ openalex.py / http.py       限流退避/批量查询  │
│ Semantic Scholar  │◄─────►│ impact.py                   引用分析+S2→OA兜底 │
│ 用户 LLM 端点     │◄─────►│ llm.py                      精排/中译/凭据共用 │
└───────────────────┘       │ scorer.py                   带权关键词规则分  │
                            │ venues.py / reporter.py     顶刊清单/日报去重  │
                            │ desktop.py + web/index.html pywebview 桥接    │
                            └───────────────┬──────────────────────────────┘
                                            │ Paper → 归一化转换
                     ┌──────────────────────▼──────────────────────────────┐
                     │ litreview（PDF / 图表 / 比较 / 综述 / MCP）           │
                     │ discovery.py  → models.py                           │
                     │ pdf.py        → compare.py → survey.py → agent.py   │
                     │ cli.py / mcp_server.py / llm.py                     │
                     └───────────────┬──────────────────────────────────────┘
                                     │ survey_<query>.md + papers.json
                                     ▼
                         CLI / 桌面 / MCP 三个入口共享该产物
```

### 2.1 模块职责

| 子包 | 模块 | 职责 |
|---|---|---|
| `arxiv_digest` | `fetcher.py` | arXiv Atom 查询构造、XML 解析、`Paper` 数据类、日期窗口过滤 |
| `arxiv_digest` | `search.py` | 检索词解析、AND/OR 查询构造、单源/多源调度、跨源去重合并 |
| `arxiv_digest` | `http.py` | 只读请求的有限重试（429/5xx，指数退避） |
| `arxiv_digest` | `openalex.py` | 正式论文检索、顶刊过滤、摘要倒排还原、批量 DOI 影响力和开放 PDF |
| `arxiv_digest` | `impact.py` | Semantic Scholar 批量引用 → OpenAlex 兜底 → 无数据降级；影响力对数分 |
| `arxiv_digest` | `venues.py` | 内置顶刊顶会清单：归一化精确匹配 + 子串包含匹配 |
| `arxiv_digest` | `scorer.py` | 关键词归一化（3 种写法）、带权打分、最终分与排序 |
| `arxiv_digest` | `llm.py` | 凭据读取顺序、OpenAI 兼容调用、坏 JSON 容错、精排与脱敏 |
| `arxiv_digest` | `reporter.py` | 简报 Markdown 渲染、历史链接收集与写盘 |
| `arxiv_digest` | `cli.py` | `arxiv-digest` 兼容入口：抓取→打分→精排→简报 |
| `arxiv_digest` | `desktop.py` / `web/index.html` | pywebview 窗口、`DesktopAPI` 桥接、CSV/BibTeX 导出 |
| `litreview` | `models.py` | 与来源无关的 `Paper` / `FigureCard` / `PaperContent`，含跨源指纹 |
| `litreview` | `sources.py` | 可注入 `httpx.Client` 的 arXiv/OpenAlex 来源，保留兼容与合并能力 |
| `litreview` | `discovery.py` | 共用检索层 → 综述模型的转换、规则排序与筛选参数透传 |
| `litreview` | `pdf.py` | 流式 PDF 下载（大小上限）、文本/内嵌图像提取、图注邻近匹配 |
| `litreview` | `compare.py` | tf-idf 判别性标签、Jaccard 相似度、贪心聚类、横向对比表 |
| `litreview` | `survey.py` | 规则综述（始终可用）+ 可选 LLM 叙述润色 |
| `litreview` | `agent.py` | 流水线编排、检索/PDF 缓存、逐级降级、`SurveyResult` |
| `litreview` | `cli.py` | 统一 `scholar-workbench` 入口；分发 search / survey / desktop / digest |
| `litreview` | `mcp_server.py` | FastMCP 1.x stdio 工具注册 |

### 2.2 核心数据模型

| 模型 | 文件 | 关键字段 / 语义 |
|---|---|---|
| `Paper`（检索侧） | `fetcher.py` | `arxiv_id / title / authors / abstract / categories / published / link`，
扩展 `source / doi / citations / venue / pdf_url` |
| `ScoredPaper` | `scorer.py` | `paper / score / matched / llm_score / llm_reason / abstract_zh`；
`final_score = score + llm_score` |
| `Paper`（综述侧） | `models.py` | `id / title / authors / year / venue / abstract / url / pdf_url /
citations / source / primary_category / published / doi`；`fingerprint()` 按 arXiv ID → DOI → 标题定序 |
| `FigureCard` | `models.py` | `kind`（figure/table）、`page`、`caption`、宽高；
`is_likely_real` 要求 ≥ 120×90 像素 |
| `PaperContent` | `models.py` | `pages / text_chars / text / figures`；`figure_count` 只数真实候选 |
| `SurveyResult` | `agent.py` | `papers / contents / survey_md / report_path / pdf_errors / source_errors` |

---

## 3. 接口设计

### 3.1 CLI

统一入口 `scholar-workbench`（`litreview.cli:main`），保留旧入口：
`litreview`、`scholar-workbench-desktop`、`scholar-workbench-mcp`、`arxiv-digest`、
`arxiv-digest-desktop`、`litreview-desktop`、`litreview-mcp`、`python -m arxiv_digest`。

| 命令 / 参数 | 行为 | 退出码 / 校验 |
|---|---|---|
| `scholar-workbench search "主题"` | 检索、去重、规则排序，向 stdout 写论文 JSON | 有结果 0，无结果/失败 1 |
| `scholar-workbench survey "主题"`（或省略子命令） | 检索 → PDF → 图表 → 比较 → 综述 | 同上 |
| `scholar-workbench desktop` | 启动桌面窗口 | — |
| `scholar-workbench digest [参数]` | 转发到 `arxiv_digest.cli.main` | 失败 1 |
| `--limit` | 保留论文数 | 1–300，越界 `parser.error` |
| `--source` | `all` / `arxiv` / `openalex` | argparse 枚举 |
| `--category` | arXiv 分类，可重复 | — |
| `--days` | 发表日期窗口 | 必须为正整数 |
| `--venues-only` / `--no-openalex` | 顶刊过滤 / 退回纯 arXiv | 兼容参数 |
| `--no-pdf` / `--no-llm` / `--offline` / `-v` | 跳过 PDF / 规则综述 / 纯缓存 / 详细日志 | — |

`digest` 子命令另有 `--config`（YAML）、`--date`（YYYY-MM-DD）、`--top`、`--no-llm`。
`--limit` 在 `search_papers` 内再夹一次到 1–300；用户中断返回 130。

### 3.2 桌面桥接（`DesktopAPI`）

pywebview 加载 `src/arxiv_digest/web/index.html`，前端通过
`window.pywebview.api.<方法>(...)` 调用；桥接层与窗口分离，可在无图形环境单测。
所有方法返回 JSON 字符串，前端 `callApi` 统一 `JSON.parse`；无 pywebview 时回退演示数据。

| 方法 | 参数 | 返回 |
|---|---|---|
| `search` | `query, categories(JSON 数组字符串), limit, days, use_llm, source, venues_only` | `{ok, rows, elapsed, impact_available, counts}` 或 `{ok:false, error}` |
| `generate_survey` | `limit, pdf, out_dir, use_llm` | `{ok, markdown, report_path, pdf_errors}`；无检索快照时 `ok:false` |
| `categories` | — | 常见 arXiv 分类 JSON |
| `llm_available` / `llm_config` | — | 是否配置 / 脱敏配置回显 |
| `save_llm_config` / `test_llm` | `api_key, base_url, model` | 保存结果 / 连通性信息 |
| `test_impact_providers` | — | `{semantic_scholar, openalex}` 可用性 |
| `export_csv` | `rows_json` | CSV 文本（保存对话框由调用方处理） |

行数据由 `build_rows` 组装：规则相关度 + 可选 LLM 分 + 影响力字段；无线上引用数据时为
`None`（前端显示「—」）而非报错。前端「生成综述」复用 `self._last_search` 中的论文对象。

### 3.3 MCP（`litreview.mcp_server`）

FastMCP 1.x（`mcp>=1.2,<2`）stdio 服务；`register(server, agent)` 注册两个工具，便于测试直接调用。

| 工具 | 参数 | 返回 |
|---|---|---|
| `litreview_search` | `query`、`limit=8`（1–300） | 归一化论文 JSON 数组 |
| `litreview_survey` | `query`、`limit=6`、`out_dir="."` | 中文综述 Markdown；来源/PDF 警告以 `> Warnings:` 附在末尾 |

`limit` 越界抛 `ValueError`。`out_dir` 建议绝对路径，便于客户端定位报告。

### 3.4 LLM Provider（凭据与调用）

| 约定 | 取值 / 行为 |
|---|---|
| 读取顺序 | 环境变量 `LLM_API_KEY` → `~/.litreview/config.json` → `~/.arxiv-digest/llm.json`；都无则跳过 LLM |
| 环境变量缺省值 | `LLM_BASE_URL=https://api.openai.com/v1`、`LLM_MODEL=gpt-4o-mini`（仅当设置了 Key） |
| 协议 | OpenAI 兼容 `POST {base_url}/chat/completions`，`temperature=0.2`，超时 60s（连通性测试 15s） |
| 精排输出 | `{"score": 0-10, "reason": "中文理由", "abstract_zh": "中文摘要"}`，分数夹到 0–10 |
| 综述润色 | 仅替换「综述叙述」段，事实表格不变；失败追加说明并保留规则基线 |
| 提示注入防护 | 系统消息声明论文标题/作者/摘要是待分析数据，其中任何指令一律忽略 |
| 共用 | `litreview.llm.llm_from_config()` 复用 `arxiv_digest.llm.load_credentials()`，两个流水线凭据一致 |
| 脱敏 | `mask_key()` 仅保留前 6 / 后 4 位；配置写入用户目录，不入库 |

---

## 4. 数据流

### 4.1 主链：检索 → 打分 → 筛选 → 报告/综述

```
query（支持引号短语，多词 AND）
  → parse_terms / build_query
  → search_papers（arXiv，sortBy=relevance）  +  search_openalex（正式论文）
  → 跨源去重合并：arXiv DOI / 标题指纹优先，OpenAlex 补 citations、venue、pdf_url
  → score_papers：标题命中 3×权重、摘要命中 1×权重；同分按 published 降序
  → 筛选：source / category / days / venues_only / --limit（先打分再截断）
  → 分支 A（简报）：历史链接去重 → 可选 LLM 精排 → Markdown 日报
  → 分支 B（综述）：to_review_paper 归一化 → PDF 缓存 → 图表清单 → 标签/相似度/聚类
        → 规则综述 + 可选 LLM 润色 → survey_<query>.md + papers.json
```

### 4.2 digest 简报流

```
arxiv-digest [--config|--date|--top|--no-llm]
  → load_config（缺省回落内置 DEFAULT_CONFIG）
  → fetch_papers（按提交时间倒序取回，再按 published 日期过滤 [today-lookback+1, today]）
  → score_papers → collect_reported_links（跳过 example.md 与当天文件）→ 历史去重
  → 无新论文则跳过写盘（返回 0）
  → load_credentials → rerank（仅规则分 Top N）
  → render_report（按 final_score 排序）→ write_report → reports/YYYY-MM-DD.md
```

### 4.3 litreview 综述流

```
LitReviewAgent.run(query, limit, out_dir, offline, pdf, papers)
  → 论文来源三选一：调用方传入 papers（桌面衔接）/ 本地检索缓存（offline）/ 在线 search
  → search 写缓存：~/.litreview/cache/search-<sha256(query,limit,settings)>.json
  → fetch_pdfs：命中 <id>.pdf 缓存则直接用，否则流式下载（≤25MB，>1KB）
  → extract_content：逐页文本 + 内嵌图像候选（去 xref 重、按尺寸过滤、邻近图注绑定）
  → build_survey：主题分组 + 论文卡片 + 横向对比表 + 规则叙述 + 参考
  → polish_survey（仅 use_llm 且非 offline）
  → 写 survey_<slug(query)>.md（slug 至多 40 字符）与 papers.json
```

### 4.4 桌面衔接与缓存

```
DesktopAPI.search  → search_all → fetch_impact → build_rows → _last_search = (query, papers)
  → 用户点「生成综述」→ to_review_paper(_last_search.papers) → agent.run(papers=...)
     （不再检索；某篇 PDF 失败时以元数据卡片继续参与综述）
```

离线缓存按「查询文本、limit、来源、分类、时间窗口、顶刊筛选」区分；先在线跑一次相同参数，
再加 `--offline` 即可复现。PDF 缓存与检索快照分开保存。

---

## 5. 边界与异常场景

| # | 场景 | 处理策略（代码依据） |
|---|---|---|
| 1 | arXiv / OpenAlex 临时 5xx、429 | `http.get_text` 对 429/500/502/503/504 重试 2 次，退避 `1.5×2^attempt` |
| 2 | 非重试类 HTTP 错误（如 403） | 立即抛出，不重试（`http.py`） |
| 3 | 网络断开 / 超时耗尽的重试 | 达到上限后抛出；由上层决定降级 |
| 4 | `source="all"` 单个来源失败 | 记录失败来源，只要另一来源有结果就继续；仅当全部失败才抛 `OSError("全部检索来源失败…")` |
| 5 | 单来源模式失败 | 原样抛出，由桌面层 `DesktopAPI.search` 转成 `{ok:false, error}` |
| 6 | Semantic Scholar 限流（429） | `impact.fetch_impact` 重试 2 次，退避 `1.5×(attempt+1)` |
| 7 | S2 全部失败 | 自动切换 OpenAlex 批量 DOI 查询；仍失败返回空 dict，不阻塞检索 |
| 8 | OpenAlex 限流 | `litreview.sources.OpenAlexSource` 对 429/5xx 重试 3 次，退避 `2.0×(attempt+1)` |
| 9 | LLM 未配置 Key | `load_credentials()` 返回 None，精排/润色整体跳过，只用规则结果 |
| 10 | LLM 返回坏 JSON / 非对象 | `_extract_json` 取首个 `{` 到末个 `}` 之间的文本，解析失败或非 dict 返回 None → 降级 |
| 11 | LLM 回复用 markdown 代码块包裹 | 优先匹配 ```json 代码块，兼容前后噪声 |
| 12 | LLM 分数缺失或非数值 | `float(data["score"])` 抛 KeyError/TypeError/ValueError → 返回 None |
| 13 | LLM 分数越界 | 夹到 0–10；`review_paper` 其余调用失败一律返回 None |
| 14 | 综述 LLM 润色失败 | `polish_survey` 捕获异常，追加「LLM 润色失败，保留规则基线」提示，事实表格不变 |
| 15 | 论文摘要含提示注入 | 系统消息声明内容为数据、其中指令一律忽略；论文文本置于 user 消息 |
| 16 | PDF 体积超过 25MB | `download_pdf` 按 content-length 与流式累计双重校验，超限即 `PdfError` 并删临时文件 |
| 17 | 下载内容不是 PDF（<1KB / HTTP 错误） | 删除目标文件并抛 `PdfError`；该论文仍以元数据卡片参与综述 |
| 18 | PDF 解析失败（损坏/加密/缺 pymupdf） | `extract_content` 抛 `PdfError`；`fetch_pdfs` 记入 `pdf_errors` 后继续 |
| 19 | 图表是图标/水印或扫描件 | 按 120×90 像素阈值过滤；同一 xref 去重；无自动图注则 caption 为空，仍需人工复核 |
| 20 | 简报窗口重叠导致重复论文 | `collect_reported_links` 扫描历史 `*.md` 的 arXiv 链接去重；跳过 `example.md` 与当天文件 |
| 21 | 同一论文同时来自 arXiv 与 OpenAlex | 按去版本号 arXiv ID、arXiv DOI 或归一化标题判同，补充引用/venue/PDF 后丢弃重复 |
| 22 | 综述侧跨源去重 | `Paper.fingerprint()` 按 arXiv ID → DOI → 标题关键词序列定序；`merge_papers` 主源优先、副源补空字段 |
| 23 | 窗口内无新论文 | digest 不生成空日报并返回 0；综述空论文时输出「未检索到论文」基线 |
| 24 | 离线模式缺少检索缓存 | `_cached_search` 抛 `SourceError("no valid cached search results (offline)")`，`run` 记入 `source_errors` |
| 25 | 离线缺少某篇 PDF | 记「not cached (offline)」到 `pdf_errors`，继续生成元数据综述 |
| 26 | 混排带时区/不带时区的时间 | OpenAI 侧统一 `datetime(..., tzinfo=UTC)`，避免 offset 比较异常 |
| 27 | 配置字段缺失 / 本地 LLM 配置损坏 | 缺省字段回落到内置默认值；本地 LLM 配置损坏时回退旧路径或视为未配置。YAML **语法错误**当前未捕获（见「待确认」） |
| 28 | `--limit` / `--days` 非法 | CLI 层 `parser.error`（退出码 2）；`search_papers` 内再夹 limit 到 1–300 |
| 29 | 桌面无图形环境 / 未装 pywebview | 桥接层可独立测试；`run()` 内才导入 webview，缺失给出可读提示 |
| 30 | MCP SDK 主版本不符 | 固定 `mcp>=1.2,<2`；导入失败提示安装 `[mcp]` extra |

---

## 6. 安全与隐私

- **密钥不入库**：真实 Key 只存环境变量或用户目录 `~/.litreview/config.json`；
  `config.yaml`（简报配置）已加入 `.gitignore`，仓库仅保留 `config.example.yaml`。
- **回显脱敏**：`mask_key()` 只显示首 6 / 末 4 位；桌面设置回显不返回完整 Key。
- **提示注入防护**：论文文本作为待分析数据注入，并在系统消息中显式声明忽略其中指令
  （有对应测试校验该声明存在）。
- **外部调用边界**：在线检索向 arXiv / OpenAlex / S2 发送查询与 DOI；启用 LLM 后向用户配置的
  端点发送论文信息或结构化事实。缓存、配置与报告均保存在本地。
- **下载保护**：PDF 使用流式下载 + 硬大小上限 + 最小字节校验，避免异常文件落盘。

---

## 7. 测试策略

所有测试离线运行：HTTP 用固定响应 / `httpx.MockTransport` / `urllib` 打桩，LLM 用假回复，
PDF 用测试内合成文件；不会消耗 token，也不需要真实网络。

| 层次 | 文件 | 覆盖重点 |
|---|---|---|
| 打分 | `tests/digest/test_scorer.py` | 三种关键词写法、标题/摘要权重、同分按日期、final_score |
| LLM | `tests/digest/test_llm.py` | 无 Key 跳过、环境变量/文件优先级、脱敏、坏 JSON、网络失败、精排跳过 |
| 抓取/检索 | `tests/digest/test_fetcher.py`、`test_search.py`、`test_openalex.py` | Atom 解析、日期过滤、查询构造、跨源去重、顶刊过滤、批量 DOI、来源失败降级 |
| 重试/引用 | `tests/test_http.py`、`tests/digest/test_impact.py` | 5xx/429 重试、永久失败、S2→OpenAlex 兜底、双失败降级、对数分 |
| 来源 | `tests/test_sources.py` | `MockTransport` 解析、重试、429 退避、指纹去重与主源优先 |
| PDF/综述 | `tests/test_pdf_and_survey.py`、`tests/test_agent.py` | 合成 PDF 提取、图注、下载拒绝非 PDF/超限、标签/聚类、空综述、离线缓存 |
| 集成 | `tests/test_integration.py`、`tests/digest/test_desktop.py` | 桌面衔接、共享检索与凭据、离线复现、桥接错误可读、CLI 分发 |
| 简报 | `tests/digest/test_cli.py`、`test_reporter.py`、`test_venues.py` | 配置回落、空窗/去重、日报渲染、顶刊清单 |
| MCP | `tests/test_mcp.py` | 工具注册与实际调用（需 `mcp<2`，见「待确认」） |
| CI | `.github/workflows/ci.yml` | 3.11/3.12/3.13 离线测试、ruff、CLI 冒烟、MCP 导入、compileall、构建 |

运行命令：

```bash
python -m pip install -e ".[pdf,mcp,dev]"
python -m pytest tests -q
python -m ruff check src
python -m compileall -q src tests
```

`docs/validation.md` 记录了合并版本的验证基线（115 项测试通过、语句覆盖率 89%）。

---

## 8. 假设与待确认

以下为无法仅凭当前代码确认，或在当前环境中存在差异的项，使用前请复核：

1. **默认 LLM 端点与模型**：`https://api.openai.com/v1` 与 `gpt-4o-mini` 是代码内置默认值，
   需要用户按实际服务配置；项目不绑定任何特定厂商。
2. **`config.example.yaml` 的 `max_results: 300`**：示例取 300，而 `arxiv_digest.cli.DEFAULT_CONFIG`
   的默认值是 500（注释为高峰期兜底）。二者都是合法取值，示例值不代表代码默认。
3. **顶刊顶会清单**：`venues.py` 为内置静态清单（归一化精确 + 子串），用于 `--venues-only` 过滤；
   其覆盖范围和口径属于项目启发式规则，不是任何权威目录的镜像，需按使用场景复核。
4. **图表清单质量**：图注靠邻近文字块正则匹配，尺寸阈值 120×90、表/图判定靠图注前缀；
   扫描件、矢量图与复杂表格可能漏检或误判，产出的是候选清单。
5. **引用数据口径**：`citations`/`influentialCitationCount` 来自 S2 或 OpenAlex 快照；
   项目用对数综合分作「影响力代理」，它不等于期刊影响因子，也不保证实时。
6. **外部服务额度与可用性**：arXiv / OpenAlex / S2 的限流策略、返回结构与免 Key 政策属于外部事实；
   重试/兜底规则是代码内的应对，不能保证第三方长期不变。
7. **综述事实边界**：可选 LLM 只重写「综述叙述」段，不改写事实表格、不新增论文；
   该约束由 prompt 与后处理实现，不能从机制上杜绝模型不听从指令的可能。
8. **MCP SDK 版本**：代码固定 `mcp>=1.2,<2`；当前验证环境安装的是 mcp 2.x，
   `FastMCP` 已更名，故 `tests/test_mcp.py` 在该环境无法收集。应在 `mcp<2` 环境中运行该项。
9. **桌面原生窗口**：自动化验证覆盖 HTML → 桥接 → 综述下载；原生 pywebview 窗口依赖操作系统
   图形环境（Windows WebView2），未在 CI 作为图形后端启动。
10. **简报去重依据**：历史去重依赖已有日报中的 arXiv 链接正则匹配；若历史文件格式变化或使用
    非 arXiv 来源，去重可能失效。
11. **损坏的 YAML 配置**：`arxiv_digest.cli.load_config` 未捕获 `yaml.YAMLError`，语法错误的
    `config.yaml` 会中断简报运行（字段**缺失**才会回落默认值）。若需优雅降级，应补充异常处理。

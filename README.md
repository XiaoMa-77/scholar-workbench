# arXiv 每日追踪 Agent

[![CI](https://github.com/XiaoMa-77/arxiv-digest-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/XiaoMa-77/arxiv-digest-agent/actions/workflows/ci.yml)

每天自动抓取指定 arXiv 分类的最新论文，按你的关键词打分排序，生成一份 Markdown 日报；可选接入任意 OpenAI 兼容大模型做相关性精排与摘要中译。纯本地 CLI + GitHub Actions 定时任务，无服务器、无数据库。

![工作流程](docs/pipeline.png)

日报效果（由 [reports/example.md](reports/example.md) 渲染）：

![日报效果](docs/report-preview.png)

## 功能特性

- **抓取**：直连 arXiv 官方 Atom API（urllib 实现，除 PyYAML 外零依赖），多分类联合查询（`cat:cs.CV OR cat:cs.CL`），按提交时间降序取回后按发表日期过滤，默认覆盖"昨天 + 今天"，窗口可配。
- **打分**：纯规则层完全离线可跑——标题命中记 3×权重、摘要命中记 1×权重，每个关键词可单独配置权重。
- **LLM 精排（可选）**：设置 `LLM_API_KEY` 后，对规则分 Top N 的论文调用 OpenAI 兼容 `chat/completions` 接口（支持 `LLM_BASE_URL` / `LLM_MODEL` 自定义端点与模型），得到 0-10 相关性分、一句话中文理由和摘要中译；无 Key 或调用失败时自动降级为规则分，绝不阻塞日报。
- **日报**：输出 `reports/YYYY-MM-DD.md`，开头是统计概览（总篇数、Top 分数），正文逐篇给出排名、分数、标题、作者（前三位 + et al.）、arXiv 链接、命中关键词或 LLM 理由、摘要（有 LLM 时为中文翻译）。
- **全自动**：GitHub Actions 每天北京时间 08:30 自动运行并把新日报提交回仓库，也支持手动触发。

## 快速开始

要求 Python 3.11+。

```bash
git clone https://github.com/XiaoMa-77/arxiv-digest-agent.git
cd arxiv-digest-agent
pip install -e .

# 直接运行（无配置时使用内置默认：cs.CV + cs.CL 与一组通用 CV 关键词）
arxiv-digest

# 使用自己的配置
cp config.example.yaml config.yaml   # 按需编辑分类与关键词
arxiv-digest --config config.yaml

# 常用参数
arxiv-digest --date 2026-10-24   # 指定日报日期（默认今天，窗口为昨天+今天）
arxiv-digest --top 20            # 日报展示前 20 篇
arxiv-digest --no-llm            # 跳过 LLM 精排，只用规则分
arxiv-digest --version
```

运行结束后日报位于 `reports/YYYY-MM-DD.md`。效果预览见 [reports/example.md](reports/example.md)。

## 桌面检索客户端

除了每日定时日报，本仓库还提供一个**交互式桌面检索工具**：输入关键词或整段研究方向描述，选择来源/分类/数量/时间范围，检索 arXiv 预印本与正式期刊会议论文，并计算每篇论文的规则相关度与学术影响力。

![桌面客户端](docs/desktop.png)

```bash
pip install "arxiv-digest-agent[desktop]"   # 或本地：pip install -e '.[desktop]'
arxiv-digest-desktop
```

功能与数据口径：

| 能力 | 说明 |
|---|---|
| 多来源检索 | **全部**（arXiv 预印本 + 期刊会议合并去重）/ **仅期刊与会议**（OpenAlex，覆盖 Nature、IEEE、Springer、ACM 等出版社）/ **仅 arXiv**；同一论文两边都有时按 arXiv DOI 或标题去重并合并引用数据 |
| 仅顶刊顶会过滤 | 内置 AI / 机器学习 / 视觉 / NLP / 机器人方向清单：Nature、Science、PNAS、TPAMI、IJCV、JMLR、AIJ、NeurIPS、ICML、ICLR、CVPR、ICCV、ECCV、AAAI、IJCAI、ACL、EMNLP、T-RO、IJRR、RA-L、Science Robotics、Nature Robotics、ICRA、IROS、CoRL、RSS 等；简写/全称兼容 |
| 关键词 / 研究方向检索 | 多个关键词取 AND（精确检索默认），按数据库相关度排序取回后统一打分 |
| 分类 / 数量 / 时间过滤 | 常见 cs.\* 分类多选（arXiv 来源），10~100 篇可选，近一周到一年或不限 |
| 相关度 | 关键词规则分（标题 ×3 / 摘要 ×1，与日报同源） |
| 学术影响力 | Semantic Scholar 优先（总引用数、高影响力引用数、正式发表 venue），限流时自动重试并切换 OpenAlex 兜底（引用数/venue）；"影响力分"为引用量对数综合分（0-10）——**arXiv 预印本没有期刊影响因子，本工具不编造，只用可溯源的引用数据** |
| LLM 精排（可选） | 点击右上角"LLM 精排"胶囊在弹窗中配置 API Key / Base URL / 模型（支持"测试连接"，保存到本机 `~/.arxiv-digest/llm.json`），配置后可对 Top 20 做 0-10 相关性精排 + 摘要中译；也可继续用环境变量 `LLM_API_KEY` |
| 引用数据源状态 | 点击右上角"引用数据源"胶囊实时探测 Semantic Scholar / OpenAlex 连通性 |
| 详情与导出 | 点击行看完整摘要/命中词/引用详情，一键复制 BibTeX（预印本 `@misc` / 期刊 `@article`）；结果可导出 CSV / Markdown |

界面为本地原生窗口（pywebview + WebView2），无服务器、无浏览器依赖、除三个学术 API（arXiv / OpenAlex / Semantic Scholar）外不联网。检索、多源合并、顶刊匹配、影响力兜底与桥接逻辑均有离线单元测试覆盖（66 项）。

## 配置说明

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `categories` | `[cs.CV, cs.CL]` | 监控的 arXiv 分类，多个按 OR 联合查询 |
| `keywords` | 内置 CV 关键词 | 关键词列表，支持 `{name: xxx, weight: N}` 带权重或纯字符串（权重 1）；也支持 `{关键词: 权重}` 映射写法 |
| `top_n` | `10` | 日报展示的论文数量上限 |
| `report_dir` | `reports` | 日报输出目录 |
| `max_results` | `500` | 单次从 arXiv 取回的最大论文数（cs.CV + cs.CL 高峰日的兜底） |
| `lookback_days` | `2` | 日期窗口（含指定日期当天），2 表示"昨天 + 今天" |

LLM 精排凭据读取顺序：环境变量优先，其次桌面端设置弹窗写入的 `~/.arxiv-digest/llm.json`。环境变量全部可选：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 无 | 设置后启用 LLM 精排与摘要中译，不设置则只用规则分 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 任意 OpenAI 兼容端点均可 |
| `LLM_MODEL` | `gpt-4o-mini` | 使用的模型名 |
| `OPENALEX_EMAIL` | 无 | 可选；填写后进入 OpenAlex 礼貌池，提升接口限额 |

## 每日自动运行

仓库自带两个 workflow：

- **`daily.yml`**：cron `30 0 * * *`（北京时间 08:30）自动抓取当天论文、生成日报并提交回 `reports/`；也支持在 Actions 页面手动触发（`workflow_dispatch`）。想启用 LLM 精排，在仓库 Settings → Secrets and variables → Actions 中配置 `LLM_API_KEY`（可选 `LLM_BASE_URL`、`LLM_MODEL`），未配置时自动降级为纯规则打分。
- **去重与空窗**：日报窗口为"昨天 + 今天"，生成前会扫描已有日报跳过已报告过的论文；窗口内没有新论文（如周末）时不生成文件，仓库不会积累空日报。
- **注意**：GitHub 会在仓库连续 60 天没有 push 时自动停用定时任务，任意一次 push 即重置计时；被停用后也可在 Actions 页面一键重新启用。
- **`.github/workflows/ci.yml`**：每次 push / PR 运行 `ruff check` 与 `pytest`，保证代码质量。

Fork 本仓库即可获得属于自己的每日 arXiv 日报流。注意：Fork 出的仓库默认禁用 Actions，需到 fork 仓库的 Actions 页面点击 "I understand my workflows, go ahead and enable them" 手动启用；如需 LLM 精排，还要在 fork 仓库的 Secrets 里配置 `LLM_API_KEY`。

## 仓库结构

```
arxiv-digest-agent/
├── .github/workflows/     # CI 与每日定时任务
├── reports/               # 生成的日报（example.md 为效果示例）
├── src/arxiv_digest/
│   ├── __init__.py        # 版本信息
│   ├── __main__.py        # python -m 支持
│   ├── cli.py             # 命令行入口与配置加载
│   ├── fetcher.py         # arXiv Atom API 抓取与解析（Paper 数据模型）
│   ├── search.py          # 检索层：arXiv + OpenAlex 多源编排与去重合并
│   ├── openalex.py        # OpenAlex：期刊/会议论文检索与影响力兜底
│   ├── venues.py          # 顶刊顶会清单与归一化匹配
│   ├── scorer.py          # 关键词规则打分
│   ├── impact.py          # 学术影响力（S2 优先 + OpenAlex 兜底）
│   ├── llm.py             # 可选 LLM 精排（OpenAI 兼容协议 + 本地配置）
│   ├── desktop.py         # 桌面客户端桥接层（pywebview js_api）
│   ├── web/index.html     # 桌面客户端前端
│   └── reporter.py        # Markdown 日报渲染
├── tests/                 # 离线单元测试（内嵌 Atom fixture）
├── config.example.yaml    # 配置示例
├── pyproject.toml
└── README.md
```

## 许可

代码与文档：[MIT](LICENSE)。

### 数据来源与归属

本工具检索与展示的数据来自第三方服务，其权利归各自所有者：

| 数据 | 来源 | 说明 |
|---|---|---|
| 论文元数据（标题/作者/摘要/分类） | [arXiv API](https://info.arxiv.org/help/api/user-manual.html) | arXiv 的元数据可自由使用，请遵其服务条款并注明出处 |
| 期刊/会议论文元数据与引用数 | [OpenAlex API](https://docs.openalex.org) | OpenAlex 数据以 [CC0](https://creativecommons.org/publicdomain/zero/1.0/) 为主，请遵其服务条款 |
| 引用数、高影响力引用、发表 venue | [Semantic Scholar API](https://api.semanticscholar.org) | Semantic Scholar 数据集采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，**非商业使用**；本工具仅作实时查询展示，不缓存再分发其数据 |

导出的 CSV / Markdown 结果包含上述来源的数据，请按同样口径使用（尤其是非商业限制）。

# 更新日志

本项目的显著变更记录于此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.4.0] - 2026-10-24

### 新增

- **多来源检索（桌面客户端）**：新增 OpenAlex 数据源，覆盖正式期刊与会议论文（Nature、IEEE、Springer、ACM 等出版社）。"来源"可选：全部（arXiv + 期刊会议合并去重）/ 仅期刊与会议 / 仅 arXiv 预印本；同一论文同时存在于两边时按 arXiv DOI 或标题去重，并把引用数/venue 合并到保留记录。
- **"仅顶刊顶会"过滤**（`venues.py`）：内置 AI / 机器学习 / 视觉 / NLP / 机器人方向顶刊顶会清单（Nature、Science、TPAMI、IJCV、JMLR、NeurIPS、CVMLR 系列、ACL、T-RO、IJRR、RA-L、Science Robotics、ICRA、IROS、CoRL、RSS 等），简写/全称两层归一化匹配，兼容不同数据库的 venue 写法。
- **LLM 精排设置弹窗**：顶部"LLM 精排"胶囊改为可点击，弹窗内配置 API Key / Base URL / 模型并支持"测试连接"，凭据保存到 `~/.arxiv-digest/llm.json`（环境变量 `LLM_API_KEY` 优先级不变）。
- **引用数据源连通性测试**：顶部"引用数据源"胶囊可点击，实时探测 Semantic Scholar 与 OpenAlex 可用性。
- **多来源容错**：合并检索模式下单个来源失败（如 arXiv 偶发 503）不拖垮整个检索，只要任一来源有结果即返回；OpenAlex 侧剔除 venue 为 arXiv 的预印本条目（正式发表论文才计入期刊/会议来源）。
- 测试 +24 项（顶刊匹配、OpenAlex 解析/过滤/分片、S2 重试与兜底、多源合并去重与容错、LLM 配置回环、混合时区排序），总计 66 项。

### 修复

- **"影响力数据暂不可用"高发**：Semantic Scholar 免 Key 共享池限流（HTTP 429）时此前直接降级为无数据；现在带 2 次指数退避重试，仍失败自动切换 OpenAlex 批量 DOI 查询兜底（引用数/venue 真实可用，高影响力引用数仅 S2 提供）。
- 顶部状态胶囊此前为纯展示元素（用户反馈"点不动"），现改为可交互按钮并接入真实动作。

## [0.3.0] - 2026-10-24

### 新增

- **桌面检索客户端**（`arxiv-digest-desktop`，pywebview 可选依赖）：输入关键词或研究方向描述，选分类/数量/时间范围交互式检索 arXiv；结果含规则相关度、可选 LLM 精排分与学术影响力。
- **学术影响力层**（`impact.py`）：Semantic Scholar 批量接口查询总引用数、高影响力引用数与正式发表 venue；影响力分为引用量对数综合分（0-10），接口失败优雅降级为"—"。arXiv 预印本无期刊影响因子，只用可溯源的真实引用数据。
- **检索层**（`search.py`）：多关键词 AND 精确检索（支持引号短语）、`(cat:…) AND (all:…)` 分组查询、`sortBy=relevance`、时间窗口过滤、limit 夹取 1~300。
- 前端（`web/index.html`）：高级简约风格，骨架屏加载、结果错落入场与指标条生长动效、详情毛玻璃弹窗、列排序、CSV/Markdown 导出、BibTeX 一键复制、Toast 提示。
- 测试 +11 项（检索构造/日期过滤、影响力解析/评分/降级、桌面桥接组装与错误路径），总计 42 项。

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

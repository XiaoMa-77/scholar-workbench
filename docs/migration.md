# 合并迁移记录

目标仓库：scholar-workbench（由 lit-review-agent 重命名）。原 arxiv-digest-agent 的末次导入提交为 `1563f569bcce15729926210c160f8263d8120e00`。

| 原内容 | 合并后位置 / 行为 |
| --- | --- |
| 全部 `src/arxiv_digest/` 模块 | 同路径保留，补上共用配置与综述衔接 |
| 全部 digest 测试与 Atom fixture | `tests/digest/` |
| YAML 配置示例 | `config.example.yaml` |
| 历史日报与 example | `reports/` |
| 桌面 / 日报 / 流程截图 | `docs/digest/` |
| 原 CHANGELOG | `docs/history/arxiv-digest-changelog.md` |
| 原 CLI / desktop / module 入口 | 继续可用，另增加统一 litreview 子命令 |
| 原每日 Actions | 删除 cron，迁为仅手动触发的 `digest.yml` |
| 原 LLM 本地配置 | 自动兼容读取，统一写入 `~/.litreview/config.json` |
| 两仓库 Git 历史 | 合并提交保留双方父提交，不做 squash |

新增的 `litreview.discovery` 将共用检索结果转换为综述模型，保持完整作者、引用数、DOI 与 PDF 链接。CLI 与 MCP 默认使用该层；桌面综述直接复用本次检索结果。

离线模式改为读取检索快照，避免离线运行再次请求搜索 API。MCP 服务使用 SDK 1.x 的 FastMCP 工具注册方式，并验证工具注册与调用。

删除原仓库的前置条件：完整功能迁移、合并测试通过、目标 main 分支验证完成、完整 Git bundle 验证可恢复。仓库级的 stars、访问统计与 Actions 运行记录不属于 Git 提交历史。

## 项目命名统一

仓库与安装分发名称统一为 `scholar-workbench`，桌面标题使用 **Scholar Workbench**。新增 `scholar-workbench`、`scholar-workbench-desktop` 与 `scholar-workbench-mcp` 入口；原命令、Python 模块、MCP 工具名及 `~/.litreview/` 配置和缓存路径继续兼容。

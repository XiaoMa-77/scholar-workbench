# 合并版本验证记录

验证日期：2026-10-29。环境：Windows、Python 3.12。

| 检查 | 结果 |
| --- | --- |
| 原 digest 与 litreview 测试 + 合并集成测试 | 115 项通过 |
| 两个包合计语句覆盖率 | 89% |
| Ruff 源码检查 | 通过 |
| Python compileall | 通过 |
| sdist 与 wheel 构建 | 通过 |
| wheel 包含桌面 HTML 与全部 Python 模块 | 通过 |
| sdist 包含迁入测试与 fixture | 通过 |
| CLI 各子命令与旧入口冒烟 | 通过 |
| MCP 真实 stdio 初始化与工具列表 | 通过 |
| MCP 搜索与综述工具调用 | 固定输入测试通过 |
| 桌面 HTML → Python 桥接 → 综述下载 | Edge 无界面自动化通过，JS 错误 0 |
| README 本地链接与迁移文件清单 | 通过 |
| arXiv / OpenAlex 合并检索在线检查 | 返回 2 篇 arXiv 论文 |
| OpenAlex 独立在线检查 | 当前环境返回 HTTP 429；退避与多源回退另有固定响应测试 |
| 原 digest Git bundle | 完整历史，可独立恢复 |

桌面自动化使用固定论文响应、实际 Python 桥接与元数据综述流水线，下载结果为真实生成的 Markdown；PDF 提取使用合成 PDF 在单元测试中验证。原生 pywebview 窗口未作为自动化图形后端启动。未使用真实 LLM Key 发起付费请求；LLM 精排、解析、配置共用和降级使用测试响应验证。

GitHub CI 在 Python 3.11 / 3.12 / 3.13 上复核离线测试、源码检查、CLI 入口、MCP 导入与分发包构建。

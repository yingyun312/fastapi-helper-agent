# 验证记录

日期：2026-10-24（Asia/Kuala_Lumpur）。本项目由 AI 在现有目录完成，未提交或推送 Git。

| 检查 | 实际结果 | 范围 |
|---|---|---|
| `python -m pytest -q` | **48 passed** | 算法、持久化、SDK 替身、工具、会话、SSE、取消及总超时、评估分母、正文摘录 |
| `ruff check app scripts ui tests eval` | 通过 | 新增 Python 代码静态检查 |
| `python -m compileall -q app scripts ui eval` | 通过 | 语法编译 |
| `python -m pip check` | No broken requirements found | 本次安装依赖一致性 |
| `git diff --check` | 通过 | 已跟踪文件改动的空白检查 |
| 官方下载 | 24 篇，固定 SHA，MIT 许可 | 真实 GitHub 网络数据，含代码示例展开 |
| 演示入库 | 413 个块 | 真实 Chroma + 手写 BM25；Embedding 为哈希替身 |
| 实际 HTTP/SSE | meta / step / sources / token / done，完整文本一致 | 本机运行 Uvicorn，演示模式 |
| Streamlit | 健康检查 200；浏览器完成问答 | 来源和执行记录可展开，显示模式与耗时 |
| GitHub 搜索 | 返回两个真实公开 PR，未限流 | 无 Token、只读；不读取 .env |
| DeepSeek 对话 | **真实调用待验证** | 当前只验证真实 SDK + 确定性 HTTP 替身 |
| 生产 Embedding | **真实调用待验证** | 批处理、顺序及形状用替身验证；需本机 Key |

固定文档版本：FastAPI 0.115.6 / `bb8c2a64981d3e806575a445115f29eddf014c77`。
运行索引版本：`4af2ba8f91ef1d89e21f169764cd62664162df9ca12b43833a0fb14a7b7e0d73`。

无密钥真实搜索检查于 20:38 左右返回 [PR 16368](https://github.com/fastapi/fastapi/pull/16368) 和 [PR 13264](https://github.com/fastapi/fastapi/pull/13264)。这仅确认接口可用，不确认这些 PR 能回答任一评估题。

## 评估记录

最终实现对应的探索报告：`eval/results/20261024T133513Z-77437c/report.json`，配套 `human_review.csv`。包含配置、题集哈希、实现哈希及逐题结果。之前的调试报告全部保留。

- 35 个文档题 × 3 个检索模式完成，失败及降级均为 0。
- 50 个问题完成离线回答流程；5 个社区题会返回演示模式不联网的工具错误，随后拒答。
- 离线无答案题仅 7/10 被拒答，文档题有 3/35 被拒答。剩余错误没有隐去。
- 所有标签仍待人工复核。演示系统只摘录原文，缺少语义判断；其召回与拒答数值不能代表真实模型质量，更不能宣称幻觉率为零。
- 未执行真实 Embedding 三组效果对比、真实 DeepSeek 全量问答，也未完成任何人工答案标注。

## 可复现命令

```bash
source .venv/bin/activate
python -m pytest -q
ruff check app scripts ui tests eval
python -m scripts.ingest --mode demo
python -m eval.run_eval --mode demo --include-unreviewed --answers
```

两个服务按 README 启动后运行 `python -m scripts.smoke_http`，验证实际 HTTP 与 SSE。`python -m scripts.check_github` 另需联网，但无需密钥。SDK / 工具测试使用确定性替身，不进行任何付费调用。

## 界面记录

`demo.png` 为本机浏览器中的实际运行截图，回答标明离线摘录模式。

## 未纳入本次范围

原计划的部署、Redis、Discussions、重排模型是后续加分项。没有录制视频、发布网站、推送 GitHub 或更改仓库公开状态。会话只存在单进程内存；引用检验是形式和原文核验，不是语义蕴含证明。

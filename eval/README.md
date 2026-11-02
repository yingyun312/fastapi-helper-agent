# 评估说明

`questions.jsonl` 中的 50 题是 AI 起草的候选集，不是已确认的基准集。当前所有标签都是 `pending_human_review`。

## 先审核标签

逐条打开 `expected_sources` 对应的本地文档，确认固定版本确实回答该问题；必要时修改问题、补全所有相关来源或移到无答案类。记录审核人 `reviewer`、ISO 日期 `reviewed_at`，最后改为 `human_verified`。不要只改状态字段而未读原文。多个来源都被标为相关时，Recall 分母是这些来源的集合大小。

35 道 `docs` 题参加离线检索；5 道 `community` 题考查动态搜索，不能写死“应该命中某个 Issue”；10 道 `no_answer` 题考查缺少证据时能否拒答。无答案题包含私有信息、不可预测信息与不存在的 API，需要人工确认拒答是否合适。

## 指标口径

- Recall@5：前五个检索块包含的相关来源页数 / 标注相关来源页数。同页多个块占多个排名，不重复计召回。
- MRR@20：前二十个块中，第一个相关来源所在排名的倒数；未找到为零。
- 失败查询记零并另外报告 `failed`，混合检索降级额外报告 `degraded`。
- 无答案拒答率分母只含 `no_answer` 题；文档拒答率用于观察误拒。请求失败单独记录，不冒充正确拒答。
- 重复调用耗时固定问题、上下文和会话，只有 `repeat_cache_hit=true` 才表示命中；GitHub/失败/拒答不缓存。
- 演示哈希向量不是语义模型，数值不与生产 Embedding 效果混用。

不带 `--include-unreviewed` 默认只评估人工确认题；当前为零题是预期结果。`--include-unreviewed` 会在报告标注 `provisional_ai_labels`。新报告同时记录非密钥配置、语料与索引版本、题集哈希和实现哈希。最初两轮探索报告早于这个记录功能，不能作为完整复现实验。

## 人工检查回答依据

运行 `--answers` 后打开 `human_review.csv`，查看每条回答、引用和对应原文，把 `human_grounding` 从 `pending` 改为 `supported` / `unsupported` / `partially_supported` / `abstention_appropriate` / `abstention_inappropriate`，在 `human_notes` 写出具体不受支持的句子或误拒原因。

真实引用并不等于正确解释；尤其检查版本、默认值、否定词、错误处理和 Issue 状态。若计算幻觉率，先约定分母（例如所有非拒答回答）和如何计部分错误，记录复核人及日期，再统计；脚本不会擅自把机械引用校验当成“零幻觉”。

## 已保存报告

- `20261024T123528Z-ce8af0`：首次离线探索，暴露摘录段落与引用 URL 的校验问题。
- `20261024T123806Z-7ee61c`：修正摘录选择并加入离线词汇覆盖门槛后的探索。
- 后续时间戳目录：以各报告 `created_at`、`implementation_sha256` 和 `configuration` 为准。

旧报告保留，不能从中选择最漂亮的数字宣称泛化提升。仍有无答案题被离线摘录模式错误接受，这正说明确定性演示缺少语义判断。真实服务效果、标签审核及人工回答复核尚未完成。

# #7 工程回归评分

在仓库根目录运行。命令离线执行，输出一个 JSON 对象，以 `baseline_reports` 保留三种基线报告，以 `ncsc_report` 返回正式 NCSC 的同口径结果。

```sh
python3 -m baselines.evaluate datasets/synthetic-v0/items.json
python3 -m unittest discover -s tests -p test_baseline_evaluation.py -v
```

正式 NCSC 从查询数据同目录的 `registry.json` 读取概念，每个条目独立建立 IR 0.2 知识库，按查询的上下文与日期取证。各系统独立生成 `item_id`、`query_id`、`status`、`evidence`。评分器按条目和查询 ID 对齐预测。重复、缺失、多余的预测或非法状态都会使评分失败。

| 字段 | 计算方式 |
| --- | --- |
| `confusion` | 四行四列，行是金标，列是预测；`correct` 为对角线之和。 |
| `unknown_gold_predicted_known` | 金标为未知却给出支持、反对或冲突的查询数。 |
| `unknown_as_refuted` | 金标未知却预测反对的数量（count），全部金标未知的查询数（eligible），以及两者之比（rate）。分母为零返回 null。 |
| `known_gold_predicted_unknown` | 金标有明确状态却返回未知的查询数。 |
| `leaves` | 每个查询分别把证据展开为本条目、同上下文、同日期的原始断言 ID 集合。计数跨查询累加，集合交集计入命中。 |
| `rule_paths` | 每条由推导根通向叶子的路径记录规则名、有序前提位置及末端原始断言 ID。直接证据只贡献叶子。每查询去重，规则或位置的差异单独反映在路径分数中。 |
| `invalid_predicted_evidence` | 不能完整展开、分区不符、引用顺序不符、叶子极性不符或有回边的预测根数。该根所有叶子和路径均无命中，其他完整根仍参与计数。精确率的分母仅为可解析集合，须结合此诊断解释。 |
| `provenance_complete` | 分母为金标含证据的查询数。预测的叶子与路径集合均与金标相等，且无无效根时计为完整。缺证据的未知查询不扩大分母。 |

`leaves` 和 `rule_paths` 分别报告金标、预测、命中总数，以及微平均精确率和召回率。分母为零时输出 `null`。此版只评价决定查询状态的正反证据，被抑制推导另由契约和数据回归核验。路径集合衡量逐叶规则链；完整证明树之间的组合差异尚未单独评分。

金标的单跳推导用 `derived_by` 和有序的原始断言 ID 列表表示。工程测试允许将一个前提写成嵌套的同形规则对象，以描述两跳路径；中间证明不需要永久 ID。若预测提供 `trace`，每个子节点必须对应同位置的前提 ID。禁止用一个缺少子树的派生 ID 充当原始叶子。

本命令用于未冻结的合成种子集。当前未划训练及盲测集，证据分母、路径口径和实验阈值待人工试标与评审后冻结。

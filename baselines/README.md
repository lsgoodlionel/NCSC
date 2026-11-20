# JSON 精确匹配基线（#7）

在仓库根目录运行：

```sh
python3 -m baselines.json_exact datasets/synthetic-v0/items.json
python3 -m unittest discover -s tests -p test_json_baseline.py
```

输入为已通过数据一致性检查的 IR 0.2 种子集。每个查询独占一行 JSON，以 `item_id` 和 `query_id` 联合定位。仅检索本条目内主体、关系、客体、上下文和日期均匹配的原始断言；无日期分区单独匹配。保留每条证据的断言 ID 和极性，按 ID 排序。出现两种极性为冲突，只有正证据为支持，只有负证据为反对，无证据为未知。该基线直接扫描 JSON，不运行推导规则，回答时无需读取期望答案。

当前结果用于工程回归。数据尚待人工试标，实验阈值及评分口径待冻结。

## 轻量 KG 基线

```sh
python3 -m baselines.kg datasets/synthetic-v0/items.json
python3 -m unittest discover -s tests -p test_kg_baseline.py
```

KG 为每条目建立按上下文和日期分区的三元组索引。查询将主体、关系、客体全部绑定，返回匹配的全部平行边。返回格式与 JSON 基线一致，可以逐行比较状态和证据；该基线仅评估直接检索。

## 独立 R1 规则基线

从仓库根目录执行以下命令，每个查询输出一行 JSON。

```sh
python3 -m baselines.rule_engine datasets/synthetic-v0/items.json
python3 -m unittest discover -s tests -p test_rule_baseline.py
```

基线对通过一致性检查的 IR 0.2 合成条目逐项建表，限定相同上下文、相同日期（含无日期）的原始断言，只启用单跳 R1。任务明确需要某资源且该资源明确不可用时，推导任务阻塞。任一前提有反证时，该组推导被抑制；其他独立、无争议的资源仍可产生支持证据。报告因果只可作为直接查询结果。当前没有多跳、规则文件加载或 IR 0.3 区间求值。

每行包含 `item_id`、`query_id`、`status` 和 `evidence`。直接证据以原始断言 ID 升序排列；推导证据随后按前提 ID 二元组排序，`derived_by` 给出单步规则路径，`premises` 依次列出需求断言与不可用断言的原始 ID。不同叶子组合分别保留。基线只导入共享的角色字段名与四值映射，独立实现连接与前提检查，运行时无需 NCSC 内核或金标。

# 独立人工试标流程

关联 #6 验收项：“记录独立人工试标和分歧”。

**本流程需要两名人工标注者执行。到目前为止尚未进行任何试标，仓库中不含任何一致性数值。** 结果产生后写入 `annotation/trials/`，见该目录的 README。

## 1. 角色

| 角色 | 人数 | 要求 |
|---|---|---|
| 标注者 A、B | 2 | 读过 `annotation/GUIDE.md`；**不看**金标断言和期望答案；两人之间不交流 |
| 裁决者 | 1 | 不是 A、B 本人；可以是金标作者 |

## 2. 材料

- 输入：每个条目只提供 `id` 和 `text`，以及登记表 `registry.json`。
- 生成方法（不含金标）：

  ```bash
  python -c "import json;d=json.load(open('datasets/synthetic-v0/items.json',encoding='utf-8'));print(json.dumps([{'id':i['id'],'text':i['text']} for i in d['items']],ensure_ascii=False,indent=2))" > trial-packet.json
  ```

- 输出：每位标注者为每个条目提交 `assertions` 与 `not_annotated`，格式同 `items.json`。

## 3. 指标（先冻结，后测量）

以下定义在第一轮试标开始前冻结。冻结之后若要修改，必须开新一轮，旧结果保留。

| 指标 | 定义 |
|---|---|
| 断言集合一致率 | 把每条断言归一为 `(subject, relation, object, polarity, context, valid_at)`，忽略 ID 与来源说明；计算 A、B 两个集合之间的 micro-F1 |
| 极性 κ | 两人都标注了的同一三元组（同分区）上，极性的 Cohen's κ |
| 不标注一致率 | `not_annotated` 中 `(span, reason)` 的集合 F1 |
| 报告因果误升级数 | 任一标注者把报告因果标成了被报告的事实本身（如由“原因是密钥”标出“密钥不可用”）的次数。目标为 0，非零即触发指南修订 |
| 与金标的一致率 | A、B 分别与金标做同样的断言集合比较，用于发现金标自身的错误 |

数据量小时 κ 很不稳定，报告时必须同时给出样本数和原始混淆表，不能只报 κ 值。

## 4. 步骤

1. **准备**：冻结指南版本号与指标定义，记录在本轮的 `round.json`。
2. **独立标注**：A、B 各自完成，提交到 `annotation/trials/<轮次>/annotator-a.json`、`annotator-b.json`。
3. **计算**：按第 3 节计算指标，写入 `metrics.json`，附计算脚本的版本。
4. **分歧记录**：逐条列出不一致之处，写入 `disagreements.jsonl`（格式见 `trials/README.md`），每条都标出分歧类别。
5. **裁决**：裁决者逐条给出结论：哪方正确、金标是否需要改、指南是否需要改。
6. **修订**：
   - 指南需要改：更新 `GUIDE.md`，在其“变更记录”中引用本轮编号；
   - 金标需要改：在数据集 PR 中修改，并在说明中引用分歧编号；
   - **不得为了提高一致率而删除有分歧的条目**。

## 5. 分歧类别

| 代码 | 含义 |
|---|---|
| `concept` | 选了不同的概念或关系 |
| `polarity` | 正反向不同，或一方把缺失标成了否定 |
| `scope-context` | 上下文不同 |
| `scope-time` | 日期或日期作用范围不同 |
| `cause` | 报告因果与事实陈述的区分不同 |
| `modality` | 一方标注了可能、计划类陈述 |
| `omission` | 一方标注、另一方未标注（且未写入 `not_annotated`） |
| `guide-gap` | 指南没有覆盖的情况 |

## 6. 何时可以冻结数据集

数据集冻结前，至少完成一轮试标，并满足：所有 `guide-gap` 类分歧都已修订指南，所有判定为金标错误的条目都已修正。冻结流程见 `datasets/README.md`。

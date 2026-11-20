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

## 声明式前向规则基线

```sh
python3 -m baselines.rule_engine datasets/synthetic-v0/items.json
python3 -m baselines.rule_engine datasets/synthetic-v0/items.json --rule tests/contract/fixtures/rules-0.2/valid/r1-resource-unavailable.json
python3 -m unittest discover -s tests -p test_rule_baseline.py
```

默认规则 R1 将“任务需要资源”和“资源不可用”连接为“任务阻塞”。可重复使用 `--rule` 提供完整替换规则集，也可通过 `predictions(dataset, rules)` 传入规则对象列表。接受 `ncsc-rules/0.2` 的固定关系、常量和主体/客体变量，支持 1–4 个正向或显式负向前提、已绑定变量的正向结论。只有 active 规则参与计算。负向前提引用的关系必须只来自原始断言，前提存在反证时抑制该组匹配。报告因果仅能作为直接断言查询。

基线在每个条目、上下文、日期（含无日期分区）内建立独立的 SQLite 内存表，把前提编译成自连接，把反证检查编译成反连接。逐轮插入以前没有的四元事实，直至该分区没有新事实。查询解释随后从匹配好的规则应用回溯至原始叶子；同一条根到叶路径内重复事实的分支被剪去。循环可传播已有种子，无种子循环无法产生事实。该实现面向小型 IR 0.2 对照实验，仅依赖 Python 标准库，不使用 NCSC 的规则加载、闭包或证明实现。解释枚举的运行成本会随独立证明组合增加，规模上限尚未实测。

每行包含 `item_id`、`query_id`、`status` 和 `evidence`。直接证据按原始断言 ID 升序排列；推导证据按规则、前提 ID 排序。单跳推导的 `premises` 保留规则前提顺序。多跳推导另附 `trace`，子证明引用与相同位置的前提一一对应，沿途可取得各步规则与叶子。可重算的 `b:` 引用只在基线解释内使用。评分时使用原始叶子和规则路径。

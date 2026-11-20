# 工程架构

## V0.1：Python 模块化单体

```text
文本/结构输入
  -> parser adapters（可选模型；不可信候选）
  -> candidate IR -> normalizer -> validator -> immutable assertion store
                         |              |                 |
                      registry   deterministic rules   query/index
                         +----------- audit/provenance --+
```

- `registry`：概念/关系/规则身份、别名、版本、合并拆分；不做向量相似。
- `ir`：版本化对象、规范序列化、哈希；不调用模型。
- `validation`：Schema、类型、角色、基数、引用完整性、时间一致性。
- `reasoning`：纯函数规则、四值结果、推导轨迹；不写正式知识。
- `store`：仓储接口；SQLite 起步，图投影只是索引而非真相源。
- `parser`：人工、规则、模型均输出候选 IR，必须通过验证。
- `adapters`：统一模型协议；核心不感知提供商。
- `evaluation`：冻结清单、划分、指标、基线、消融和错误分类。

## 信任边界

| 边界 | 输出 | 禁止 |
|---|---|---|
| 模型适配器 | 候选 IR、原始响应、模型元数据 | 直接成为已验证事实 |
| 确定性核心 | 验证报告、查询、带轨迹推论 | 猜测缺失语义 |
| 存储 | 不可变版本、索引、审计 | 覆盖历史、静默合并 |
| 权限/执行 | 已批准动作的收据 | 把“计划”当授权；V0.1 不做外部执行 |

## ID 与迁移

主键使用不含语义的 128 位不透明 ID（可用 UUIDv4；格式见 [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html)）。类型不得编码进可变十进制段；名称/定义/上位关系属于版本记录；ID 永不复用。

合并时旧 ID 保留为 `deprecated` 并 `redirects_to` 新 ID，历史断言不重写。拆分时旧 ID 指向多个 `superseded_by`，旧断言必须重判，不能自动任选。所有同一性决策带证据且可撤销。

## 身份、数值、结构、向量、Token

| 表示 | 合法运算 |
|---|---|
| 身份 ID | 相等、引用、迁移；禁止大小/距离 |
| 数值/量 | 在单位约束下算术/比较 |
| 结构 IR | 验证、匹配、查询、规则 |
| 向量 | 指定模型/版本下近邻；不能决定身份 |
| 模型 Token | 模型内部序列；不能作长期 ID |

## 逻辑与原生接口

V0.1 默认开放世界、显式否定、有限单调规则；结果至少为 `supported/refuted/both/undetermined`。每条规则有适用域、版本和轨迹。默认逻辑、概率逻辑、SCM 分别留实验接口，不混入核心。

原生研究只读导出 `GraphBatch(nodes, edges, roles, masks, targets, schema_version)`；不透明 ID 在训练快照内映射到索引，模型/向量不得回写注册表。

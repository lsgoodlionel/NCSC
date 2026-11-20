# 语义 Schema 提案

状态：`draft-0.1`，可替换，不是核心公理。

顶层对象：`ConceptVersion, Lexeme, IdentityDecision, RelationType, EntityRef, Event, Proposition, Argument, Quantity, TemporalExtent, Evidence, Source, Assertion, Rule, Derivation`。

共有字段：`id`（不透明）、`schema_version`、`record_version`、`status`、`created_at`、`created_by`。内容变化新增版本，不覆盖。

```yaml
Assertion:
  id: assertion:uuid
  proposition: Proposition
  polarity: positive | negative
  epistemic_status: reported | supported | verified | inferred | disputed | refuted | expired
  confidence: {value: 0.0..1.0, method: string, calibration_set: optional-id}
  valid_time: TemporalExtent | null
  transaction_time: {recorded_at, superseded_at?}
  context: [ContextRef]
  evidence: [EvidenceRef]
  provenance: ProvenanceRef
  scope: {quantifier?, jurisdiction?, population?, measurement_basis?}
```

`null` 仅表示字段未给；未知用 `UnknownValue(reason, queried_at)`；空集合用 `[]`；不适用用 `NotApplicable(reason)`；遮蔽用 `Redacted(policy_ref)`。

## IR 示例

“企业因为资金不足，所以暂时停止软件开发。”

```json
{
  "schema_version": "ncsc-ir/0.1",
  "assertions": [
    {"id":"a1","predicate":"has_funding_status","args":{"holder":"enterprise-1","value":"insufficient"},"epistemic_status":"reported","evidence":["span-1"]},
    {"id":"a2","predicate":"pause","args":{"agent":"enterprise-1","theme":"software-development-1"},"aspect":{"temporary":true},"epistemic_status":"reported","evidence":["span-2"]},
    {"id":"a3","predicate":"reported_cause","args":{"cause":"a1","effect":"a2"},"epistemic_status":"reported","evidence":["connector-because"]}
  ]
}
```

没有 `validated_causal_claim`。验证因果必须另含因果问题、变量、假设、数据/实验设计、识别方法、估计与不确定性。SCM 的干预和反事实结论依赖数据与假设（Pearl, [Causal Inference](https://proceedings.mlr.press/v6/pearl10a.html)）。

关系定义含允许角色、domain/range 约束、方向、对称/传递性（默认 false）、时间敏感性、基数和版本。中文省略成分可 `unfilled`，不得伪造实体。

Schema 升级提供纯函数 `upgrade(vN)->vN+1`、迁移报告及不可逆字段清单。概念合并/拆分是注册表迁移，不等于 Schema 迁移。

V0.1 用规范 JSON 便于测试，可选 JSON-LD 上下文互操作；二进制格式只在测得瓶颈后引入。交换格式不等于推理语义。

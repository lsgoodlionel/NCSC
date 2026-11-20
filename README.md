# NCSC 原型：数字—汉语原生语义认知架构

这是一个离线、确定性的最小纵切片，验证稳定概念编号、中文别名、显式关系角色、正负断言、来源、上下文/时间隔离、四值查询与白名单规则溯源。它不依赖 LLM、网络或 API 密钥。

“0–9 十类”目前只是待验证研究标签，不是本原型的公理，也不参与推理。

## 快速运行

```bash
python3 -m ncsc.cli validate examples/project_state.json
python3 -m ncsc.cli query examples/project_state.json \
  --subject c:task:release --relation r:status:blocked --object c:value:true \
  --context ctx:project-alpha --valid-at 2026-11-19
python3 -m unittest discover -s tests -v
```

查询状态只有四种：

- `支持`：存在正向证据，没有反向证据；
- `反对`：存在反向证据，没有正向证据；
- `冲突`：同一上下文、同一时间分区内正反证据并存；
- `未知`：没有可用证据。缺失绝不当成否定。

## IR 契约

输入是 JSON 对象，顶层仅允许 `version`、`concepts`、`assertions`。概念 ID 与中文词面分离；断言的 `subject/relation/object` 都必须引用已声明 ID。每条断言必须有：

- 稳定 `id`；
- `roles`（当前固定为 `subject/relation/object`）；
- `polarity`（`positive` 或 `negative`）；
- 非空 `sources`，每项含来源 ID 与中文说明；
- 明确 `context`；
- 可选 `valid_at`，格式为 `YYYY-MM-DD`。

未知字段、悬空引用、重复 ID、空来源、未支持角色或时间结构会被拒绝。查询必须明确上下文；数据中使用时间时，查询也必须给出完全相同的日期。不同上下文或日期的证据不会合并成冲突。

## 当前白名单规则

`resource_unavailable_blocks_task`：同一证据分区中，若任务 `需要资源` 某资源，且该资源被正向断言为 `不可用=true`，则推导任务 `阻塞=true`。推导结果列出规则名和两条前提 ID。规则只做精确 ID 匹配，不做词面猜测。

`报告原因为` 只表示“某来源报告了因果说法”；内核不会把它提升为已验证因果，也不会据此推导。

## 边界与后续

当前仅支持单日精确时间分区，不支持区间、时区、上下文继承、概率、自然语言解析、开放世界规则学习或跨分区推理；遇到这些结构会拒绝或返回未知。案例是少量真实结构的合成数据，不是生产事实。

完整的分阶段开发方案、已确认缺陷清单与 IR 0.2 提案草案见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。

后续工作包括：迁移研究材料、模型适配、人工标注规范、JSON/KG/规则基线对比，以及性能、规模、可靠性和非功能实测。当前不宣称任何未经测量的指标。

NCSC V0.1 的第一轮完整工程研究方案已纳入 [docs/v0.1/README.md](docs/v0.1/README.md)，包括工程可行性、架构、语义 Schema、实施计划、风险和研究问题。该研究包仍是启动决策材料，不代表核心公理已经冻结。

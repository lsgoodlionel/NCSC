# IR 0.2 契约提案

关联 Issue #3。P-1/2/3/5/7 已由 Codex 复核同意；P-4 评审记录待填，P-6 见 #19。自 2026-11-20 起本目录由 Codex 主责，见 [../HANDOFF.md](../HANDOFF.md)。
本目录取代 `docs/DEVELOPMENT_PLAN.md` §5 中 P-1～P-5、P-7 的初稿；P-6（时间区间）另行提出。

## 决策一览

| 提案 | 决策 | 破坏性 | 结构层 / 内核层 | 判例 |
|---|---|---|---|---|
| [P-1](P-1-kind-and-roles.md) 概念类别与角色 | `kind` 改为 6 值枚举；`relation` 位只接受关系类型；十类不进入 IR | 是 | 结构层 | `fixtures/0.2/structural/kind-*`、`relation-*`、`subject-is-relation` |
| [P-2](P-2-identifiers.md) 标识符 | 前缀表示记录类型，前缀后不透明；生产用不透明 ID；推导 ID 改为哈希 | 是 | 结构层 | `fixtures/0.2/structural/id-*`、`valid/opaque-ids` |
| [P-3](P-3-premise-conflict.md) 前提冲突 | 方案 A：前提在本分区非“支持”即不推出，记入 `suppressed` | 语义变化 | 内核层 | `cases/d1-*.json` |
| [P-4](P-4-rule-format.md) 规则格式与求值 | 每条规则一个 JSON 文件；结论只能正向；前提可正可负；报告因果不可作前提或结论；分层不动点求值；证据按 ID 排序 | 新增（0.2 输出顺序变化） | 结构层 + 内核层 | `fixtures/rules-0.2/*` |
| [P-5](P-5-query-trace.md) 查询溯源与原因 | 增加 `status_code`、`trace`、`reason`、`suppressed`、`other_partitions`；未声明 ID 报错 | D4 部分破坏，其余为增量 | 输出 Schema + 内核层 | `cases/d1-control-no-conflict.json` |
| [P-7](P-7-aliases.md) 别名 | 概念内唯一、去首尾空白、至少一个含汉字；**跨概念同名允许** | 是 | 结构层 | `fixtures/0.2/*/alias-*`、`valid/polysemy` |

迁移清单（破坏性变化、身份迁移、人工确认项）见 [MIGRATION-0.1-to-0.2.md](MIGRATION-0.1-to-0.2.md)。

## 与 `docs/v0.1/` 研究包的统一

`docs/v0.1/` 与 `docs/DEVELOPMENT_PLAN.md` 有四处分歧，本轮处理如下：

| 议题 | DEVELOPMENT_PLAN 初稿 | docs/v0.1 | 本提案 |
|---|---|---|---|
| ID | 可读正则（`c:task:release`） | 128 位不透明 ID，类型不编码进 ID | 采纳 v0.1 原则：前缀只表示**记录类型**（概念/关系类型/断言/来源/上下文），前缀后对内核不透明；生产数据用不透明值。可读值仅限夹具与示例，且同样不得被解析（P-2） |
| 类别 | 受控 `kind` 枚举 | 多轴（ontological_kind、role、value_kind…），十类降为 `coarse_tags` | 0.2 只落地一根轴：`kind` ≈ ontological_kind；角色由边表达；其余轴待有用例再加。十类不进入 IR，只在标注数据（#6）中作为可证伪的实验标签（P-1） |
| 状态词 | 支持/反对/冲突/未知 | supported/refuted/both/undetermined | 中文 `status` 保持不变（共享契约），新增一一对应的 `status_code`（P-5） |
| 运行时 | 仅标准库 | Python 3.12 + Pydantic + SQLite | 维持 `pyproject` 的 Python ≥3.9 与零运行时依赖，直到出现确需新版本或第三方库的功能；`sqlite3` 属标准库，不冲突。此项不改契约，只记录 |

另外，初稿把 D6（别名跨概念重名）当作缺陷；结合 v0.1 “语言表达可多对一或多义”的原则，本提案改判为**合法的多义**，见 P-7。

## 评审方式

1. 复核者逐条在 PR 中给出“同意 / 修改 / 否决”。
2. 同意的条目由 #4（校验器）与 #5（规则与溯源）实现；实现时把 `tests/contract/manifest.json` 中对应夹具的 `kernel` 从 `unimplemented:*` 改为 `enforced`，判例中的 `p3-option-a` 同理。
3. 否决或修改的条目，先更新本目录与夹具，再进入实现。

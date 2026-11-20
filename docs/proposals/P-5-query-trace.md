# P-5 查询输出：溯源树、未知原因与未声明 ID

状态：提议 · 关联 D4、D8 · 输出增量 + D4 部分破坏

## 问题

- 推导证据只列前提 ID，审阅者需要回到原文档逐个查找前提的来源。
- “未知”无法区分：确实没有证据、只在别的分区有证据、规则因前提冲突被抑制（P-3）。
- 查询 ID 拼写错误（`c:task:relase`）返回“未知”，与“没有证据”无法区分（D4）。
- 推导证据的来源直接拼接，链式推导后会重复（D8）。

## 决策

输出形状由 `schema/query-result-0.2.draft.schema.json` 定义。相对 0.1：

| 字段 | 变化 | 说明 |
|---|---|---|
| `status` | 不变 | 支持 / 反对 / 冲突 / 未知 |
| `status_code` | 新增 | supported / refuted / both / undetermined，与 `status` 一一对应 |
| `query` | 不变 | |
| `evidence[].sources` | 修正 | 推导证据按 `source.id` 去重，保留首次出现顺序（D8） |
| `evidence[].assertion_id` | 修正 | 推导证据使用 P-2 的 `d:` ID |
| `evidence[].trace` | 新增 | 推导证据必须带；逐个前提展开其证据，可递归，叶子为原始断言 |
| `suppressed` | 新增 | P-3 被抑制的推导；总是出现，可为空数组 |
| `reason` | 新增 | 仅当“未知”时出现：`no_evidence` 或 `premise_conflict` |
| `other_partitions` | 新增 | 仅当“未知”时可出现：同一三元组在哪些其他分区有证据；只作提示，**不合并** |

未声明 ID（D4）：subject、relation、object 任一未在文档中声明时，查询**报错**（`undeclared_concept`，CLI 退出码 2），不返回四值。

## 理由

- `trace` 让每条推导证据自带完整审计链，满足“所有推导可追到规则和前提”的验收要求，而且不需要第二次查询。
- `reason` 与 `other_partitions` 针对风险表中“精确分区导致大量未知，用户误以为系统失效”一项：给出提示，但分区仍然严格隔离。
- D4 用报错而非新增 `reason`：拼写错误是调用方的输入错误，不是知识状态，不应进入四值。
- `status_code` 是增量字段：中文状态词属于共享契约，不改；英文代码对齐 `docs/v0.1` 的用语，便于基线与评测脚本使用。

## 被否决的备选

- **D4 返回 `未知` + `reason=undeclared`**：调用方容易忽略 `reason`，拼写错误被静默当作“没有证据”。
- **`other_partitions` 合并为弱证据**：违反分区隔离原则。

## 判例

`cases/d1-control-no-conflict.json`：

- `blocked`：推导证据带 `trace`、`d:` ID 与去重来源；
- `other-date`：查询 2026-11-20 得到未知，`reason=no_evidence`，`other_partitions` 指出 2026-11-19；
- `undeclared-id-d4`：0.1 现状返回未知（已验证），0.2 期望报错。

## 评审记录

（待 Codex 填写）

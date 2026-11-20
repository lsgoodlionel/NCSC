# P-2 标识符

状态：提议 · 关联 D5、D8 · 破坏性（IR 0.2）

## 问题

- 0.1 只要求 ID 是非空字符串：`" c:task:release"` 与 `"c:task:release"` 被视为两个概念（D5）。
- 推导 ID 是 `derived:{A}+{B}`，断言 ID 自身含 `+` 时可构造碰撞（D8）。
- `docs/v0.1` 要求 ID 不含语义、类型不编码进 ID，而 0.1 示例的 `c:task:release` 把“task”写进了 ID。

## 决策

1. **语法**：`<前缀>:<主体>`。

   | 前缀 | 记录类型 |
   |---|---|
   | `c` | 概念（kind ≠ relation） |
   | `r` | 关系类型（kind = relation） |
   | `a` | 断言 |
   | `src` | 来源 |
   | `ctx` | 上下文 |
   | `d` | 推导结论（仅出现在输出中，输入不得使用） |

   主体：`[0-9a-z]`，中间允许 `. _ : -`，首尾为字母或数字，总长不超过 128。只用小写、无空白。

2. **前缀表示记录类型，不表示本体类别**。`c`/`r` 的区分对应 v0.1 Schema 中 `ConceptVersion` 与 `RelationType` 两种不同的顶层记录，记录类型不会随重分类改变，因此不违反“类型不编码进 ID”。“task”“resource”这类本体类别**不得**作为生产 ID 的组成部分。

3. **主体不透明**。内核不得解析、切分、排序、比较主体内部结构，不得用数值差或前缀推出语义。生产数据应使用不透明值，推荐 UUIDv7 的 32 位小写十六进制（可按时间排序便于存储，但排序不承载语义）。可读主体（如 `c:task:release`）只允许出现在夹具与示例中，同样不得被解析。

4. **推导 ID**：`d:<rule_id>:<h>`，其中 `h` 是 `sha256(json([rule_id, premises]))` 的前 32 位十六进制；`json` 采用 UTF-8、无空格、`ensure_ascii=False`，`premises` 保持规则定义的顺序。不同前提组合不会碰撞，同一组合在任何机器上得到同一 ID。

5. **ID 永不复用**。删除、合并或拆分概念时，旧 ID 保留为废弃状态并指向新 ID（注册表能力，不在 0.2 IR 内，见迁移清单“身份迁移”）。

## 理由

- 用正则在结构层一次性消除空白、大小写、前缀错误这类 ID 歧义，各语言实现结论一致。
- 保留 `c:`/`r:` 两个前缀，使 P-1 的角色约束可以在结构层用前缀检查，而不必查表。
- 推导 ID 用哈希而非拼接，长度固定，且与断言 ID 的字符集无关。

## 被否决的备选

- **纯 UUID、无前缀**：最符合“不透明”，但角色约束只能在内核查表；人工审阅夹具时也无法一眼识别记录类型。
- **完全保留 0.1 可读 ID 规则**：类别进入 ID，重分类后 ID 与语义不符，违背 v0.1 的身份原则。

## 判例

| 夹具 | 期望 |
|---|---|
| `0.2/structural/id-whitespace` | 拒绝（D5） |
| `0.2/structural/id-uppercase` | 拒绝 |
| `0.2/structural/id-wrong-prefix` | 拒绝 `assertion:` |
| `0.2/structural/context-free-text` | 拒绝自由文本上下文 |
| `0.2/valid/opaque-ids` | 接受生产风格的不透明 ID |
| `cases/d1-control-no-conflict.json` → `p3-option-a` | 推导 ID 形如 `d:resource_unavailable_blocks_task:<32hex>` |

## 待定

- 上下文 ID 是否需要像概念一样先声明（上下文注册表）。0.2 暂不要求声明，只约束语法。

## 正则方言说明

Python 正则（`jsonschema` 使用 `re.search`）的 `$` 会匹配“字符串末尾，或末尾换行之前”，ECMA-262 的 `$` 不会。因此 `"c:task:release\n"` 曾能通过 Python 下的结构层。现在所有 ID 额外引用 `singleLine` 约束（禁止任何换行类字符），使两种方言的结论一致；内核侧用 `re.fullmatch`，本来就没有这个问题。判例：`0.2/structural/id-trailing-newline`。

## 评审记录

- 2026-11-20 Codex（#13 复核）：**同意**输入 ID 主体 1–128 位，以及按前提顺序计算推导 ID。指出 `$` 与末尾换行的方言差异。
- 2026-11-20 Claude：已修复，见上节“正则方言说明”。

# IR 契约 Schema

| 文件 | 状态 | 用途 |
|---|---|---|
| `ir-0.1.schema.json` | 现行 | IR 0.1 的结构层，忠实描述当前内核 |
| `ir-0.2.draft.schema.json` | 草案，待 #3 评审 | P-1 / P-2 / P-7 的结构层约束 |
| `rules-0.2.draft.schema.json` | 草案，待 P-4 评审 | 规则文件的结构层 |
| `query-result-0.2.draft.schema.json` | 草案，待 #3 评审 | P-3 / P-5 的查询输出形状 |

## 两层校验的分工

**结构层（JSON Schema）** 只回答“这份 JSON 的形状对不对”：字段集合封闭、类型、枚举、ID 语法、日期格式、别名格式。它可以被任何语言的 Schema 实现复用，不依赖 Python。

**内核层（Python）** 回答需要看整份文档或需要语义的问题：

| 检查 | 为什么不放进 Schema |
|---|---|
| 概念 ID、断言 ID 全局唯一 | 跨数组元素比较 |
| 角色引用的概念已声明 | 跨数组引用 |
| 同一断言内来源 ID 不重复（0.2） | `uniqueItems` 比较整个对象，不能只比 `id` |
| 日历有效性（如 `2026-02-30`） | 正则无法表达 |
| 分区隔离、四值判定、规则推导、冲突抑制 | 运行时语义 |

### 正则方言

Schema 的 `pattern` 要在 ECMA-262 与 Python `re` 下给出相同结论。已知差异：Python 的 `$` 会匹配“末尾换行之前”，`.` 会匹配 U+2028 等行分隔符。为此，所有 ID、日期和 0.2 文本字段都额外引用 `$defs/singleLine`，禁止任何换行类字符（与 Python `str.splitlines` 的行边界一致）。新增带 `$` 或 `.` 的模式时，必须同时引用 `singleLine`，并补一个末尾换行的反例夹具。

内核必须同时执行结构层的全部约束（不能假设调用方先跑过 Schema）。两层对同一夹具的期望由 `tests/contract/manifest.json` 的 `layer` 字段给出，`tests/contract/test_contract.py` 分别验证。

## 已知差异

当前无。

新的差异登记方式：在 `tests/contract/manifest.json` 中把对应夹具的 `kernel` 标为 `pending:<Issue> <缺陷号>`，并在此表登记；内核修复后测试会失败并提醒改为 `enforced`。

| 编号 | 差异 | 状态 |
|---|---|---|
| D2 | 0.1 内核曾接受 `2026-1-5` | 已由 #12 修复，夹具已改为 `enforced` |

## 运行

```bash
python -m pip install -e ".[dev]" "jsonschema>=4.18,<5"
python -m unittest discover -s tests -v
```

未安装 `jsonschema` 时结构层用例自动跳过，内核层用例照常运行。

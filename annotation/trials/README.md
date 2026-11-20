# 试标记录

尚无记录。每一轮试标建立一个子目录，命名为 `YYYY-MM-DD-<数据集>-r<轮次>`，例如 `2026-12-01-synthetic-v0-r1`。

## 目录内容

| 文件 | 内容 |
|---|---|
| `round.json` | 指南版本、指标定义版本、数据集与条目范围、标注者代号（不写真实姓名） |
| `annotator-a.json`、`annotator-b.json` | 独立标注结果 |
| `metrics.json` | 按 `TRIAL_PROTOCOL.md` §3 计算的结果、样本数、混淆表、脚本版本 |
| `disagreements.jsonl` | 每行一条分歧，格式见下 |
| `adjudication.md` | 裁决结论摘要，以及引发的指南或金标修改 |

## `disagreements.jsonl` 的行格式

```json
{"id": "d-001", "item": "syn-v0-009", "category": "cause", "a": "标注了 签名密钥 不可用 正向", "b": "只标注了报告原因", "gold": "只标注报告原因", "resolution": "A 错误；指南 §6 补例句", "guide_change": true, "gold_change": false}
```

`category` 取 `TRIAL_PROTOCOL.md` §5 中的代码。上面只是格式示例，不是试标结果。

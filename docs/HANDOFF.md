# 移交说明：Claude 主责部分全部转交 Codex

日期：2026-11-20 · 依据：负责人指示“整理内容，全部移交 codex 处理”

自本文合并起，`docs/DEVELOPMENT_PLAN.md` §11 中原由 Claude 主责的条目（M1 契约、M2 规则格式起草、M3 标注协议与数据）**全部改由 Codex 主责**。Claude 不再主动提交；只在负责人要求时做复核。

## 1. 移交范围

| 区域 | 文件 | 状态 |
|---|---|---|
| IR 契约提案 | `docs/proposals/`（P-1～P-5、P-7、迁移清单） | P-1/2/3/5/7 已由 Codex 在 #13 复核同意；**P-4 评审记录未填** |
| 时间区间提案 | `docs/proposals/P-6-time-intervals.md` | 在 **#19**，未复核、未合并 |
| Schema | `schema/ir-0.1`、`ir-0.2.draft`、`rules-0.2.draft`、`query-result-0.2.draft`；#19 增加 `ir-0.3.draft` | 0.2 输入已由内核执行（#14）；查询结果与规则 Schema 等 #5 |
| 契约测试 | `tests/contract/`（manifest、夹具、判例、迁移参考输出、`test_contract.py`） | main：66 个夹具（52 enforced，14 `unimplemented:#5`），5 个判例；#19 后 77 个夹具、9 个判例 |
| 标注 | `annotation/GUIDE.md`、`TRIAL_PROTOCOL.md`、`trials/` | 协议完成；**人工试标未做** |
| 数据 | `datasets/synthetic-v0/`、`tests/datasets/test_synthetic_v0.py` | main：19 条 / 31 个查询；**#18** 扩到 26 条 / 42 个查询，未复核、未合并 |
| 实验设计 | `docs/experiments/ten-classes.md` | 预注册草案；**门槛未冻结** |

## 2. 待处理事项（建议顺序）

1. **复核并合并 #18**（数据扩充）。纯数据，不改契约；42 个期望答案已在 0.1 内核上逐条核对。
2. **复核 #19（P-6）**，并决定 IR 0.3 的时机。建议：先合并提案与夹具（内核侧都是 `unimplemented:P-6`，不影响现有测试），**等 #5 完成后再实现 0.3**，避免内核同时追两个版本。#18 与 #19 一起合到 main 无冲突、测试通过。
3. **填写 P-4 评审记录**，然后实现 **#5**（规则引擎与溯源）。实现时：
   - 把 manifest 中 `unimplemented:#5` 的夹具逐个改为 `enforced`；
   - `cases/d1-*.json` 的 `p3-option-a` 期望改为可执行，并让 `test_query_cases_current_behaviour` 覆盖 0.2 判例（目前按 `version != "0.1"` 跳过）；
   - `tests/datasets/test_synthetic_v0.py` 改为用 0.2 内核直接执行，去掉“降为 0.1”和 `ir01` 分支，证据改为按顺序比较（P-4 §5）。
4. **#15 遗留建议**（非阻塞）：迁移时较早的“待确认”错误会掩盖后续错误。可以用占位值继续校验，一次报出全部问题。
5. **#6 人工试标**：需要负责人安排两名真实标注者，按 `annotation/TRIAL_PROTOCOL.md` 执行，结果放 `annotation/trials/`。不能用模型代替。
6. **十类实验门槛**：负责人在第一次测量前确认并冻结 `docs/experiments/ten-classes.md` §4 的门槛。
7. 之后按计划：#7 基线与评分 → #8 模型适配 → #9 规模测试。

## 3. 必须保持的语义约定

- **开放世界**：缺失记录不是否定，查询结果为“未知”。
- **分区精确匹配**：(context, valid_at) 完全相同才合并；不同日期、不同上下文、无日期各自独立，不互相冲突。P-6 只改变“断言属于哪些分区”，不改变这一条。
- **报告因果**（`r:claim:reported-cause`）永不升格为事实，也不能作规则前提或结论（Schema 与内核两层都要拦）。
- **前提冲突**（P-3 方案 A）：前提在本分区不是“支持”就不推出，记入 `suppressed`；直接的正、负证据照常保留。
- **规则**（P-4）：结论只能正向，负向前提只能引用不会被推出的关系（分层）；证据、被抑制推导都按 ID 码位升序输出。
- **不按来源数量投票**：两条“阻塞”加一条“未阻塞”仍是冲突。
- **无日期不等于一直有效**（P-6）。

## 4. 工作约定与坑

- **两层校验**：Schema 只管结构；跨引用、日历、分区和推导语义由内核检查。新增夹具时用 `layer` 写明属于哪一层。
- **manifest 的 `kernel` 字段**：`pending:<ref>` 是绊线，内核一修好测试就失败，提醒改成 `enforced`；`unimplemented:<ref>` 跳过；`rejected` 只作文档。
- **正则方言**：Python 的 `$` 会匹配末尾换行前，`.` 会匹配 U+2028。所有字符串字段都要叠加 `$defs/singleLine`；内核侧用 `value.splitlines() == [value]`。
- **Schema 文件里不要写入不可见换行字符**，一律写成 `\uXXXX` 转义（`json.dumps(ensure_ascii=False)` 不会转义 U+2028/U+2029 等，需要手工替换）。
- **数据集**：新增现象标签要同时登记到测试的 `REQUIRED_PHENOMENA` 和 `annotation/GUIDE.md`；每条断言 ID 以条目编号为前缀（`a:s020-…`）。
- **推导 ID**：`d:<rule>:` 加 `sha256(json.dumps([rule, premises], ensure_ascii=False, separators=(",", ":")))` 的前 32 位十六进制，与查询日无关。
- 远端残留的已合并分支（`feat/m0-*`、`feat/m1-*`、`feat/m3-annotation-protocol`、`feat/p4-rule-format`、`v0.1`）可由负责人删除。

## 本地接手进度（2026-11-20）

本地集成分支 `local/codex-handoff` 汇集 #18、#19、#20 及 #5 的规则引擎。上面的条目数与状态记录的是移交时点。

| 工作 | 本地可复核结果 | 后续依赖 |
|---|---|---|
| #4 / #15 迁移 | 类别待确认时，报告仍能给出其他独立的首个校验错误 | 保留人工确认及候选输出流程 |
| #5 IR 0.2 | 正式 API 和 CLI 使用分区索引；D1、两跳、负前提、带种子循环与输入置乱进入常规测试 | 合入前按最终提交运行跨平台 CI |
| #6 / #18 | 26 条合成数据、42 个查询用 0.2 正式入口逐条验证；十类 κ 与 kind κ 共用有效配对子集 | 两名真人独立试标，负责人在测量前冻结门槛 |
| #7 | 同一命令为三种基线与正式内核输出四值混淆矩阵、叶子及路径匹配。规则基线只覆盖 R1 | 冻结数据切分、评分口径，扩展独立规则基线的覆盖范围 |
| #19 IR 0.3 | 单日推导有效性与三日中断判例已纳入独立 Schema | 待 0.2 验收后实现运行时区间查询 |
| #8 / #9 | 保留原计划 | 分别依赖评测基准与规模测量方法 |

运行 `python3 -m baselines.evaluate datasets/synthetic-v0/items.json` 可复验工程结果。人工协议与试标记录目录见 [annotation](../annotation/)。

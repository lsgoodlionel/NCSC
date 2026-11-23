# #8 离线候选适配契约

从仓库根目录调用 `adapters.base.propose_ir(text, schema, sources=..., provider=...)`。本轮接口中的 `schema` 为已有 IR 的版本号（0.2 或 0.3）。省略 provider 时直接返回 disabled。测试替身接收原文和版本，返回一个 JSON 形状的 Python 字典。调用者负责预配置生成器可用的来源 ID，适配层从不自动生成 ID 或补齐断言。

调用者将来源 ID 映射到输入中的非空原文片段。候选经过同一内核的 validate_document 校验，每条来源的 description 还须逐字等于登记片段。通过返回 candidate 和独立副本；输入错误、生成异常及校验失败分别返回 invalid_input、provider_error、invalid_candidate。每次至多调用一次生成器。来源对照表用于核对出处；断言是否符合原文含义、否定或因果是否被误读，仍待人工评审。候选不会自动写入知识库。

复验命令为 `python3 -m unittest tests.test_adapter -v`。示例与测试使用本地函数替身。实际抽取效果需在 M3 数据冻结后评测。

## 指代反例回归

运行 `python3 -m unittest tests.test_adapter_referents -v`。三条开发用例固定项目、日期、看板来源及两个任务，只改变“已完成”所指的任务。每个测试替身返回手写候选，发布和迁移两次查询分别核对。显式指名发布时预期为支持／未知，显式指名迁移时为未知／支持，指代不明时为未知／未知。把完成状态移到另一任务，或在指代不明时任选一个任务，仍能逐字引用原文并通过候选校验，但双向查询会暴露错误。此处的预期只供离线开发回归，正式中文复核和冻结集抽取评测另行进行。

## 回环 Ollama 参考实现与本地抽取评分

从仓库根目录运行，运行时仅依赖 Python 标准库。已由调用者准备并运行的本地 Ollama 接收一次 `POST /api/generate`。发送方固定使用 127.0.0.1、无代理、无重定向，超时 120 秒；生成器使用 JSON 模式并关闭流式接收。启用前须设置 `NCSC_OLLAMA_MODEL`，可设置 `NCSC_OLLAMA_PORT`（默认 11434）。鉴权代理可设置 `NCSC_OLLAMA_REQUIRE_TOKEN=1`，凭据从 `NCSC_OLLAMA_TOKEN` 读取；未设置凭据时返回配置错误。普通本地 Ollama 不需要密钥。[Ollama 生成接口](https://docs.ollama.com/api/generate)

盲输入为仅含 id、text 的 JSON 行数组和对应 IR 登记表。调用者将逐条完整原文登记为本条目的 `src:excerpt`；该 ID 在不同条目中独立解析。取样时记录代码提交、模型名称及模型文件摘要，并锁存输入与输出。以下两个步骤可分别在生成侧和持有冻结参考的评分侧执行。

```sh
python3 -m eval.extraction predict packet.json registry.json --enable-local-model > predictions.json
python3 -m eval.extraction score adjudicated.json predictions.json
```

对先前独立锁存的外部盲预测，可用 `python3 -m eval.extraction validate packet.json registry.json responses.json > predictions.json` 取代第一步。responses.json 每行只含 id 和 assertions。每个候选的来源 ID 与原文片段均通过现有校验；上下文须已登记。provider_error 和 invalid_candidate 的条目保留在报告中。

评分在每条目内对角色三元组、极性、上下文、单日／区间去重，匹配数、预测数和参考数分别跨条目求和。micro-P 为匹配数除以预测数，micro-R 为匹配数除以参考数。零分母返回 null。调用失败或非法候选按该条零预测计；报告另列各状态计数。对文本抽取效果使用逐条独立裁决的标注作为参考。同一报告不评价来源身份识别、模型生成过程、未标注理由或保留来源摘要的质量。

## ai-eng-v1 的一次真实抽取

2026-11-23，在独立的 Codex GPT-6 系列会话中执行一次原文抽取。输入为公开的 26 段原文、登记表和指南；会话单独启动，未继承项目交互历史，工具按指令限于临时目录。没有测试操作系统级盲标隔离。模型后端快照不可见。协调人先锁存整份原始预测（SHA-256 `9214cc6d311e1bddef7be3989e260381fe494fe0c21e8926a31c57a2489513d3`），随后通过适配器校验，再对照本机受控裁决参考。此结果归属于该次 Codex 运行。Ollama 参考实现使用本地测试替身验收，本机当时无可用 Ollama 服务。

26 项均返回有效候选，预测与参考分别包含 24 个条目内去重断言键，24 个命中，断言级 micro 精确率和召回率均为 1.000。24 个预测来源引用均可定位到输入段落。本次使用整段回引，衡量的是片段归属；这项检查不能判断最小引文边界或独立外部来源的真实性。参考与预测来自同一模型家族，语料已公开用于开发。本次工程观测无法估计新语料的表现或真人可靠性。逐项预测及裁决表仅在协调人本机保存。
**ai-eng-v1 工程冻结评分。** 协调人用以下命令重新验证已锁存的原始盲预测，并核对公开语料、登记表和受控参考的冻结版本。真实裁决表只交给此评分端。条目缺失、重复、参考字节改变或引文无法与该条原文匹配时退出码为 2。完整作答中其余非法候选照实计入失败桶。

```sh
python3 -m eval.extraction score-frozen packet.json registry.json adjudicated.json responses.json
```

报告的 verified_source_occurrences 统计通过验证的候选中逐次出现的来源引用；同一原文被多个断言引用时分别计数。该数衡量原文与引用的字面对应，来源所述事实、语义指代和现实真实性仍需独立复核。通用 score 接受预校验候选，仅比较断言键并检查 IR 结构，无法核实引文与原文或冻结参考的绑定。

# #8 离线候选适配契约

从仓库根目录调用 `adapters.base.propose_ir(text, schema, sources=..., provider=...)`。本轮接口中的 `schema` 为已有 IR 的版本号（0.2 或 0.3）。省略 provider 时直接返回 disabled。测试替身接收原文和版本，返回一个 JSON 形状的 Python 字典。调用者负责预配置生成器可用的来源 ID，适配层从不自动生成 ID 或补齐断言。

调用者将来源 ID 映射到输入中的非空原文片段。候选经过同一内核的 validate_document 校验，每条来源的 description 还须逐字等于登记片段。通过返回 candidate 和独立副本；输入错误、生成异常及校验失败分别返回 invalid_input、provider_error、invalid_candidate。每次至多调用一次生成器。来源对照表用于核对出处；断言是否符合原文含义、否定或因果是否被误读，仍待人工评审。候选不会自动写入知识库。

复验命令为 `python3 -m unittest tests.test_adapter -v`。示例与测试使用本地函数替身。实际抽取效果需在 M3 数据冻结后评测。

# Claude 后续完善清单

本文件只描述未来协作任务；当前未联系 Claude、未创建远端、未同步或发布任何外部对象。

## P0：共享契约与正确性

1. 将 IR 契约抽成正式 JSON Schema，并让 Python 校验器与 Schema 运行同一组契约测试。
   - 依赖：确认 `version: 0.1` 冻结窗口。
   - 文件边界：新增 `schema/`、`tests/test_schema.py`；不要单方面修改 `ncsc/core.py` 的公共语义。
2. 为规则执行增加显式规则注册表、循环检测和重复推导消解。
   - 依赖：先定义规则 ID 稳定性与推导 ID 规范。
   - 文件边界：建议新增 `ncsc/rules.py`；与内核负责人评审接线改动。
3. 补全拒绝测试：重复来源、非中文别名策略、非法 ID、混合有/无时间证据、规则前提正负性。
   - 依赖：无。
   - 文件边界：只增改 `tests/`，发现契约歧义先提议，不直接改变共享契约。

## P1：基线与数据工程

1. 设计人工标注指南和可审计的小型数据集；把“报告因果”和“验证因果”分开标注。
2. 实现 JSON 精确匹配、轻量 KG 查询、规则引擎三种可复现基线。
3. 设计原研究材料迁移清单，但原始研究包保持在默认 Git 跟踪之外。
4. 评估模型适配接口；模型只能提出候选 IR，必须经过同一严格校验，不能绕过内核。

## P2：非功能验证

在数据与测量方法冻结后，实测规模、延迟、内存、可重复性、错误诊断和安全边界。不要预填或编造指标。

## 可并行边界

- 契约/Schema：`schema/`、`tests/test_schema.py`
- 规则：`ncsc/rules.py`、规则专属测试
- 数据：`datasets/`、`annotation/`（不得放真实敏感信息）
- 基线：`baselines/`
- 文档：除 README 的契约段外，可编辑 `docs/`

`ncsc/core.py`、IR version、状态词（支持/反对/冲突/未知）、作用域语义和来源/溯源字段属于共享契约。变更必须先形成提案并由代码与接口负责人共同评审。

## 验收命令

```bash
python3 -m unittest discover -s tests -v
python3 -m ncsc.cli validate examples/project_state.json
python3 -m ncsc.cli query examples/project_state.json --subject c:task:release --relation r:status:blocked --object c:value:true --context ctx:project-alpha --valid-at 2026-11-19
```

验收还应确认：离线运行、零 API 密钥；未知字段被拒绝；缺失返回未知；跨上下文/时间不合并；所有推导可追到规则和前提；报告因果不升级为验证因果。

## 未来仓库协作规则

等用户提供 GitHub 仓库地址后再配置远端。代码、数据、接口/Schema 各设一名唯一负责人；多 agent 按上述文件边界分工，避免同时写同一文件。每项工作使用小 PR，附测试与契约影响说明；共享契约至少需要接口负责人和受影响模块负责人评审。未经用户授权，不创建仓库、不推送、不邀请协作者、不联系外部 agent。

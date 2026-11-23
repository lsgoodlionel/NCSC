# NCSC 原型：数字—汉语原生语义认知架构

这是一个离线、确定性的最小纵切片，验证稳定概念编号、中文别名、显式关系角色、正负断言、来源、上下文/时间隔离、四值查询与白名单规则溯源。它不依赖 LLM、网络或 API 密钥。

“0–9 十类”目前只是待验证研究标签，不是本原型的公理，也不参与推理。

首次使用请从[项目发布状态核对手册](docs/USAGE.zh-CN.md)开始。手册提供可运行的四日示例、自有数据模板、日常复核流程及系统接入方法。

## 浏览器工作台

在仓库根目录运行 `python3 -m workbench.server`，打开 http://127.0.0.1:8765/ 。可以导入项目 JSON、选择应用、逐日查询、跟踪规则执行、比较四日索引复用耗时，或用已登录的 Codex 调用本机 NCSC 工具后继续提问。[工作台操作与架构](docs/WORKBENCH.md)

| 要完成的工作 | 入口 |
|---|---|
| 输入自己的工单、核对状态与依据 | [使用手册](docs/USAGE.zh-CN.md) |
| 理解内核、开放世界与时间分区 | [架构与可行性](docs/v0.1/README.md) · [版本契约](docs/proposals/README.md) |
| 复验 AI 工程开发集和四系统评分 | [冻结说明](datasets/freezes/ai-eng-v1/README.md) · [评分说明](baselines/EVALUATION.md) |
| 启用可选模型候选抽取 | [适配器与测量口径](adapters/README.md) |
| 复查性能、内存限制及大规模实测 | [规模测量](benchmarks/README.md) |

## 快速运行

从仓库根目录运行。下列命令使用 Python 3.9 或更高版本。macOS 若只有 `python3`，将 `python` 换成 `python3`；Windows 可用 `py -3`。

```bash
python -m ncsc.cli validate examples/project_state.json
python -m ncsc.cli query examples/project_state.json --subject c:task:release --relation r:status:blocked --object c:value:true --context ctx:project-alpha --valid-at 2026-11-19
python -m unittest discover -s tests -v
```

IR 0.2 使用同一条查询命令。下面的示例会返回发布任务受阻的证据、规则 ID 及可追到两个原始来源的前提。显式传入一个或多个 `--rule <文件>` 可替换默认 R1 规则集。

```bash
python -m ncsc.cli query tests/contract/fixtures/0.2/valid/example-migrated.json --subject c:task:release --relation r:status:blocked --object c:value:true --context ctx:project-alpha --valid-at 2026-11-19
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
- 可选 `valid_at`，格式为 `YYYY-MM-DD`。IR 0.3 也可用 `valid_during` 指定闭区间，例如 `{"from":"2026-11-19","to":"2026-11-21"}`，允许省略其中一端。

未知字段、悬空引用、重复 ID、空来源、未支持角色或时间结构会被拒绝。查询必须明确上下文；省略日期仅查询无日期分区，指定日期匹配同日断言及覆盖当日的区间断言。不同上下文或日期的证据不会合并成冲突。

## 当前白名单规则

初始规则、候选规则及其准入条件见 [M0 规则表](docs/M0_RULES.md)。开发环境可用 `python -m pip install -e ".[dev]"` 安装命令行入口与质量工具，然后运行 `ncsc validate examples/project_state.json`、`python -m ruff check ncsc tests`、`python -m mypy`。仅运行示例和单元测试时可直接使用源码。

`resource_unavailable_blocks_task`：同一证据分区中，若任务 `需要资源` 某资源，且该资源被正向断言为 `不可用=true`，则推导任务 `阻塞=true`。推导结果列出规则名和两条前提 ID。规则只做精确 ID 匹配，不做词面猜测。

`报告原因为` 只表示“某来源报告了因果说法”；内核不会把它提升为已验证因果，也不会据此推导。

## 边界与后续

查询按日求值。当前不支持整段区间聚合、时区、上下文继承、概率、自然语言解析、开放世界规则学习或跨分区推理；遇到这些结构会拒绝或返回未知。案例是少量真实结构的合成数据，不是生产事实。

完整的分阶段开发方案、已确认缺陷清单与 IR 0.2 提案草案见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。

IR 0.2 正式查询按带极性的事实收敛。冲突前提记录在 `suppressed` 中，证据可沿 `trace` 追至来源。超过查询预算时 CLI 以状态码 3 退出。0.2 和 0.3 的 CLI 输入上限为 2 MiB，响应上限为 1 MiB。为兼容既有 0.1 文件，正式 `query` 在解析后检查 IR 字节数；实验入口 `query-preview` 在解析前限制读取。

合成集含 26 个条目、42 个查询。JSON、轻量 KG 和规则基线的复验命令见 [基线说明](baselines/README.md)。0.3 的派生证据只适用于查询当日，原始叶子保留来源声明的区间。本轮已完成 AI 工程试标及评分冻结，见[冻结范围](datasets/freezes/ai-eng-v1/README.md)与[规模实测](benchmarks/README.md)。

NCSC V0.1 的第一轮完整工程研究方案已纳入 [docs/v0.1/README.md](docs/v0.1/README.md)，包括工程可行性、架构、语义 Schema、实施计划、风险和研究问题。该研究包仍是启动决策材料，不代表核心公理已经冻结。

# 把 NCSC 用于项目发布状态核对

项目负责人问“指定日期，哪些记录支持或反对发布受阻？”时，把当日可核查的断言交给 NCSC，读取四值结果，再沿证据树回到看板、配置或工单。首次试用建议选一个项目、一项发布任务和一种关键资源。交付物是一份经校验的事实文件，以及按日保存的查询 JSON。内核离线运行；无需模型服务、容器或 API 密钥。

## 一、跑通随附案例

在随附源码根目录运行。Mac 本机现成工作目录为 `/Users/lionel/Develop/ncsc-use-guide`。需要 Python 3.9 或更高版本。使用源码模式可以跳过安装；Windows PowerShell 将命令中的 `python3` 替换为 `py -3`。

```sh
python3 -m ncsc.cli validate examples/release-readiness.json
python3 -m ncsc.cli query examples/release-readiness.json --subject c:task:release --relation r:status:blocked --object c:value:true --context ctx:project-alpha --valid-at 2026-11-19
```

校验应返回 `{"valid": true, "version": "0.3"}`。第二条查询应返回 `status: 支持`。打开第一条 evidence，查看 derived_by、premises 和 trace：构建配置说发布需要签名密钥，资源登记表说签名密钥不可用，两条记录在当天、同一项目内满足白名单规则。每个叶子的 sources 给出相应的记录。

只改最后的日期，观察同一问题的四种结果：

| 日期 | 输出 | 现场应怎样读 |
|---|---|---|
| 11 月 19 日 | 支持 | 两条前提齐全，规则推出发布受阻。 |
| 11 月 20 日 | 未知 | 运维回执说密钥可用，与登记表相抵。查看 reason=premise_conflict 和 suppressed，先核对密钥状态。 |
| 11 月 21 日 | 冲突 | 规则仍支持受阻，看板同时明确说未受阻。保留两路证据，由负责人核实。 |
| 11 月 22 日 | 反对 | 资源记录的区间已结束，当天仅看板明确说未受阻。 |

事实区间含首尾两日。省略 --valid-at 只查无日期记录；它不会自动取今天或最新记录。冲突只在同一上下文和同一查询日判断。未知也可能来自完全没有证据，此时查看 reason=no_evidence。

## 二、换成自己的记录

复制示例到团队自己的受控数据目录。保留一份原始快照。示例内所有断言均为合成数据，开始录入时应清空 assertions，再逐条加入业务记录。已有概念适用时沿用其稳定 ID；新增概念先登记到 concepts，再用 ID 引用。查询输入使用 ID，aliases 保存中文叫法。

例如，项目 Alpha 的发布工单 REL-128 明确记载 2026-12-01 发布未受阻时，在 assertions 数组加入下面这条记录。示例中所用概念已声明。

```json
{
  "id": "a:rel-128-clear",
  "roles": {"subject": "c:task:release", "relation": "r:status:blocked", "object": "c:value:true"},
  "polarity": "negative",
  "context": "ctx:project-alpha",
  "valid_at": "2026-12-01",
  "sources": [{"id": "src:rel-128", "description": "示例工单 REL-128，12 月 1 日复核记录：发布任务未受阻。"}]
}
```

将示例工单号、日期、项目、来源说明和状态替换为实际记录。每条断言使用唯一 ID；同一命题有相反记录时分别录入并保留各自来源。“没找到工单”应保留为缺证；只有原文明确否定才录入 negative。来源说明应能让复核人定位原文。记录“有人报告原因是……”时，使用登记的报告原因关系；仅凭归因陈述无法建立资源不可用等独立事实。

## 三、日常交付流程

| 环节 | 负责人做什么 | 留下什么 |
|---|---|---|
| 录入 | 项目协调人整理工单、配置和看板，逐条确认对象、项目、日期、正负和来源 | 一份按版本保存的 UTF-8 IR 文件，原始资料按团队权限保管 |
| 校验 | 对该文件执行 validate。按报错的字段路径修正非法 ID、缺少来源或日期格式后重跑 | 校验退出码 0 的输入快照 |
| 查询 | 将下方命令指向自己的输入，按项目和日期逐次执行 | 一份含 status、evidence 和 suppressed 的 JSON |
| 复核 | 负责人展开 trace。对冲突核对两侧原文，对未知区分缺证和前提冲突；有新记录后再查询 | 查询日期、输入快照、内核版本、结论及对应工单 |

以下假设你将业务文件保存为当前目录的 project.json。输出路径按项目与日期命名。

```sh
python3 -m ncsc.cli validate project.json
python3 -m ncsc.cli query project.json --subject c:task:release --relation r:status:blocked --object c:value:true --context ctx:project-alpha --valid-at 2026-12-01 > alpha-2026-12-01.json
```

自动任务应先检查命令退出码，再读取输出。查询成功返回 0，四种业务状态都可能出现；输入或参数错误通常返回 2，查询资源或嵌套超限返回 3，诊断写入标准错误。超限时应缩小输入或查询范围。0.2/0.3 CLI 输入预算为 2 MiB，查询响应预算为 1 MiB。百万条基准在生成语料阶段触及测试预算，不能据此估算实际服务容量。

## 四、接入已有系统

在应用内反复查询同一份数据时，可复用 KnowledgeBase 实例。每个新快照重新构造实例，将结果作为结构化字段提供给日报或工单页面。当前交付的入口是 CLI 和 Python 库；定时抓取、数据库持久化、身份权限和业务页面由接入方负责。

```python
from ncsc import KnowledgeBase

kb = KnowledgeBase.from_path("examples/release-readiness.json")
result = kb.query("c:task:release", "r:status:blocked", "c:value:true",
                  "ctx:project-alpha", "2026-11-20")
print(result["status"], result.get("reason"))
```

如果输入只有中文原文，先由业务人员结构化录入即可上线试用。可选的本地 Ollama 提供方可生成候选 IR，还需经过来源核对、语义复核和正式校验，再进入业务快照。此次验收中的真实模型成绩来自公开工程开发集上的一次 Codex 抽取。新项目的文本质量应单独验证。[模型适配说明](../adapters/README.md)

## 五、交给另一台机器或团队验收

将随附源码与两个 examples 文件一起复制到新目录。从源码根目录重跑第一节。使用 GitHub 已发布的 04f1c835 主线时，也可直接用随仓库已有的 `tests/contract/fixtures/0.2/valid/example-migrated.json` 执行第一节的 11 月 19 日查询；四日教学案例随本手册提供。

需执行完整回归时，推荐使用独立虚拟环境。首次安装开发依赖需要可访问的软件包源，或团队已有离线包。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m annotation.verify_ai_freeze
.venv/bin/python -m baselines.evaluate datasets/synthetic-v0/items.json
```

Windows 将 .venv/bin/python 换成 .venv\Scripts\python.exe。日常使用验收以四日案例的结果和可回溯来源为准；完整回归再核对 127 项测试、冻结清单和四系统报告。工程开发集共 26 条、42 问；这些结果不衡量陌生项目的模型抽取准确率。

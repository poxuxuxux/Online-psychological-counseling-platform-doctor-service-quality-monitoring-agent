# 管理 Agent 结果 Agent 与共享通信池

实现日期：2026-10-15。本方案用于本地新结构化评价链路，现有Railway演示前端尚未切换。

## 流程与职责

管理Agent → 确定性计划校验 → 通信池发布情境与任务 → 三个评价Agent → 证据核验 → 仲裁与一次定向复评 → 最终采纳记录 → 结果Agent → 报告保存。

管理Agent只提出候选情境与计划。结果Agent对应原流程图中的总结Agent，只生成有来源引用的文字说明，不修改单项分数或总分。总分汇总尚未实现时，说明中不会补造数值。

## 管理与情境识别

实现文件：`app/agents/management.py`。

输入为本次会话和任务快照中的指标目录。输出ManagementPlan包括context_summary、consultation_stage、needs_history、events和tasks。events用本次消息ID关联诉求、医生回应、患者反馈和不确定性；tasks列出18项指标、负责人、关联事件与适用性提示。

后端强制检查：18项完整且无重复；8/6/4归属正确；事件ID唯一；消息属于本次会话；任务关联的事件存在。D6任务始终保留，最终适用性由评价/核验按Skill判断。consultation_stage是咨询阶段，不作为临床初诊/复诊的确定判断。

计划校验失败或调用失败时，保留安全错误码，退回完整固定任务，management.status=fallback。管理情境是候选提示，不作为评分证据。needs_history只提出需求，工具未接通时报告明确记录history_requested_but_tool_unavailable，不编造历史内容。

## 结果 Agent

实现文件：`app/agents/result_summary.py`。

从通信池中读取最终采纳、核验supported且没有待人工复核规则命中的Finding。不把未核验版本、未决争议或完整原始会话传入总结模型。

输出ResultNarrative包含observations和improvements，每条必须引用输入范围内的finding_ids。后端拒绝不存在的引用、额外评分字段及常见数值评分表述。结构化分数不可写回；限制项、复核标记和score_explanation由后端保留。

没有可用结论时summary_status=skipped；模型或输出校验失败时为failed并保留固定状态说明；成功时为completed。格式和引用检查不能证明所有自然语言解释都正确，报告仍保留人工审阅要求。

## 持久化共享通信池

接口是`app/application/communication.py`中的RunCommunicationPool。直接测试可用内存模式；worker使用`LocalJobStore`的communication_records表持久化。

| 记录类型 | 内容 |
| --- | --- |
| context | 管理情境、已校验计划、规则版本 |
| task/task_status | Agent任务、指标、上下文关联和执行状态 |
| finding/verification | 初评、复评及与finding_id关联的核验 |
| conflict/arbitration | 分歧与仲裁或应用规则建议 |
| revision/adoption | 新旧版本关联、最终采纳映射、未决指标 |
| summary/failure | 结果说明或安全错误码 |

每条记录保存record_id、run_id、kind、source、payload、时间、schema_version，以及可选correlation_id和supersedes_record_id。新增记录表达状态变化，不覆盖旧记录。SQLite触发器拒绝修改和删除；记录ID不可重复，关联引用不能跨run，外键保证任务存在。

这不只是进度日志：评价执行器从池中读取管理情境与任务提示；复评关联旧结论；结果Agent根据采纳记录选择已确认Finding。模型不能直接操作数据库，写入和读取由应用编排控制。

当前支持核验/仲裁触发的定向复评。风险Hook、跨事件分歧Hook及任意新发现触发跨指标任务的完整机制尚未接入。数据保留/删除政策和PostgreSQL生产实现也仍待设计。

旧`domain/ledger.py`、`InMemorySharedLedger`及`agents/subagents`中的早期管理/总结占位接口继续留给旧演示协调器；新链路实际入口是本文件指明的management.py、result_summary.py和RunCommunicationPool，不再依赖这些占位类。

## API与报告

新增认证接口：

```text
GET /api/v1/evaluation-runs/{run_id}/communication?after_sequence=0&limit=50
Authorization: Bearer <LOCAL_API_TOKEN>
```

返回run_id、records和next_sequence。limit最大200，按next_sequence继续分页。未知任务404，缺失或错误令牌401。记录包含本次任务的结论和证据内容，只供已授权操作员访问。

报告增加management、result_summary、summary_status、score_explanation、communication_run_id和communication_record_count。summary为展示文字，result_summary保留逐条Finding来源。

## 输出可靠性与验收

本轮126项自动化测试与Ruff检查通过。真实Qwen运行run-4b30c0a2-3e5c-46c0-ad69-8d84736b439f中，管理Agent完成并通过校验，55条通信记录通过认证API分页读取及数量核对；专业服务Agent连接失败，最终仅10项评价，结果Agent因没有可总结的已确认结论而跳过。因此这次完整真实链路未通过验收。

另用固定合成结论单独验证结果Agent时，调用仍返回model_connection_failed，尚未获得真实结果Agent的成功响应。其结构校验、失败处理和完整集成目前由模拟Provider测试验证，不能把这些测试当作真实模型验收成功。

结构化调用使用百炼非思考模式的JSON Object输出，并继续执行本地Schema和业务校验；普通固定文字连接测试仍使用文本模式。官方依据：https://help.aliyun.com/zh/model-studio/qwen-structured-output 。不会自动重试付费调用。

自动化测试覆盖非法管理计划降级、18项完整分派、情境传递、跨任务隔离、不可覆盖、复评版本关联、总结引用范围、拒绝新增分数及原流程回归。真实验收命令是 `python -m app.smoke`，读取本地.env后执行，最多约11次合成会话调用，并通过API分页核对通信池记录数。

尚未完成：历史检索Tool、D2工具事实注入、风险/分歧Hook、确定性总分汇总、人工复核提交、真实数据完整授权脱敏和前端联调。三部分接入不代表整个产品已完成。

# 模块维护契约

## 依赖方向

API → 组合根 → Workflow → Context / Team / Evaluation → Domain Ports。
Infrastructure 实现 Ports，由组合根注入；Domain 不导入 FastAPI、LangGraph 或数据库驱动。

`workflow/service.py` 只定义主流程顺序、恢复与超时。`team/runtime.py` 只负责调度和自主循环。
`team/tools.py` 执行有边界的工具；`team/state.py` 提供可序列化共享任务板、证据池、消息队列；
`team/conflicts.py` 负责事实冲突候选。独立模型决策与工具执行分离，便于把工具后续拆为服务。

## 常见调整入口

- 增减指标/维度、评分锚点、权重：`app/rubrics/metrics`。保持 YAML 与 SKILL.md 发布状态一致。无需改团队类。
- 更换 Qwen/GLM 或增加供应商：实现 `ModelGateway.json` 并在 `bootstrap.py` 注入。
- 对接平台历史表：实现 `EvaluationRepository.history` 和 `save_session`，必须保持医患双键、严格时间过滤、不可变输入及完整性契约。
- 更换数据库：实现 Repository 接口；保持租约与 checkpoint 的原子性。默认 PostgreSQL 和本地 SQLite 共用 SQL 契约。
- 更换对话对象存储：实现 `object_store.put/get/delete/ping`，在 `bootstrap.py` 注入。对象先上传，数据库再以事务提交引用；跨服务没有原子提交，上传失败不得替换旧引用。
- 接知识库：实现 `KnowledgeSource.search`，返回版本和来源，禁止把规范文档当作当前医生行为证据。
- 增加工具：更新 ToolCall 枚举、TOOL_HELP、TeamTools.execute；验证权限、输入、预算和恢复重放语义，再加行为测试。
- 更改风险阈值或汇总策略：`evaluation/scoring.py`，升级 policy_version；不修改 Agent 评分。
- 更改自然语言总结或纵向比较：`evaluation/reporting.py` 中独立纯函数；保留当前证据与历史评分隔离。
- 更改 UI：保留 `api/contracts/evaluation.ts` 与后端报告契约一致；新增字段不改变旧字段语义。

## Runtime 状态所有权

每个运行拥有独立 `data`；无全局任务列表或全局消息队列。`team.tasks[agent_id]` 是独立任务上下文，
`team.evidence` 存原文，`team.messages` 存传递状态，`context` 存当前/历史背景。

Agent 只能提交 `metric_ids` 分派范围内的结果；Reviewer 无评分写权限。消息工具可以将接收任务重新激活。
每个工具动作在内存中整体成功或回滚。启用 Bucket 时，save 节点先上传加密快照，再由数据库事务提交引用和协作审计。模型不能传递任意 session_id 查询历史，
历史范围始终来自可信 session 的患者、医生和时间。

主图和子图都使用 LangGraph `StateGraph`。动态调度采用公平轮转，每次只执行一个 Agent 的决策；
没有固定 A→B 协作链。将来可以将独立决策并发化，但必须保持消息可见性、事务提交和状态合并规则。

## 恢复与失败契约

checkpoint 在模型调用前记录预算，在工具成功后记录动作和消息。租约失效时禁止旧 worker 写入。
未处理消息、缺失指标、失败 Agent、预算耗尽都使结果保持 partial/failed；缺失指标显式生成 NOT_EVALUABLE。
证据校验失败不会被零分或平均分掩盖。数据库失败不回退到另一数据库，避免产生两份不一致历史。

外部副作用工具必须增加幂等键和事务 outbox 才能接入；当前没有自动给患者发消息、修改医嘱等工具。

## 测试划分

`test_workflow.py`：真实 LangGraph 循环、消息唤醒、修订、Reviewer、历史、防锚定、恢复和预算。
`test_api.py`：FastAPI 生命周期、前端兼容、身份边界、报告与审计读取、人工复核。
`test_policies.py`：动态维度、Skill 冲突、风险保留、模型异常。
`test_postgres.py`：可丢弃 PostgreSQL 的事务审计；CI 提供容器，默认本地没有测试地址时跳过。
`test_object_storage.py`：Bucket 引用、加密校验、旧行迁移、上传失败回退和完整评价工作流。

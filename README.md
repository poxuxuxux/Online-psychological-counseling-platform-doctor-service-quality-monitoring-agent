# 医生服务质量评价 Agent Teams

Python 3.11+ / FastAPI / LangGraph / PostgreSQL。评价对象是医生服务行为。外层确定性流程，内层按需协作团队；不根据分数诊断患者。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# 填写模型配置；已有 .env 时不要覆盖。
.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，接口文档为 `/docs`。无 DATABASE_URL 的 local 环境使用 `data/local/teams.sqlite3`。无模型配置会持久化明确的失败/不可评价结果，不生成演示分数。

```powershell
.\.venv\Scripts\python.exe -m app.cli check
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-teams
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m app.cli evaluate examples/team-session.json --output data/local/report.json
.\.venv\Scripts\python.exe -m app.cli resume <evaluation_id>
```

CLI 会加载 `.env`；`evaluate` 会调用配置的真实模型。自动测试使用可编程模型替身，执行真实图、工具、数据库和 API。`TEST_DATABASE_URL` 专用于可丢弃测试库，CI 启动 PostgreSQL 16 执行集成测试，禁止把它指向生产数据库。

## 模块边界

```text
app/
  domain/          Pydantic 输入/动作/评分契约、模型/仓储/知识接口
  context/         对话规范化、医患关系查询、初复诊路由、历史上下文
  rubrics/         现有 metric.yaml + SKILL.md、动态目录加载和版本哈希
  team/            任务状态、共享证据、消息工具、独立 Reviewer、动态子图
  evaluation/      证据语义校验、确定性评分、服务风险、总结、纵向分析、报表
  workflow/        外层 StateGraph、依赖编排、恢复入口和总超时
  infrastructure/ Qwen/GLM 网关、PostgreSQL/本地 SQLite 适配
  api/            HTTP 参数、鉴权、响应；不实现评分规则
  bootstrap.py    组合根：注入模型、仓储、Skill 和知识库
  config.py       运行预算与环境配置
  web/            原前端构建产物
```

更换模型实现 `domain.ports.ModelGateway`，更换知识源实现 `KnowledgeSource`，更换存储实现 `EvaluationRepository`。通过 `build_container` 或 `create_app` 注入，评分逻辑无需改动。细节见 [模块开发说明](docs/MODULES.md)。

## 执行流程

主图节点：预处理 → Session Context → Initial / Historical Context → Team Lead → Team Initialization → Team Subgraph → Completion Check → Evidence Validator → Scoring → Risk → Summary → Longitudinal Analysis → Report → Storage。

团队子图：`schedule → observe → reason → act → save → schedule`。不是一次并行评分后结束；每一步根据当前观察调用工具，并重新进入调度。

- 主责 Evaluator 按 `app/rubrics/groups.py` 分为 D1+D3、D2+D5、D4+D6 三组；原始六个维度仍独立评分和统计。新增未映射维度会自动建立单独 Agent。临时 Reviewer 在需要时创建。
- 任务拥有独立观察记录、负责指标、状态、步数和耗时。消息接收者在已完成或等待状态下也会重新进入 PENDING。
- 消息经过 PENDING → DELIVERED → PROCESSED；接收者读取后必须记录采纳/无关/已答复及理由，才能完成任务。
- 共享证据必须是当前消息中连续原文，带角色、消息 ID、轮次、来源 Agent；解释不能充当事实。
- 只允许指标主责 Agent 修订自己的评分。全部修订和原始版本保存，Reviewer 只提出复核意见。
- 相同主体、行为和范围的相反事实主张触发复核；不同维度分数差异不触发冲突。表达未被归一为同一行为的语义冲突可由 Agent 主动报告；当前不宣称确定性检测器能识别全部语义等价表述。
- 严重服务风险标记单调保留，Reviewer 不能取消。
- 有步数、轮次、消息、复核、修订、单 Agent 耗时、总耗时和模型调用数限制。

工具包括 `read_skill`、`get_dialogue`、`get_evidence`、`share_evidence`、`time_calculator`、`search_knowledge`、`get_session_context`、`get_previous_evaluations`、`send_message`、`get_messages`、`acknowledge_message`、`request_review`、`submit_review`、`submit_evaluation`、`wait`、`finish`。模型输出结构化工具决策，后端执行受控能力，不执行模型提供的 Python/SQL。

## 初复诊与历史防锚定

`patient_id + doctor_id + session_time` 决定历史查询；仅查询相同医患关系的严格更早会话，排除本次会话。时间统一 UTC，必须带时区。

- 找到更早会话：FOLLOW_UP。
- 没有更早会话，身份时间齐全，可信导入方确认 `history_complete=true`：INITIAL。
- 其余：UNKNOWN。不能将“没查到”自动当成初诊。

`history_complete` 是平台导入契约，默认 false，不能由 LLM 设置；接入方只有确认历史导入完整时才能置 true。历史原始数据通过受保护的 `/sessions` 导入。旧数据库表保留，但不自动猜测它们的医患键或时间字段，也不把旧演示分数并入新标准。

历史评价、风险、总结与未解决问题进入服务端 Context Store 和纵向分析。常规 Evaluator 只看到会话类型和历史可用状态。历史工具仅对 Skill 的 `allowed_sources` 明确包含 `historical_dialogue` 的指标开放，只返回历史事实，隐藏历史分数与总结。现有指标尚未声明该来源，所以历史工具会明确返回不允许，不会偷偷注入旧分数。

## Skill 与评分

保留的指标位于 `app/rubrics/metrics/<metric_id>/`。维度由 `dimension_id` 或指标 ID 的点号前缀确定，可增加新维度而不改 Agent 类。每次运行冻结规则内容、说明及哈希。

18 个指标以 `metric.yaml` 的 `status` 字段为发布状态唯一依据。配套 `SKILL.md` 已同步为遵循该状态：published 指标可以按已发布锚点评分；证据不足、材料冲突或无法区分锚点时仍须留空并触发相应人工复核。

模型请求仅携带 `metric.yaml` 的结构化规则，避免重复传入旧版说明中的接口和候选锚点。规则与对话由程序预载；Agent 仍可主动取证、协作和修正。核验输出的 `issues` 只接受阻断错误代码，普通说明进入 `notes`。有效的语义核验指出评分或引用错误时，原评价者最多自动修正一次，随后独立复核；无法解决的问题保留待复核，不直接放行。

新报告的 `team.usage` 记录供应商返回的输入/输出 token、实际记录用量的请求数与输入字符数，前端报告中可展开查看。旧报告没有 token 统计，不把缺失统计当作零成本。模型超时和服务错误每个 Agent 最多连续累计两次后停止，避免预算空转。

可运行 `python -m scripts.prepare_real_samples` 从本地真实数据流式选取 3 份订单范围样本，输出到忽略提交的 `data/private/quality-samples`。不会把跨年线程当作一次问诊，也不会截断长订单来伪装完整会话。样本去除原始身份元数据及可识别的姓名、联系方式，但自由文本不保证完全匿名，必须保留私有访问。没有明确结束事件时 `observation_complete=false`，没有明确接诊事件时不生成首次响应计时起点。

分数必须在 Skill 的 `score_values` 中，NOT_EVALUABLE / NOT_APPLICABLE 不补零。语义校验逐项核验事实、适用性和评分锚点；缺项、引文不匹配、未决冲突不计分。总分使用 Skill 权重均值，默认等权；所有适用指标覆盖并通过校验且团队任务完成，才生成总分。风险为服务质量风险：总分低于 3/5 为 high、低于 4/5 为 medium，证据充分且无标记为 low；证据不足为 unknown，严重服务风险标记优先 high。这些是版本化工程策略，不是临床风险诊断。

总结由确定性模板和已核验结果生成自然语言，不额外让 LLM 编造事实。纵向分析仅在规则哈希一致且两次总分均有效时计算变化；历史来源、限额及不可比原因保留。

## API 与权限

- `POST /api/v1/evaluations`：同步完成并返回兼容现有前端的报告。
- `POST /api/v1/runs`：持久化待执行任务，返回 run_id；不隐式创建后台进程。
- `POST /api/v1/runs/{id}/execute`：执行/恢复。长运行可先创建 ID，再由客户端轮询 GET。
- `GET /api/v1/runs/{id}`：状态、阶段、最终报告。
- `GET /api/v1/runs/{id}/audit`：任务、证据、消息状态、模型调用数、复核、版本和工具审计。
- `POST /api/v1/sessions`：导入可信平台会话；同一 session_id 的内容不可被覆盖。
- `GET /api/v1/consultations`、`/{session_id}`、`/evaluations/recent`、`/evaluations/overview`：查询。
- `/evaluations/{id}/reviews`：人工复核记录；不会静默重写机器评分。
- `/demo/session`、`/demo/sessions`、`/demo/sessions/{id}`：内置合成样本。

真实数据和审计需 `Authorization: Bearer <EVALUATION_API_TOKEN>`，至少 24 字符。匿名接口只允许服务端固定合成样本，伪造 source_id 无法绕过。此 token 是单平台管理凭据；多机构权限隔离需在接入平台认证层另行实现。前端当前仍为合成样本工作台，真实平台数据通过 API/CLI 接入。

## 持久化与恢复

新增 `team_sessions`、`team_runs`、`team_tasks`、`team_evidence`、`team_messages`、`team_events`、`team_human_reviews`，不删除旧表。启动执行幂等建表；后续 schema 变更应新增迁移。

每步模型请求前预留预算并保存状态，工具动作后将整个快照和协作审计在同一事务提交。恢复从已提交的节点边界继续；进程在模型调用中崩溃时，该调用可能重发，但已预留调用数不会回退。已提交消息不会丢失或重复发送，未提交的内存动作不对外可见。数据库租约防止同一 run 被两个 worker 同时执行；崩溃后等待租约过期，再调用 execute 或 CLI resume。主动取消释放租约。

这是应用级节点快照恢复，不宣称提供 LangGraph 原生 checkpoint 的任意节点 time-travel。后续可以替换存储并增加原生 checkpointer，当前外部工具均为只读或事务内状态修改。

## Railway

保留 `Dockerfile` 和 `railway.toml` 启动入口 `app.main:app`。在 **后端服务** Variables 中引用既有 PostgreSQL 服务的 `DATABASE_URL`；它由 Railway 注入，不需要复制密码到本地 `.env`。同时设置模型配置、`APP_ENV=production`、`EVALUATION_API_TOKEN`。`/health` 为存活检查，`/ready` 检查数据库并报告模型及规则状态。

该重构已准备部署配置，未自动发布到 Railway，也未连接生产库执行测试。旧独立 worker 入口已移除；运行与恢复统一通过新 API/CLI。若 Railway 原来还有旧 worker 服务，应停用旧 start command 或改为调用新运行接口。

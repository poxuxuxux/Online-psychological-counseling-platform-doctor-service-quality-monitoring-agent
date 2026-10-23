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
  evaluation/      评分汇总、服务风险、总结、纵向分析、报表
  workflow/        外层 StateGraph、依赖编排、恢复入口和总超时
  infrastructure/ Qwen/GLM 网关、PostgreSQL/本地 SQLite 适配、加密 Bucket 对象存储
  api/            HTTP 参数、鉴权、响应；不实现评分规则
  bootstrap.py    组合根：注入模型、仓储、Skill 和知识库
  config.py       运行预算与环境配置
  web/            原前端构建产物
```

更换模型实现 `domain.ports.ModelGateway`，更换知识源实现 `KnowledgeSource`，更换存储实现 `EvaluationRepository`。通过 `build_container` 或 `create_app` 注入，评分逻辑无需改动。细节见 [模块开发说明](docs/MODULES.md)。

## 执行流程

主图节点：预处理 → Session Context → Initial / Historical Context → Team Lead → Team Initialization → Team Subgraph → Completion Check → Scoring → Risk → Summary → Longitudinal Analysis → Report → Storage。独立 Evidence Validator 已移除。

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

18 个指标以各自 `SKILL.md` YAML frontmatter 的 `status` 字段为发布状态唯一依据；当前 18 项均为 published，包括 D6.1、D6.2。发布状态不等于所有指标都已开放数值评分：结构化 `scoring_blockers`、证据不足、材料冲突或无法区分锚点时仍必须留空并按对应规则人工复核。草案指标则不得提交数值评分，适用案例须记录 `rubric_unpublished`。

模型请求携带 `SKILL.md` 的结构化规则与执行说明。规则与对话由程序预载；Agent 仍可主动取证、协作和修正。已移除独立模型语义校验及其自动修正调用；报告明确标记 `verification_mode=none`，前端显示“Agent 已评分”，不声称经过独立核验。

新报告的 `team.usage` 记录供应商返回的输入/输出 token、实际记录用量的请求数与输入字符数，前端报告中可展开查看。旧报告没有 token 统计，不把缺失统计当作零成本。模型超时和服务错误每个 Agent 最多连续累计两次后停止，避免预算空转。

可运行 `python -m scripts.prepare_real_samples` 从本地真实数据流式选取 3 份订单范围样本，输出到忽略提交的 `data/private/quality-samples`。不会把跨年线程当作一次问诊，也不会截断长订单来伪装完整会话。样本去除原始身份元数据及可识别的姓名、联系方式，但自由文本不保证完全匿名，必须保留私有访问。没有明确结束事件时 `observation_complete=false`，没有明确接诊事件时不生成首次响应计时起点。

分数必须在 Skill 的 `score_values` 中，NOT_EVALUABLE / NOT_APPLICABLE 不补零。提交工具仍校验指标归属、发布状态、分数锚点取值、原文证据引用、时间事实和显式复核规则；未解决冲突或缺项不计分。这里不再有独立的事实/适用性/评分语义复核，Agent 判断可能有误。总分使用 Skill 权重均值，默认等权；覆盖门控只统计可计分指标（published 且无 scoring_blockers），配置上无法数值计分的指标在 `quality_profile.score_exclusions` 中披露，不再阻塞总分；其余全部适用指标可计分且团队任务完成，才生成总分。风险为服务质量风险：总分低于 3/5 为 high、低于 4/5 为 medium，覆盖不足为 unknown，严重服务风险标记优先 high。这些是版本化工程策略，不是临床风险诊断。

带有结构化 `scoring_blockers` 的指标即使状态为 published，也不能提交或计入数值评分；必须提交对应人工复核原因。当前 D2.1、D2.2 的计时政策尚未配置，因此只记录可用时间事实，不生成确定性分数，但不再因此放弃其他指标的总分。

总结由确定性模板和 Agent 的可计分结果生成自然语言，不额外让 LLM 编造事实。纵向分析仅在规则哈希一致且两次总分均有效时计算变化；历史来源、限额及不可比原因保留。

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

真实数据和审计需 `Authorization: Bearer <EVALUATION_API_TOKEN>`，至少 24 字符。匿名接口只允许服务端固定合成样本，伪造 source_id 无法绕过。此 token 是单平台管理凭据；多机构权限隔离需在接入平台认证层另行实现。前端服务模式默认不显示演示会话；在“服务连接”输入访问令牌后，仅列出真实导入会话，批量评价也只处理这些会话。离线样例需显式切换。访问令牌只保留在当前页面内存，刷新后需重新输入。

## 持久化与恢复

新增 `team_sessions`、`team_runs`、`team_tasks`、`team_evidence`、`team_messages`、`team_events`、`team_human_reviews`，不删除旧表。启动执行幂等建表；后续 schema 变更应新增迁移。

每步模型请求前预留预算并保存状态。启用 Bucket 后，会话原文与完整运行快照先加密压缩上传，数据库只在事务中写对象引用、报告和协作审计；上传失败不会把新引用写进数据库。跨服务无法做到严格原子提交，数据库提交失败可能留下未引用对象，清理时必须先核对数据库引用。恢复从已提交的节点边界继续；进程在模型调用中崩溃时，该调用可能重发，但已预留调用数不会回退。已提交消息不会丢失或重复发送，未提交的内存动作不对外可见。失败或预算耗尽任务无法再处理的收件消息由系统以 `system_closed` 关闭并在事件审计中留痕，不再永久阻塞完成判定；已完成任务收到迟到消息时保留其评分结果，收件同样由系统关闭。数据库租约防止同一 run 被两个 worker 同时执行；崩溃后等待租约过期，再调用 execute 或 CLI resume。主动取消释放租约。

这是应用级节点快照恢复，不宣称提供 LangGraph 原生 checkpoint 的任意节点 time-travel。后续可以替换存储并增加原生 checkpointer，当前外部工具均为只读或事务内状态修改。

## Railway

保留 `Dockerfile` 和 `railway.toml` 启动入口 `app.main:app`。在 **后端服务** Variables 中引用既有 PostgreSQL 服务的 `DATABASE_URL`；它由 Railway 注入，不需要复制密码到本地 `.env`。同时设置模型配置、`APP_ENV=production`、`EVALUATION_API_TOKEN`。`/health` 为存活检查，`/ready` 检查数据库并报告模型及规则状态。

后端服务的 `DATABASE_URL` 建议使用 Railway 引用 `${{Postgres.DATABASE_URL}}`。部署后打开后端公网地址的 `/ready`，确认 `database.backend` 为 `postgresql`、`database.connected` 为 `true`、`model.configured` 为 `true`；启用 Bucket 时还须确认 `database.bucket.connected` 为 `true`，否则 `/ready` 返回 503。接口不会暴露数据库密码。若 `model.configured` 为 `false`，在后端服务配置 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 或 `GLM_API_KEY` 中的一种。前端会在批量评价前检查模型状态并直接给出配置提示。

### 对话 Bucket

`conversation-files` 的变更先在 Railway 控制台 **Apply/Deploy**。后端服务需要从该 Bucket 引用 `BUCKET`、`ENDPOINT`、`REGION`、`ACCESS_KEY_ID`、`SECRET_ACCESS_KEY`，另设 `BUCKET_ENCRYPTION_KEY`。密钥使用 Fernet 格式，可在可信本机运行 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成，并安全备份；丢失后无法读取已上传对象，不能直接轮换旧密钥。密钥不要发到聊天、写入 Git 或配置到前端。只配部分 Bucket 变量或缺少加密密钥时后端拒绝启动，防止误把对话写回 PostgreSQL 或明文上传。

配置完整时，`team_sessions.payload` 与 `team_runs.payload` 写入小型对象引用；完整会话和运行快照在 Bucket 中加密压缩保存。评价报告及任务、证据和消息审计仍写 PostgreSQL。旧内联记录仍可读。确认 Bucket 可访问并完成数据库备份后，可显式运行 `python -m app.cli migrate-bucket` 迁移旧行；失败会保留原行，命令可重复执行。PostgreSQL 的 UPDATE 不会立即缩小已有卷文件，空间回收需安排数据库维护，切勿在接近 500 MB 容量上直接执行需要额外空间的重写操作。

已整理成 `Session` 结构的每会话 JSON 文件可用 `python -m app.cli import-directory <目录>` 导入，或在前端“服务连接”中设置访问令牌后选择这些 JSON 文件上传；前端单文件上限 2 MB。`data/longest_1000_sessions.json` 是原始平台线程格式，不能直接上传或交给此命令。先按可信订单边界转换并检查隐私。`scripts.prepare_real_samples` 只生成少量测试样本，并不表示已导入全部 921 MiB；仓库当前的私有测试样本也不会随 Docker 构建进入 Railway。Bucket 本身不替代独立备份；Railway 当前 Bucket 不提供服务端加密、对象版本和自动快照，故这里在应用端加密。[Railway Bucket 文档](https://docs.railway.com/storage-buckets)

直接访问后端公网域名时，FastAPI 已托管 `app/web` 前端，浏览器使用同源 `/api`，无需前端地址变量。若单独部署 `frontend/`，先为前端服务创建公网域名，再在**前端服务**配置构建变量 `VITE_API_URL=https://<后端公网域名>`，并在**后端服务**配置 `FRONTEND_ORIGINS=https://<前端公网域名>`。两个值都不带尾部 `/`，前端变量更改后需重新构建部署。`API_PROXY_TARGET` 仅供本地 Vite 开发服务器使用；`VITE_DATA_MODE` 当前未被应用代码读取。

该重构已准备部署配置，未自动发布到 Railway，也未连接生产库执行测试。旧独立 worker 入口已移除；运行与恢复统一通过新 API/CLI。若 Railway 原来还有旧 worker 服务，应停用旧 start command 或改为调用新运行接口。

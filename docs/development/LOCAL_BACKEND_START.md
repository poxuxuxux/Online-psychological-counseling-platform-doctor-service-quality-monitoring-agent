# 本地后端开发与百炼连接

本分支为 `codex/backend-ingestion-qwen`，基于 `chore/railway-smoke-config` 的 `6f82ab1`。代码在本地仓库副本中，尚未提交、推送或部署。

## 已实现范围

- 流式读取顶层 data 数组，每次只保留一个聊天线程。
- 来源命名空间消息 ID、重复消息检查、消息类型/服务通知解析。
- 秒/毫秒时间归一化与 create_time 交叉检查，默认来源时区 Asia/Shanghai，可配置。
- 按明确订单号分组；缺订单号消息保留待确认，不猜测相邻订单归属。
- 首次实际文本回复、明确医患消息对的响应时间工具；系统接诊通知不算人工回复。
- 退诊状态、重复购买边界、未解析媒体和时间冲突标记。
- 百炼 qwen3.5-plus 的异步 OpenAI 兼容 HTTP 适配器，安全错误码、超时及截断检查。
- 本地预览命令只输出聚合计数，不输出会话内容、原始身份或订单号。

当前订单分组只是候选轮次，尚未确认服务结束边界；没有可用结束事件时保持 end_boundary_unconfirmed。首次回复时间只是观察事实，不意味着整个轮次可评分。结构化卡片原始信息保留在源文件，本版仅提取已支持的文本字段，不能当作所有模态都已解析。

当前网页仍走原演示评价链路。QwenProvider 实现既有 LLMProvider.complete 协议，可供后续正式 Runner 注入；设置密钥不会自动将现有网站切成真实评价，也不会自动发送本地咨询记录。

## 安装与验证

在仓库根目录运行（Windows PowerShell）：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
```

本次开发环境已创建 .venv，可直接使用，不必重复创建。

## 本地数据预览

当前真实数据在仓库外的上一级 data 目录中：

```powershell
.\.venv\Scripts\python.exe -m app.cli preview-data "../data/longest_1000_sessions.json" --limit 10
```

`--limit 0` 扫描全部线程。此命令只读本地文件，不调用模型，不保存原文副本。来源时区可通过 `--timezone Asia/Shanghai` 指定。订单字段语义及结束事件映射仍待确认。

## 百炼配置与连接测试

复制 `.env.example` 为 `.env`，在本地编辑：

```dotenv
DASHSCOPE_API_KEY=填写你自己的百炼API密钥
QWEN_MODEL=qwen3.5-plus
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_TIMEOUT_SECONDS=90
QWEN_MAX_TOKENS=4096
```

上面的地址属于北京地域旧域名，官方说明仍可使用。也可用控制台对应的业务空间专属地址；API Key 与地址必须属于同一地域。这里接的是百炼模型 API，不是 Coding Plan 专用接口。密钥只在后端使用，不放入 frontend/VITE 变量。

配置文件不会被 Provider 自动读取，以下命令显式加载 `.env`，只发一条固定的英文合成连接测试，不读取咨询文件，可能产生少量模型调用费用：

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env run -- .\.venv\Scripts\python.exe -m app.cli qwen-smoke
```

成功返回 status=connected、模型名称及 expected_reply 是否为 true。401/403 请检查地域、密钥和模型权限；429 为限流；model_incomplete_response 表示输出没有正常结束。不会静默切换为演示分数。非流式调用显式关闭 enable_thinking，后续可以另行扩展带预算的思考模式。

官方参考（2026-10-14查阅）：
- https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
- https://help.aliyun.com/zh/model-studio/deep-thinking

## 上传方式

建议从此本地分支通过 Git 提交和推送，再创建面向团队选定集成分支的 PR；无需把整个文件夹手动上传覆盖仓库。上传前检查 git diff 和 git status，排除 `.env`、`.venv`、真实数据及本地产物。原始数据保留在仓库外。当前分支以部署分支为基础，不能在未确认集成策略时把它当成仅基于 main 的小改动直接合并。

## 第二批实现与验证状态

百炼固定文字连接测试已成功，实际请求模型为 qwen3.5-plus，返回预期的 OK。没有发送真实咨询数据。第二批新增代码与原有测试合计94项通过；随后第三批扩展至100项，并开始真实Qwen合成会话验收，见下文。

已新增：

- 18项版本化指标目录及8/6/4职责分配，D6.1和D6.2默认纳入所属Agent任务。
- 三个评价Agent并行调用、结构化输出校验、指标集合完整性检查、原文定位及语义核验。
- 本地SQLite保存轮次、不可覆盖的输入快照、任务、规则快照、阶段事件和报告。
- 创建任务时支持Idempotency-Key；重复提交同一请求不产生重复任务。
- 独立worker领取任务；失败状态落库，中断任务显式恢复标记，不自动重复付费调用。
- 独立的带Bearer令牌校验的本地API，原Railway演示服务与前端未切换。

评分锚点尚未配置，因此评价Agent只做行为观察和适用性判断，score必须为null；如果模型擅自返回分数，会判定输出不合格。报告明确标记partial与规则缺失。当前报告是本地开发DTO，不能直接替换前端现有ReportSchema。

## 第三批实现 仲裁与一次定向复评

新增 `app/agents/review.py`，沿用同一Provider完成核验和仲裁，由应用控制派单与采纳：

1. 确定性的引用错误直接生成修复任务；语义分歧进入仲裁Agent。
2. 仲裁只能建议指定争议指标重评或人工复核，不能改分或直接跳过核验。
3. 编排器检查仲裁指标集合完整、无重复、未越界；不合法的裁决转人工复核。
4. 按原Agent归属定向重评，每个指标最多一次；引用修复和仲裁建议共用额度。
5. 复评结果再次定位原文并做语义核验；只有核验支持的新结果才被采纳。
6. 仍有争议或执行失败时保留初评，标记未解决，不循环争论。

报告增加 finding_history、verification_history、arbitration_decisions、re_evaluation_attempts、re_evaluation_failures、unresolved_metrics、adopted_findings。初评与复评用不同finding_id，复评通过supersedes_finding_id关联旧版本，最终checks关联实际采纳的finding_id。

核验超时或结构化输出失败是执行问题，不被伪装成语义分歧；记录安全错误码，转入待复核。单任务总预算600秒，没有自动无限重试。新增6项分支测试，目前共100项测试通过。

真实模型联调中修正了两处输入约束：评价引用要求每条evidence对应单条消息的连续原文，禁止省略号拼接；核验与仲裁只接收本次待处理指标的定义，避免全量18项定义与部分任务范围混淆。对于结构校验失败分别记录schema类型、覆盖范围错误或模型传输错误，不记录包含提示词原文的异常文本。

### 真实模型端到端验收命令

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env run -- .\.venv\Scripts\python.exe -m app.smoke
```

该命令使用服务端固定合成会话，经带认证的API保存轮次、创建持久化任务、实际调用Qwen、读取报告；每次生成独立的本地smoke数据库。根据问题数量最多约9次模型调用。输出仅含任务ID、Agent状态、指标数量和本地数据库位置，不输出密钥。要求三个Agent成功、18项结论、18项最终核验且没有语义核验执行失败；存在需要人工判断的业务争议可以保留。它不代表评分规则或真实数据评估已经完成。

2026-10-15最终真实验收记录：run-d79b2df5-40d8-406b-9cd5-7f0e6f02a9de。三个评价Agent均completed，返回18项结论和18项核验，语义核验执行失败0项，定向复评2项；最终仅D2.1/D2.2仍未解决，其余16项得到核验支持。D2的时间工具结果尚未注入当前结构化评价输入，后续需接通服务事件与时间事实；不能仅凭对话顺序判断响应质量。评分锚点未配置，报告状态仍为partial且无总分。

本地真实数据导入另完成1条聊天线程验证，保存77个候选分组/待归属记录（不代表77次确认咨询），模型调用0次。数据保存在被Git忽略的data/local/import-smoke.sqlite3，未发送外部模型。100项自动化测试与Ruff均通过。

### 本地运行新接口

在本地 `.env` 增加 `LOCAL_API_TOKEN`（自行生成的随机字符串，至少24字符，不能使用百炼API密钥）和可选的 `LOCAL_JOB_DB=data/local/jobs.sqlite3`。本地SQLite仅用于开发，不替代Railway上的PostgreSQL生产仓储。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.local_backend:create_app --factory --env-file .env --host 127.0.0.1 --port 8001
```

请求业务接口时带 `Authorization: Bearer <LOCAL_API_TOKEN>`。API不接收调用方上传任意会话执行模型，合成会话由服务端固定生成。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | /api/v1/rounds/demo | 保存合成示例，返回round_id |
| GET | /api/v1/rounds | 分页查看轮次候选列表 |
| GET | /api/v1/rounds/{round_id} | 查看已授权本地轮次内容 |
| GET | /api/v1/rubrics/indicators-20261010-draft-v1 | 查看18项指标及未配置评分状态 |
| POST | /api/v1/evaluation-runs | JSON提交round_id，另带Idempotency-Key请求头，返回202与run_id |
| GET | /api/v1/evaluation-runs/{run_id} | 查看任务状态和阶段 |
| GET | /api/v1/evaluation-runs/{run_id}/report | 读取报告；尚无报告时返回409 |

创建任务只入队。另开终端，执行一次领取队列中一项任务（三个评价调用、核验及按需仲裁/一次复评，会产生模型费用）：

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env run -- .\.venv\Scripts\python.exe -m app.cli worker-once
```

同一幂等键返回原任务，失败后如需重新运行需显式使用新键。进程异常退出留下running状态时，停止worker后再运行 `python -m app.cli recover-local`，将其标记为interrupted；它不会再次发送模型请求。API与worker必须使用同一个LOCAL_JOB_DB路径。

### 将原始数据保存到本地候选轮次库

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env run -- .\.venv\Scripts\python.exe -m app.cli import-local "../data/longest_1000_sessions.json" --limit 10
```

该操作保留原文到被Git忽略的本地数据库，不做模型调用；本地API可以查看这些记录，但不能对raw_local轮次创建模型任务。真实数据还需完成脱敏、边界核查后另行启用。不要提交或公开该数据库。

## 后续实现

1. 数据边界复核、可靠脱敏、生产PostgreSQL仓储与迁移。
2. 成员交付逐指标评分规则（显式1～5或0～5）；Skill包加载与规则注入已完成，时间事实仍待接通。
3. 确定性评分与完整人工复核闭环；管理、结果Agent和新链路持久化通信池已接入。
4. 人工复核提交及前端异步任务联调。

完整设计另见本地项目根目录的 `design/后端设计与数据接入方案.md`；该文件位于本Git仓库之外。

## 第四批实现 指标Skill交接接口

交接规范见 [指标Skill接口](../contracts/METRIC_SKILL_CONTRACT.md)，机器格式见 [JSON Schema](../contracts/metric-skill-v1.schema.json)。成员按每指标一个目录交付metric.yaml和SKILL.md，样例位于examples/metric_skills/D4.1。

评价、核验、仲裁和复评已使用同一份任务Skill快照。draft与缺失Skill不评分；published要求完整分档，单项分数必须属于其显式量表。不适用和资料不足保持null。人工复核规则ID会校验并写入指标和报告。任务排队后修改规则文件不会改变其执行依据。

GET /api/v1/rubrics/current可读取当前动态规则版本；POST创建任务可省略rubric_version选择当前快照，或显式提供内容版本。完整量表或单包校验使用 `python -m app.cli validate-skills <包根目录>`，完整发布检查加 `--require-complete`。

112项测试通过，包含分制、草稿/发布、未知复核规则、版本快照、结构Schema与实际Agent注入测试；本轮未调用百炼，未部署。成员尚未交付18项正式规则，接口接通不等于指标内容已经定稿。总分汇总仍未实现。

## 第五批实现 管理 结果与共享通信池

设计与接口见 [管理Agent、结果Agent与通信池](../architecture/MANAGER_RESULT_POOL.md)。本地新链路增加管理计划校验、共享情境读取、任务与评价版本持久化、最终采纳记录，以及只基于已核验结论的结果Agent。

新增GET /api/v1/evaluation-runs/{run_id}/communication分页查看通信记录。模型或计划失败会显式降级；总结失败不会覆盖原始评价。旧演示前端与旧内存账本未迁移。此版本真实smoke包含管理和结果调用，最多约11次请求，以本节说明为准。

本轮126项测试和静态检查通过。真实管理Agent与通信池API读取验证通过；完整真实链路因评价请求连接失败未通过，单独结果Agent测试也遇到连接失败。结果Agent代码已接通并通过模拟测试，真实验收仍待网络请求恢复后完成。没有推送或部署。

## 三个业务Tool设计

接口设计见 [三个Tool设计](../architecture/THREE_TOOLS_DESIGN.md)，模型侧请求Schema草案见 [工具请求定义](../contracts/three-tools-v1.functions.json)。时间Tool计算D2间隔；历史Tool仅在可信复诊与授权门控后访问既往片段；证据Tool在三位评价Agent提交初评/复评时强制绑定原文、编号与时间。

此部分目前仅完成设计与请求Schema，尚未实现正式Handler或接入主流程。旧时间函数和原文匹配函数是可复用基础，不等于三个Tool已经实现。工具参数不允许模型填写患者身份、授权、订单起点或消息时间；这些由后端绑定。

## 两个业务Hook设计

设计见 [风险监测与分歧检测Hook](../architecture/TWO_HOOKS_DESIGN.md)，结果接口见 [Hook结果Schema草案](../contracts/two-hooks-v1.results.schema.json)。风险Hook在评价前记录当前患者候选风险表达，通知管理Agent补充D6专项关注；D6两项仍默认执行。分歧Hook只比较已核验的当前有效结论，标记同一事件或相关指标之间的候选冲突，不裁决、不改分。

现有review.py中的“评价与核验意见不一致”分支继续保留，与新增的“已核验结果之间的冲突检测”分开。此轮仅完成设计，通用HookRegistry和现有分歧处理不等于两个正式Hook已实现。

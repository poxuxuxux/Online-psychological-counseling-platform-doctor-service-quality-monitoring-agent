# 指标评价网页联调与 Railway 部署

当前分支保留原有同步演示评价，另新增「指标评价」页面。新页面只允许服务端固定生成的合成咨询轮次，使用同源 `/api/v1/rounds/*` 和 `/api/v1/evaluation-runs/*` 接口。访问码由操作员在页面输入，仅留在页面内存；模型密钥只在 worker 环境变量中。

## 本地闭环

在项目根目录的 `.env` 中配置 `METRIC_RUNS_ACCESS_CODE`（随机 24 字符以上）、`LOCAL_JOB_DB` 和 `DASHSCOPE_API_KEY`。本地无 PostgreSQL 时会用 SQLite。启动网页 API：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

另开终端，以相同 `.env` 启动 worker：

```powershell
python -m dotenv -f .env run -- python -m app.cli worker-forever
```

打开首页「指标评价」，输入访问码后开始评价。页面依次保存合成轮次、创建任务、每 4 秒查询状态，任务完成后读取报告与原文。任务编号保留在当前标签页；刷新后重新输入访问码即可查询。创建任务使用幂等键，不会因为页面轮询重复调用模型。

## Railway

部署前先由团队审查并合并集成分支，让 web 服务和 worker 服务都连接到包含本次改动的同一 Git 分支或提交。现有 web 服务继续使用 `railway.toml`，创建**第二个私有 worker 服务**，在该服务的 Settings 中将 Config File Path 设为 `/railway.worker.toml`，不分配公网域名。两个服务均使用同一个 Railway PostgreSQL 的 `DATABASE_URL`（例如引用 `${{Postgres.DATABASE_URL}}`），并设置 `APP_ENV=production`。web 服务设置 `METRIC_RUNS_ACCESS_CODE`；worker 服务设置 `DASHSCOPE_API_KEY`、`QWEN_MODEL` 和 `QWEN_BASE_URL`。worker 不需要访问码。两个服务必须指向同一个数据库，不要在 Railway 上使用本地 SQLite 文件。

web 启动时创建 `metric_rounds`、`metric_jobs`、`metric_job_events` 和 `metric_communication_records` 表。web 未配置访问码时，新接口返回未启用；部署环境未配置 PostgreSQL 时拒绝启动指标任务，避免网页与 worker 写入不同的临时 SQLite 文件。旧演示接口继续可用。

验收顺序：

1. `/health` 返回 `ok`，`/ready` 显示数据库已连接；`/api/v1/metric-runs/capabilities` 返回 `enabled: true`。
2. 在「指标评价」页面输入访问码并提交一次合成轮次，确认页面显示 `queued`，worker 启动后显示 `running`，最终读取 `partial` 报告。
3. 核对 18 项指标、18 条核验及原文引文。当前所有规则仍为 draft，分数应为空；不应显示正式总分。
4. 刷新页面并重新输入访问码，确认能凭任务编号重新读取报告。再检查旧「评估工作台」的同步演示接口仍可用。

模型调用会产生费用。任务失败不会自动重发；若 worker 在执行中被终止，停止 worker 后由维护者执行 `python -m app.cli recover-local` 将遗留运行状态标为 `interrupted`，再以新任务显式重试。

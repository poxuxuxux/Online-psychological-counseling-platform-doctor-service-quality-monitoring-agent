# 澄心质检前端

面向单平台质检操作员的 Vue 3 + TypeScript 后台。页面依据 `docs/product/PRD_B2B_QUALITY_CONTROL_CONSOLE.md` 和 `docs/architecture/TEAM_DEVELOPMENT_CONTRACT.md` 实现；评价对象为一次订单或咨询轮次，D6.1/D6.2 默认纳入任务，风险 Hook 只提供候选线索。

## 本地运行

需要 Node.js 22+，使用 pnpm 11。进入 `frontend/` 后运行：

```bash
pnpm install
pnpm dev
pnpm build
```

开发模式默认使用**合成演示数据**。登录页的“进入演示工作台”不会校验真实身份，演示复核记录仅存放在当前浏览器会话的内存中，刷新后恢复初始样例。演示任务只复制内置样例报告，不调用模型。页面始终显示“合成数据演示”标识。

复制 `.env.example` 为 `.env.local` 可显式配置数据模式；不要在 `VITE_` 变量中放置任何密钥。

```text
VITE_DATA_MODE=demo
VITE_API_BASE_URL=
```

生产构建默认进入 `api` 模式，不会自动回退到演示数据。当前后端只提供 `/health`，业务接口与单账号登录尚未实现，因此接入前会显示明确的接口错误，而不会展示伪造的业务结果。

## 页面范围

- 登录与单操作员工作台布局；
- 总览、评价任务列表与详情、六维覆盖视图；
- 风险案件列表、当前会话证据定位、复诊历史独立展示、人工复核提交；
- 18 项指标目录、数据接入状态、演示审计记录；
- 加载、空数据、部分完成、证据不足和接口失败状态。

每份报告只对应一次咨询轮次。界面不把历史对话当作本次评分证据，不把风险 Hook 候选当作已确认事实，不展示未经定义的数值总分或医生排名。

## 后端对接

`src/api/service.ts` 是唯一的数据入口，`src/api/demoData.ts` 保存合成样例。真实模式按当前架构文档中的计划调用 `/api/v1/*`：登录、总览、评价任务、案件、指标和审计。最终请求/响应 DTO 尚需由前后端共同确认；尤其要统一任务状态、指标结果、证据引用、历史片段和人工复核决定的字段。前端不直接读取 Excel 列名或后端内部 `AgentInput`。

开发服务器将 `/api` 代理到 `http://127.0.0.1:8000`。若前后端分别部署，使用 `VITE_API_BASE_URL` 指向后端公开地址，并由后端配置受信任的前端来源及 Cookie 策略；身份校验和业务权限始终由后端负责。

## Railway 交接说明

仓库根目录的 `railway.toml` 当前只部署 FastAPI 冒烟环境。前端应由集成负责人在 Railway 建立**独立服务**，其根目录设为 `/frontend`，构建命令为 `pnpm install --frozen-lockfile && pnpm build`，静态服务需把前端路由回退至 `index.html`。生产服务使用 `VITE_DATA_MODE=api`，后端 API 可用后再设置 `VITE_API_BASE_URL`。部署与域名、环境变量及发布分支由团队集成负责人管理；前端分支不修改根目录的部署配置。

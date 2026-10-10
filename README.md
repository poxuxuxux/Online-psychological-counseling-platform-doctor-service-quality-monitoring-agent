# 在线心理咨询平台医生服务质量监测 Agent

面向在线心理咨询平台运营方的 B2B 服务质检与风险线索监测系统。平台操作员导入授权的咨询记录后，后端按质检指标调用多个专职 Agent，生成带消息证据的服务质量评价，并将高风险、证据不足或结论冲突的记录放入人工复核流程。

系统评价医生在会话中可观察到的服务行为，辅助平台扩大质检覆盖、定位问题和追溯依据。系统不对患者作临床诊断，不替代专业人员判断，也不会根据未复核的模型输出自动处罚医生或联系患者。

## Agent 工作流程

```mermaid
flowchart LR
    A[导入授权会话] --> B[校验、规范化、脱敏]
    B --> C[创建质检任务]
    C --> D[加载指标 Skill 和平台规则]
    D --> E[确定性路由与专职 Agent 分析]
    E --> F[结构化结果与证据核验]
    F --> G[分歧处理、评分汇总、风险门控]
    G --> H[报告和待复核案件]
    H --> I[操作员复核并留审计记录]
```

评价维度包括共情回应、专业沟通与服务边界、咨询过程，以及风险信号识别。每项结论应能定位到本次会话消息；上下文不足、证据无效或 Agent 意见冲突时，系统明确保留限制并提示人工核查。

## 产品与技术结构

- **使用对象**：单平台工作空间中的一名平台质检操作员，不包含组织成员、角色或租户管理。
- **后端**：Python 3.11+、FastAPI、Pydantic 数据契约、可替换的 LLM Provider 接口和版本化 Skill。
- **前端**：规划为 Vue 3 + TypeScript 管理后台，按总览、质量监测、风险中心、复核工作台、评价任务、指标管理、数据接入和审计日志划分。
- **系统形态**：比赛 MVP 采用 FastAPI 模块化单体；前端通过版本化 HTTP API 与后端交互。

```text
.
├── app/                    # FastAPI、Agent 编排、评价规则与基础设施适配
├── frontend/               # Vue 3 后台前端目录骨架
├── data/                   # 合成演示数据与本地数据目录
└── docs/
    ├── architecture/       # Agent 与系统架构设计
    └── product/             # 后台 PRD 与后端功能说明
```

## 本地启动

需要 Python 3.11 或更高版本。

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

### macOS / Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

启动后打开 [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)，服务应返回：

```json
{"status":"ok"}
```

`/health` 只检查 FastAPI 进程是否响应，不代表数据库、模型服务或完整评价工作流已经连通。前端目录目前仅含架构说明和目录占位文件，还没有独立安装与启动命令。

## 文档

- [Agent 系统设计文档](docs/architecture/AGENT_SYSTEM_DESIGN.md)：Agent 模块职责、30 步评价流转、数据契约、状态机、API、失败处理和安全设计。
- [B2B 后台架构融合提案](docs/architecture/B2B_ADMIN_CONSOLE_ARCHITECTURE.md)：后台如何融入现有项目结构，以及单操作员 MVP 的边界。
- [后台产品 PRD](docs/product/PRD_B2B_QUALITY_CONTROL_CONSOLE.md)：产品目标、用户、流程、页面、功能需求和验收标准。
- [后端 Agent 功能说明](docs/product/BACKEND_AGENT_FUNCTIONAL_SPEC.md)：后端完整业务能力、评价器职责、证据、风险复核和接口。
- [前端目录骨架说明](frontend/README.md)：Vue 3 前端模块划分和后续工程初始化约定。

## 数据与安全

- 演示优先使用合成会话；未经授权不要导入真实咨询记录。
- 不要提交 `.env`、患者身份信息、数据库文件、私有对话或本地向量索引。
- 评价结论必须与会话证据分开记录平台规则知识；引用无效或证据不足时不应给出确定分数。
- 跨会话患者记忆默认关闭。启用前必须具备授权、匿名映射、访问审计、保留和删除策略。
- 高风险结果是平台内部待核查线索；人工复核和平台处置流程保留最终判断权。

## 工程说明

仓库提供可启动的 FastAPI 服务入口和健康检查，Agent 与评价流程按模块化架构组织。真实模型供应商、持久化数据层和后台页面应在满足平台授权与安全要求后接入；当前的 `/health` 响应不代表完整质检产品已可投入运营。

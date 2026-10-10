# 在线心理咨询平台医生服务质量监测 Agent

仓库现包含整体架构文档和**可运行的项目起步骨架**。骨架目前只提供 FastAPI 健康检查及核心模块接口；多 Agent 真实评价、数据库、模型调用和 RAG 仍需按架构分阶段实现，不能视为已完成系统。

## 本地启动

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/health` 可检查服务。`pytest` 运行基础接口测试。

## 文档与架构图

- [整体架构说明](docs/architecture/ARCHITECTURE.md)：系统分层、运行流程、扩展机制、数据边界、协作与实施计划。
- [B2B 风控与服务质检后台架构融合提案](docs/architecture/B2B_ADMIN_CONSOLE_ARCHITECTURE.md)：前端后台、租户权限、风险案件、人工复核与落地顺序。
- [B2B 质检风控后台 PRD](docs/product/PRD_B2B_QUALITY_CONTROL_CONSOLE.md)：用户角色、核心流程、功能需求和 MVP 验收标准。
- [后端 Agent 功能说明](docs/product/BACKEND_AGENT_FUNCTIONAL_SPEC.md)：会话处理、多 Agent 评价、证据核验、风险复核和 API 职责。
- [前端目录骨架说明](frontend/README.md)：Vue 3 后台前端的模块目录规划；当前仅有占位文件，尚未实现页面。
- [系统模块图](docs/architecture/assets/01_system_architecture.svg)
- [运行时流程图](docs/architecture/assets/02_runtime_workflow.svg)
- [功能扩展图](docs/architecture/assets/03_extension_paths.svg)
- [Memory 与 RAG 图](docs/architecture/assets/04_memory_and_rag_design.svg)
- [Harness 机制映射图](docs/architecture/assets/05_claude_style_harness_mapping.svg)

## 数据安全

不要提交真实患者数据、`.env`、数据库文件或本地向量索引。当前样例指标为待专家审核的占位 Skill；无可信匿名患者映射和授权前，跨会话 Memory 默认关闭。

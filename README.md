# 在线心理咨询平台医生服务质量监测 Agent

本仓库用于设计一套基于真实医患文本互动的、多维度、可追溯医生服务质量评价系统。当前提交提供**整体代码架构与开发约定**，不是已经完成的运行系统；后续实现按一周内可本地演示的范围推进。

## 架构文档

- [整体架构说明](docs/architecture/ARCHITECTURE.md)：系统分层、运行流程、可扩展机制、数据边界、三人协作与一周实施计划。
- 架构图：
  - [系统模块图](docs/architecture/assets/01_system_architecture.svg)
  - [一次评价的运行时流程](docs/architecture/assets/02_runtime_workflow.svg)
  - [功能扩展路径](docs/architecture/assets/03_extension_paths.svg)
  - [Memory 与 RAG 设计](docs/architecture/assets/04_memory_and_rag_design.svg)
  - [参考 Claude Code Harness 的机制映射](docs/architecture/assets/05_claude_style_harness_mapping.svg)

## 设计原则

- 一周版本采用**模块化单体**：FastAPI + SQLite，优先保证可运行、可解释、可演示。
- 评价指标以 Skill 形式管理；Skill 提供指标定义、评分锚点和证据要求，不执行任意代码。
- Agent 复用统一的受控执行循环；工具经注册、权限检查和分发后调用，不允许任意 shell 或文件写入。
- 对话证据、知识库引用、患者背景记忆分开保存和引用；无可靠患者映射时不启用跨会话记忆。
- 当前仓库不包含真实患者数据、密钥或本地向量索引。

## 后续开发入口

开发前先阅读 [架构说明](docs/architecture/ARCHITECTURE.md)，由团队共同冻结接口契约，再按文档中的三人分工和 PR 流程并行实现。

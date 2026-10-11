# GitHub 团队协作与开发分工手册

更新日期：2026-10-11。

适用仓库：`Online-psychological-counseling-platform-doctor-service-quality-monitoring-agent`。

本手册用于两人或三人第一次通过 GitHub 协作开发本项目。目标是让成员在稳定公共契约的前提下并行实现模块，并通过 Pull Request（下文简称 PR）完成评审和集成。业务与技术边界以 [三人协作开发与模块接口约定](../architecture/TEAM_DEVELOPMENT_CONTRACT.md) 为准。

## 1. 先统一四条规则

1. `main` 始终保持可安装、可测试；所有功能从独立分支通过 PR 合入。
2. 一个 Issue 对应一个清晰任务，一个 PR 只解决一个主题。不要把数据导入、Agent、页面和无关格式化放进同一 PR。
3. 公共契约先合并，具体实现后并行。`app/domain/`、API DTO、契约 fixture、`app/bootstrap.py` 属于高冲突区域。
4. 患者原始数据、模型密钥、`.env`、数据库、转写文件和含隐私的日志不能提交到 GitHub。

本项目建议使用 **短生命周期功能分支 + PR + Squash and merge**。团队规模小，不需要 `develop` 分支；增加长期分支只会多一次同步和冲突。

## 2. 仓库管理员第一次配置

### 2.1 邀请成员

仓库所有者在 GitHub 仓库页面依次进入：

`Settings` → `Collaborators`（有些界面显示为 `Collaborators and teams`）→ `Add people`

输入另外两人的 GitHub 用户名或邮箱。对方接受邀请后才拥有协作权限。GitHub 官方步骤见 [Inviting collaborators to a personal repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。

三个人都应开启 GitHub 两步验证，并各自使用自己的账号和提交身份；不要共用账号、Personal Access Token 或 SSH 私钥。

### 2.2 设置合并方式

在 `Settings` → `General` → `Pull Requests` 中：

- 开启 `Allow squash merging`；
- 建议关闭 `Allow merge commits` 和 `Allow rebase merging`，避免第一次协作时出现三种历史风格；
- 开启合并后自动删除分支。

PR 内可以有多次小提交；Squash 合并后，`main` 上每个 PR 只留下一个清楚的提交。

### 2.3 保护 main

先让本仓库新增的 `CI` 工作流中的 `quality` 检查在 GitHub 上至少成功运行一次，再设置规则。进入：

`Settings` → `Branches` → `Add branch protection rule`，Branch name pattern 填 `main`。

建议启用：

- `Require a pull request before merging`；
- `Required approvals: 1`；
- `Dismiss stale pull request approvals when new commits are pushed`；
- `Require status checks to pass before merging`，选择 `quality`；
- `Require conversation resolution before merging`；
- 禁止 force push；
- 禁止删除 `main`。

两人组也建议保留 1 人批准：作者写代码，另一人检查。若比赛当天只有一人在线且规则确实阻塞紧急修复，由仓库管理员临时调整规则，并在 Issue 记录原因；正常开发不要直接推送 `main`。保护分支能强制 PR、评审和状态检查，具体选项见 [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。如果个人账号下的私有仓库因当前 GitHub 套餐不提供保护分支，仍按同一流程人工执行；也可以将仓库转入三人共同的 Organization 后再配置可用规则。

### 2.4 建立第一批 Issues

在 GitHub `Issues` 中按第 9 节的里程碑拆任务。每个 Issue 至少写清：

- 背景和目标；
- 输入、输出与验收条件；
- 负责人和评审人；
- 依赖的 Issue/PR；
- 预计修改的目录；
- 是否改变公共契约。

标签建议只保留少量：`backend`、`agent`、`frontend`、`contract`、`bug`、`blocked`。状态用 GitHub Project 或 Issue 列表统一管理，不在微信群里保存唯一版本的任务状态。

## 3. 每位成员第一次配置本机

### 3.1 克隆仓库

安装 Git 和 Python 3.11+ 后，在 PowerShell 执行：

```powershell
git clone https://github.com/poxuxuxux/Online-psychological-counseling-platform-doctor-service-quality-monitoring-agent.git
cd Online-psychological-counseling-platform-doctor-service-quality-monitoring-agent
git remote -v
git branch --show-current
```

预期远端名为 `origin`，当前分支为 `main`。

### 3.2 设置自己的提交身份

在仓库目录内配置，避免修改共用电脑上其他项目的身份：

```powershell
git config user.name "你的 GitHub 显示名"
git config user.email "你的 GitHub 提交邮箱"
git config --get user.name
git config --get user.email
```

邮箱可使用 GitHub 提供的 `noreply` 地址。每个人都用自己的身份提交，不让一人代替全组提交。

### 3.3 创建 Python 环境

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check app tests
```

若 PowerShell 禁止激活脚本，可以直接运行 `.\.venv\Scripts\python.exe -m pytest`，不需要为了项目修改全局执行策略。

## 4. 每个任务的标准操作

以下流程每个 Issue 重复一次。

### 4.1 从最新 main 创建分支

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/session-segmentation
```

分支名使用小写英文和连字符：

- `feat/session-segmentation`
- `feat/agent-runner`
- `fix/evidence-offset`
- `docs/github-workflow`
- `test/report-contract`

不要使用成员姓名作为分支名。分支表达工作内容，一项工作完成后删除。

### 4.2 开发和提交

开发过程中经常检查：

```powershell
git status
git diff
```

只暂存本次任务的文件，优先写明确路径：

```powershell
git add app/application/segmentation tests/test_segmentation.py
git diff --cached
git commit -m "feat: add consultation round segmenter"
```

提交前最低检查：

```powershell
python -m ruff check app tests
python -m pytest
```

提交信息格式为 `<类型>: <动作>`：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`。一句话说明做了什么，不写“更新代码”“修改一下”。

### 4.3 推送并创建 PR

```powershell
git push -u origin feat/session-segmentation
```

在 GitHub 打开提示中的链接创建 PR：

- Base 选择 `main`；
- 标题说明最终行为；
- 正文按仓库 PR 模板填写；
- 关联 Issue，例如 `Closes #12`；
- 未完成时使用 Draft PR；
- 准备好后请求指定成员评审。

### 4.4 评审和合并

评审人重点检查：

- 是否满足 Issue 验收条件；
- 是否破坏公共契约或越过模块边界；
- 是否把患者数据、密钥或真实对话写入代码、fixture、截图和日志；
- 失败、缺失数据和部分完成是否有明确状态；
- 测试是否验证关键行为，而不是只重复实现；
- CI 是否通过。

作者解决评审意见后再请求复审。批准并且 CI 通过后，使用 `Squash and merge`。Squash 提交标题沿用清楚的 PR 标题。

### 4.5 合并后清理本地分支

```powershell
git switch main
git pull --ff-only origin main
git branch -d feat/session-segmentation
git fetch --prune origin
```

## 5. 开发中同步 main 与解决冲突

一个分支开发超过一天，或依赖的 PR 已合入时，在自己的功能分支执行：

```powershell
git fetch origin
git switch feat/session-segmentation
git merge origin/main
```

若没有冲突，测试后正常 push。若出现冲突：

1. 运行 `git status` 查看冲突文件；
2. 打开文件，处理 `<<<<<<<`、`=======`、`>>>>>>>` 标记，保留最终需要的内容；
3. 对公共契约的冲突，同时找契约负责人确认语义，不能只让编辑器自动选一边；
4. 逐个暂存已解决文件；
5. 提交、测试并 push。

```powershell
git add app/domain/models.py
git commit -m "chore: merge main into session segmentation"
python -m ruff check app tests
python -m pytest
git push
```

如果发现合并方向错了且尚未提交：

```powershell
git merge --abort
```

GitHub 的冲突处理说明见 [Resolving a merge conflict using the command line](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/resolving-a-merge-conflict-using-the-command-line)。初期统一使用 `merge origin/main`；不要对共享分支使用普通 `--force`。熟悉 rebase 后，只能整理自己独占的分支，并且只能用 `--force-with-lease` 更新它。

## 6. 公共契约如何修改

下列内容改变会同时影响多人：

- `app/domain/` 的 Pydantic 模型和枚举；
- Agent 输入输出、指标目录、证据核验结果；
- API 请求/响应 DTO 和错误格式；
- 前后端共享 fixture；
- `app/bootstrap.py` 中的装配方式；
- 数据库迁移和配置项名称。

采用以下顺序：

1. 建立带 `contract` 标签的 Issue，写出字段、状态、兼容性与调用示例；
2. A/B/C 共同评审，集成负责人确认最终方案；
3. 用一个小 PR 只修改契约、兼容导出、fixture 和契约测试；
4. 契约 PR 合入后，各成员从最新 `main` 创建或同步实现分支；
5. 消费者分 PR 接入，不在三个并行 PR 中各自定义同名模型。

增加字段时优先保持兼容。删除字段、改变含义或枚举值时，必须在 Issue 写迁移方式；已保存的报告和指标配置需要保留版本号。

## 7. 模块、分支与交叉评审规则

“负责”表示第一责任人和默认评审人，不表示其他人禁止修改。跨模块改动要在 PR 中 @ 对应负责人。三人版采用“集成部署 + 前端 + 后端”分工；集成负责人不等于替代后端或前端，而是负责把两边的代码接成一条可演示流程。

| 区域 | 默认负责人 | 可以直接修改 | 未经协商不能修改 |
|---|---|---|---|
| `frontend/` | 前端成员 | 页面、组件、样式、API client、前端测试 | 后端模型、数据库、`.github/` |
| `app/` 后端实现 | 后端成员 | API、导入、切分、Agent、评价、仓储和后端测试 | `frontend/` 页面和 Railway 发布设置 |
| `app/domain/`、API DTO、契约 fixture | 集成负责人牵头 | 契约 PR、兼容导出、联调 fixture | 在没有 contract Issue 和消费者评审时改字段 |
| `app/bootstrap.py`、集成测试 | 集成负责人 | 装配、路由注册、Fake 端到端流程 | 直接重写前端或 Agent 具体实现 |
| `.github/`、`Dockerfile`、`railway.toml`、发布文档 | 集成负责人 | CI、容器和部署配置 | 前端/后端成员在功能 PR 中顺手改部署配置 |
| `data/`、`.env`、模型密钥 | 无人提交 | 只使用合成 fixture 和环境变量 | 患者数据、密钥、数据库文件和本地日志 |

分支规则：

- `main` 只接受 PR，三人都不能直接 push；
- `release/railway-demo` 只给 Railway 部署，默认只有集成负责人更新；
- `feat/frontend-*` 只能承载前端工作；
- `feat/backend-*` 只能承载后端和 Agent 工作；
- `chore/contract-*` 只修改公共契约和契约测试；
- Railway 不连接任何 `feat/*` 分支。

如果 GitHub 套餐不能限制 `release/railway-demo` 的写权限，就用团队约定限制：只有集成负责人 push；其他人发现线上问题，提交 PR 到 `main`，不能直接修改发布分支。

`README.md`、架构图和共享配置容易冲突。功能 PR 只更新与该功能直接相关的段落；大范围文档整理单独开 PR。

## 8. 三人版分工：集成部署、前端、后端

### A：集成部署与完整流程负责人

A 的目标是先把一条最小流程跑通，再持续把队友的功能接入线上演示版本。

负责：

- `release/railway-demo` 分支和 Railway 服务；
- Dockerfile、Railway 环境变量、CI、健康检查和部署文档；
- `bootstrap.py`、路由注册、合成端到端 fixture 和集成测试；
- 把前端和后端合并到同一条“导入/选择案例 → 创建任务 → 查看报告”的流程；
- 线上日志、回滚、演示数据重置和比赛版本冻结。

主要目录：`.github/`、`Dockerfile`、`railway.toml`、`app/bootstrap.py`、`tests/integration/`、部署文档。

A 不负责替队友实现全部页面或全部 Agent。A 可以修改公共契约，但必须开 Issue、写迁移说明并让前端和后端都评审。

### B：前端负责人

负责：

- Vue 3 + TypeScript 工程和 API client；
- 任务列表/详情、会话证据定位、六维报告、风险中心和复核工作台；
- 加载、空数据、失败、部分完成、待复核等状态；
- 页面级测试、构建检查和演示交互。

主要目录：`frontend/`。

B 可以读取 API fixture，但不能修改后端评分逻辑、数据库模型或 Railway 配置。需要新增字段时，先开 contract Issue，由 A 组织 B/C 评审。

### C：后端与 Agent 负责人

负责：

- Excel 导入、轮次切分、预处理、上下文和仓储；
- API、任务生命周期和错误 DTO；
- `LLMProvider`、共享 `AgentRunner` 和结构化输出校验；
- 三个专职 Agent、不同提示词/Skill、18 项指标及 8/6/4 归属；
- 证据核验、定向复评、仲裁、评分、门控和总结；
- Fake Provider、后端单元测试和契约测试。

主要目录：`app/api/`、`app/application/`、`app/agents/`、`app/evaluation/`、`app/skills/`、`app/tools/`、`app/infrastructure/`。

C 不修改 `frontend/` 页面，不把 Excel 列名直接暴露给前端，也不为三个 Agent 复制三套 Runner。

### 三人评审关系

| PR 作者 | 默认评审人 | 第二意见的触发条件 |
|---|---|---|
| A | B、C | 改公共契约、数据库或页面 API 时必须两人都看 |
| B | A | 改 API DTO、任务状态或指标展示字段时加 C |
| C | A | 改 API DTO、指标含义或报告字段时加 B |

A 是发布负责人，但不能在没有 B/C 评审的情况下自行改变他们消费的契约。

### 集成分支的更新流程

1. B/C 在各自功能分支完成工作；
2. PR 合入 `main`，CI 通过；
3. A 在本地同步 `main` 到 `release/railway-demo`；
4. A 在 Railway 中观察部署日志和 `/health`；
5. A 运行完整演示流程，发现问题后回到对应功能 Issue；
6. 比赛前冻结 `release/railway-demo`，不再接受普通功能更新。

```powershell
git fetch origin
git switch release/railway-demo
git merge origin/main
git push origin release/railway-demo
```

## 9. 两人版分工

两人版不删除模块，只合并职责，并按阶段控制同时进行的工作量。

### A：平台与数据链路

负责数据导入、轮次切分、预处理、上下文、仓储、任务生命周期、API、`bootstrap.py` 和 CI。A 还负责前端的 API client、任务列表和基础布局，使 B 不必承担全部前端工程。

主要目录：`app/application/`、`app/api/`、`app/infrastructure/importers/`、`app/infrastructure/repositories/`、`app/bootstrap.py`、`frontend/src/api/` 和前端基础框架。

### B：评价链路与报告体验

负责 Provider/Runner、三个专职 Agent、Skill、核验/复评/仲裁、评分/门控/总结，以及报告详情、证据定位和人工复核页面。

主要目录：`app/agents/`、`app/evaluation/`、`app/skills/`、`app/tools/`、`app/infrastructure/llm/`，以及报告和复核相关前端页面。

### 两人协作方式

- A 和 B 互相评审，公共契约必须两人同意；
- A 维护组合根和 API contract，B 维护评价 contract，改变对方输入时先开 contract PR；
- 一个里程碑内，每人最多同时保留一个主要开发 PR，减少无人评审和长期分支；
- 联调问题由发现者建 Issue，模块负责人修复，另一人验证；
- 每完成一个纵向场景再扩展下一项能力，不等所有后端完成后才开始页面。

## 10. 建议实施顺序与首批 Issues

并行开发的前提是输入输出已固定。推荐按下列顺序推进。

### M0：协作与契约基线

1. `contract: define source conversation and segmentation result`
2. `contract: define metric catalog, agent task and per-agent input`
3. `contract: define verification, report and review DTO`
4. `chore: add shared synthetic fixtures and CI`

M0 由全员评审。完成前只做可隔离的调研或原型，不在各分支创造竞争契约。

### M1：最小可贯通骨架

- A：Docker/部署 smoke test → 合成来源导入 → 创建/查询任务 API → Railway 演示环境；
- B：使用固定 fixture 完成任务列表、报告详情、证据定位和复核提交；
- C：Fake Runner → 三个不同 AgentTask → 固定结果 → 核验/汇总/报告。

验收：不使用真实模型和患者数据，也能从合成输入跑出可查看、可复核的报告。

### M2：真实数据适配与 Agent 实现

- A：接入前后端、维护 Railway 演示分支、完成集成测试和线上回滚；
- B：接真实 API，完善进度、失败、部分结果和指标目录驱动展示；
- C：实现 Excel 适配器、可版本化切分策略、Provider/Runner、18 项 Skill、三个专职 Agent 和结构化核验。

验收：脱敏后的本地样例可以完成单轮次评价；三个 Agent 收到各自任务和提示词；D6 始终分配，风险 Hook 只补充线索。

### M3：可信闭环

- 接入一次定向复评、仲裁、评分策略版本、人工门控和总结；
- 持久化运行快照、证据链、复核决定和审计事件；
- 完成错误恢复、重跑和契约兼容测试。

### M4：比赛演示与验收

- 固化三到五个完全合成的端到端场景；
- 演练初诊、复诊、边界不明确、材料不足、风险线索和 Agent 失败；
- 执行完整测试、前端构建和演示流程；
- 冻结比赛版本，只合入阻塞性修复。

## 11. 每日协作节奏

每天用 10 分钟同步三件事：昨天合入了什么、今天要交付什么、被什么阻塞。具体决定回写到 Issue 或 PR，聊天只用于提醒。

推荐限制：

- 每人同时最多一个主要开发 PR；
- PR 尽量控制在可于 20–30 分钟内评完的范围；
- 开发超过两天仍无法合并时，拆出契约或基础部分先合入；
- Draft PR 尽早推送，让其他人看到接口方向；
- 合并公共契约后，其他成员当天同步 `main`。

## 12. 数据与密钥处理

当前患者数据位于仓库外的 `数据/patients`。保持原位，不复制到仓库。开发时通过本地环境变量或未跟踪配置指向它，测试只使用人工合成、不可反推真实个体的 fixture。

提交前运行：

```powershell
git status
git diff --cached
```

重点检查 `.env`、`data/`、日志、截图、Notebook 输出和测试 fixture。`.gitignore` 是最后一道防线，不代替人工检查。

如果密钥已经推送：立即撤销并重建密钥，然后通知仓库管理员处理历史记录。如果患者数据已经推送：停止继续分享和合并，通知全组及仓库管理员，限制仓库访问并清理 Git 历史；仅在最新提交中删除文件并不能从历史中移除数据。清理后所有成员重新克隆，不继续使用旧副本。

## 13. 常见问题速查

### `git pull` 提示本地和远端分叉

先确认自己没有在 `main` 上开发。保存工作后，在功能分支用第 5 节的 `fetch + merge origin/main`。不要直接执行来源不明的 reset 命令。

### push 被拒绝

若是受保护的 `main`，说明应该创建功能分支和 PR。若是自己的功能分支远端有新提交，先确认是否被他人共用，再 fetch/merge；不要直接 force push。

### CI 本地通过、GitHub 失败

打开 PR 的 `Checks` 查看失败步骤，确认 Python 版本、依赖锁定、文件大小写和未提交文件。修复后 push 到原分支，CI 会自动重跑。

### PR 太大，无法评审

暂停继续加功能，把公共契约、纯重构、一个垂直功能和文档拆开。新的 PR 从最新 `main` 创建；不要让多个 PR 依赖一个长期未合并的大分支。

### 两个人修改了同一个公共模型

先暂停其中一个实现 PR，确定一份 contract PR 并合入；两边同步 `main` 后按同一模型继续。不要在两个分支各自保留“临时兼容版本”。

## 14. Definition of Done

一个 Issue 只有同时满足以下条件才算完成：

- 验收条件通过；
- 公共接口和错误状态有类型定义；
- 关键路径有必要测试，现有测试未回归；
- Ruff 和 pytest 通过，前端变更还需通过前端构建/检查；
- 文档或 OpenAPI 与行为一致；
- 没有真实患者数据、密钥或敏感日志；
- 至少一名非作者完成评审；
- PR 已合入 `main`，Issue 已关闭，分支已清理。

# 心衡 Skills 与后端接入说明

更新日期：2026-10-16。

## 本次完成

以用户提供的《后端设计.zip》为基础，在本目录建立独立联调副本。原前端仓库及原压缩包未被覆盖。

- app/skills/metric_packages 下安装全部18项指标包，包含 metric.yaml、SKILL.md、examples.yaml。
- 使用后端现有 catalog / metric_loader 自动加载，无需另造接口。
- 三个评价角色按8/6/4分配规则；评价与证据核验收到同一内容哈希的规则快照，任务与报告保留版本。
- 修正 app/agents/structured.py 的人工复核提示：明确遵循 Skill 中的复核条件，避免草案规则与通用提示冲突。
- 新增20项接入测试，验证完整任务执行、持久化报告、HTTP接口读取与任务入队，以及18项草案拒绝数值评分。
- 旧测试通过 tests/conftest.py 使用独立空规则目录，保留原先“未安装规则”的测试情境；实际交付规则由独立接入测试显式加载。

## 验证结果与范围

全套测试在加入前19项接入测试后：161项通过；随后新增HTTP接入测试，20项接入测试全部通过。改动文件的Ruff检查通过。依赖有一条测试客户端弃用提示，不影响本次结果。

后端 validate-skills 确认 supplied=18、published=0，版本为 indicators-20261010-draft-v1+ccd5030f84fd4321。

验证使用合成会话和模拟模型响应，未调用付费模型API、未发送真实患者数据。上述结果证明工程连接，不证明模型能准确理解规则或具备临床有效性。仲裁与复评沿用后端已有实现及原有回归测试，本次实际18项规则测试重点覆盖评价、核验和保存。

## 如何运行

在此目录打开终端：

```powershell
.venv/Scripts/python.exe -m app.cli validate-skills app/skills/metric_packages
.venv/Scripts/python.exe -m pytest -q
```

默认目录已接好。如果系统原先设置了 METRIC_SKILLS_DIR，须确保它指向本目录的 app/skills/metric_packages，否则会读取其他位置的规则。

真实模型及本地API的启动方式见 docs/development/LOCAL_BACKEND_START.md。原压缩包内的 .env、Git历史和数据库没有复制到此联调副本，需要在本机重新配置后端使用的模型密钥和LOCAL_API_TOKEN；不要把密钥交付或提交到GitHub。

## 当前边界

所有18项仍为draft：单项score与总分保持空值，按规则返回行为观察、证据和复核提示。没有将草案自动改为published。后端总分汇总本身也尚未实现；发布规则并不等于总分功能自动完成。

此目录接入的是后端本地新链路，原线上前端演示链路未切换，GitHub和Railway未更新。下一步在配置好模型后使用合成会话验证实际模型输出，再开展授权样本与专业审定。

## 交给后端同学

配套“心衡_Skills后端接入补丁.zip”只包含18项规则包、改动的评价器文件、两份测试文件及此说明。应在《后端设计.zip》对应版本上合入；如队友后续已改过structured.py，合并提示词改动即可，不应整文件覆盖其新改动。

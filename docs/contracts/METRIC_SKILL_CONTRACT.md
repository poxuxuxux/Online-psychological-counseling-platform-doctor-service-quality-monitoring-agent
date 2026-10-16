# 指标 Skill 接口交接规范

接口版本：1.0。更新日期：2026-10-15。

## 先看结论

指标负责人编写“何时适用、什么原文可作证据、各档分数的条件、何时需要人工复核”。后端加载对应指标Skill，把同一份规则交给评价Agent、证据核验Agent、仲裁Agent和定向复评Agent使用。

Skill是声明式规则包，不是独立运行的Agent，也不需要开发HTTP接口或调用百炼。模型调用、消息定位、输出校验、任务状态、一次复评预算和报告保存由后端负责。总分权重与汇总策略仍由平台统一配置。

已有的旧版 `app/skills/registry.py` / `loader.py` / `packages/empathic_response` 是早期占位接口。本规范对应的新接口是 `app/skills/contracts.py` 与 `app/skills/metric_loader.py`，实际结构化评价链路已接入，不要按旧占位格式交付。

## 交付文件

每项指标一个目录；先交一项即可联调，不需要等18项全部完成。

```text
metric_packages/
  D4.1/
    metric.yaml       必需：机器可读规则
    SKILL.md          必需：执行步骤、语境判断、边界案例解释
    examples.yaml     建议：合成案例和预期结果；当前不自动加载到模型
  D4.2/
    metric.yaml
    SKILL.md
```

后端默认读取 `app/skills/metric_packages`，也可用环境变量 `METRIC_SKILLS_DIR` 指定其他包根目录。目录名不作为指标身份；以metric.yaml中的metric_id为准。不允许重复metric_id，包括同一目录树中放两份不同版本。旧版本由任务快照保存。

交接样例位于 `examples/metric_skills/D4.1`。它是draft，anchors尚未填写，不能当作已定稿的评分标准。成员应填入自己制定的规则，不必照搬样例内容。

## metric.yaml 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| schema_version | 字符串 | 固定写 `"1.0"`，保留引号 |
| metric_id | 字符串 | 固定18项之一，如D4.1 |
| name | 字符串 | 指标名称 |
| version | 字符串 | 如1.0.0、0.1.0-draft；规则变化时升级 |
| status | draft / published | draft只观察，不允许打分；published允许按已完整配置的档位打分 |
| owner | 字符串 | 下面职责表中的Agent ID，不可自行改变分工 |
| definition | 字符串 | 本指标评价的医生服务行为 |
| applicability | 对象 | applicable_when、not_applicable_when、insufficient_context_when三个非空字符串列表 |
| evidence | 对象 | allowed_sources、required_checks、forbidden_uses三个非空列表 |
| score_values | 整数列表 | 明确选择[1,2,3,4,5]或[0,1,2,3,4,5]，不能混用或省略 |
| anchors | 对象列表 | 每项为score整数和criteria文字；published必须覆盖score_values所有分数且不重复 |
| manual_review | 对象列表 | 每项为唯一rule_id和condition文字；至少一条 |
| required_tools | 字符串列表 | evidence_locator、time_calculator；省略时默认只需evidence_locator |

allowed_sources仅允许：current_dialogue（本次对话）、current_intake（本次病情卡）、service_events（本次服务事件）、tool_facts（工具计算的事实）。历史背景不能替代本次医生行为证据。

rule_id用小写字母、数字和下划线，以字母开头，例如context_ambiguous。条件用可操作的文字描述，不是Python表达式。不要把指令写成“根据情况酌情判断”；需要描述什么证据或情境触发规则。

metric.yaml中不能包含本规范未声明的字段，也不能出现重复YAML键。每个必需文件最大256KB。SKILL.md应与结构化字段一致，不得在文档中另定义不同的分制、Agent归属或重评权限。

### 关于1～5和0～5

后端支持两种显式分制。你们若确定采用1～5分，就为相应包声明score_values: [1,2,3,4,5]并提供五档criteria，后端会拒绝0分和小数单项分。若保留0～5分，则必须多提供0分档位。整个量表最后最好统一；混合分制不会被后端自动换算，总分汇总仍未实现。

“不适用”“资料不足”“执行失败”不能写成最低分，使用score: null。即使发布了Skill，缺少必需工具事实也不能打分。目前time_calculator结果尚未注入结构化Agent输入；D2声明此工具后，缺少时间事实会明确阻断评分。

## 固定指标归属

| owner | 指标 |
| --- | --- |
| professional_service | D1.1、D1.2、D3.1、D3.2、D3.3、D3.4、D3.5、D6.2 |
| process_response | D2.1、D2.2、D5.1、D5.2、D5.3、D5.4 |
| empathy_relationship | D4.1、D4.2、D4.3、D6.1 |

D6默认分派任务，再用Skill判断是否适用。风险扫描结果不控制D6任务是否存在。

## 后端如何调用

```python
from pathlib import Path
from app.skills.metric_loader import load_metric_package
from app.skills.catalog import snapshot

package = load_metric_package(Path("examples/metric_skills/D4.1"))
# package = {"spec": {...}, "instructions": "...", "content_hash": "..."}

rubric = snapshot(Path("app/skills/metric_packages"))
# 18项目录 + 已提供Skill内容 + 按内容生成的版本号
```

`StructuredEvaluation(provider, rubric=rubric)`消费该快照。没有Skill的指标保持not_configured，不能打分。提供了但有格式错误的Skill直接报错，不能静默回退旧规则。

入队时保存完整快照，含metric.yaml的解析内容、SKILL.md全文、包内容哈希。执行时使用任务保存的快照，不从磁盘重新读取更新后的Skill；评价、核验、仲裁、复评共享这个版本。更改文字而忘记升级version时，内容哈希仍会变化，但正式交付仍应手动升级版本号。

## Agent输入与输出约定

后端向评价Agent提供：本次会话session、分派给它的metrics（每项内有skill.spec、skill.instructions、skill.content_hash）、可选的revision_requests。当前结构化输入已接本次合成文本会话；病情卡、服务事件和工具事实的标准输入仍待后续接通，Skill不得将未提供的来源视为已存在。

指标成员只交规则包，不需要自行编写模型输出程序。Agent按后端Schema返回：

```json
{
  "metric_id": "D4.1",
  "applicability": "applicable",
  "score": null,
  "rationale": "描述观察到的行为及规则依据",
  "evidence": [{
    "message_ids": ["d1"],
    "quote": "听起来你很担心今晚的睡眠。",
    "explanation": "说明这条原文支持哪项判断"
  }],
  "review_rule_ids": [],
  "requires_manual_review": false,
  "limitations": []
}
```

applicability为applicable、not_applicable或insufficient_context。Finding还会由后端填充finding_id、metric_version、attempt、supersedes_finding_id等追溯字段。每条引用必须来自一条当前消息的连续原文，不用省略号拼接。负向判断需要完整观察范围支持，不能编造“未发生”的原话。

核验Agent读取同一Skill及Finding，返回metric_id、status（supported/unsupported/uncertain）、reason、applicability_status、rubric_status和review_rule_ids。对published Skill，适用性与评分规则两项核验都必须matched才允许维持supported；缺项或不确定转为uncertain。核验Agent不能自行改分。

命中的人工复核规则以rule_id写入review_rule_ids，后端验证这些ID确实存在于对应Skill，设置指标人工复核标记并汇入报告review_rule_hits。除此之外，后端还会因引用错误、模型执行失败、未决争议等系统原因保留人工复核；Skill不能关闭这些系统门控。

人工复核条件属于语义规则，当前由模型判断是否命中；这不是把自然语言条件编译成确定性代码。原文存在性、分数范围、版本和派单范围等结构约束由后端代码强制检查。

## 本地校验与交接步骤

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m app.cli validate-skills examples/metric_skills
.\.venv\Scripts\python.exe -m app.cli validate-skills app/skills/metric_packages --require-complete
```

第一条允许单项draft联调。第二条要求18项全部存在且published；用作完整量表交付检查。此命令只读文件、不调用模型。

1. 成员先照目录结构交付1个指标包。
2. 校验字段和版本，并用合成案例测试适用性、评分档位和人工复核。
3. 确认后继续交付剩余17项；不需要修改后端派单或API。
4. 将正式规则放入app/skills/metric_packages，或配置METRIC_SKILLS_DIR；已生成任务不会受之后修改影响。

机器格式见同目录metric-skill-v1.schema.json；跨字段规则（完整分档、唯一指标、归属等）还须通过Python校验器。JSON Schema校验本身不能替代后端交叉校验。

## 本次范围

已实现Skill契约、包加载、版本快照、评价/核验/仲裁/复评规则注入、单项分数约束和人工复核规则记录。未替成员编写18项正式规则；样例仅用于交接。总分汇总、真实数据完整脱敏和前端展示新增字段不属于本接口已完成范围。

接口及回归测试共112项通过；此轮通过模拟模型验证规则注入与输出约束，没有调用百炼。交接压缩包仅含规范、Schema、契约源码及样例，不是完整后端；校验命令需在本仓库Python环境运行。

# 风险监测与分歧检测 Hook 设计

版本：1.0-design。日期：2026-10-15。状态：接口和流程设计；尚未实现这两个正式Hook或接入主流程。

风险监测Hook在评价前扫描本次对话，定位患者明确表达的候选风险信号，通知管理与情境识别Agent开展针对性评价。分歧检测Hook比较已通过证据核验的有效评价结果，标记同一事件或相关指标间的结论冲突。二者均不评分、不裁决、不自行发布最终结论。

## 1 与既定流程的对齐

沿用用户已确认的流程图：D6.1和D6.2默认进入每轮18项任务，由所属Agent按Skill判断是否适用。风险Hook的“触发专项评价”实现为向这两项任务补充风险事件、证据范围和重点核查要求，不以Hook命中与否决定D6任务是否存在。

| Hook | 触发阶段 | 输出接收者 | 不承担的职责 |
| --- | --- | --- | --- |
| risk_monitor | 本轮规范化、必要转写与脱敏完成后，管理/三个评价Agent执行前 | 管理Agent通过共享通信池读取候选风险事件 | 患者诊断、医生服务质量评分、最终违规认定 |
| disagreement_detector | 证据核验完成后；复评再次核验后只检查受影响的结果关系 | 应用编排器接收冲突候选，按流程交仲裁或复核 | 选择胜方、修改分数、替换结论、无限重评 |

Hook由应用阶段事件自动触发，不是供模型任意调用的Tool。内部可以复用确定性处理或受限模型调用，但其对外职责仍是返回信号/标记；内部模型也不能直接调度其他Agent。

## 2 共同调用契约

建议独立的有类型处理接口：

```text
RiskMonitorHook.run(RiskScanContext) -> RiskScanResult
DisagreementDetectorHook.run(ConflictScanContext) -> ConflictScanResult
```

context由应用注入：run_id、当前round_id、源快照、规则版本、事件版本和调用预算。Hook不得根据模型提供的任意会话ID读取其他数据。结果包含hook_name、hook_version、run_id、round_id、source_snapshot_id、status、issues、结果列表和覆盖统计。

status区分completed、partial、skipped、failed、not_configured。空列表只有在成功检查了明确范围时才表示该范围未发现候选；不能把超时、未配置或材料无法扫描等同于“没有风险/没有分歧”。

现有HookRegistry回调只返回None，适合通知，但不适合承载这两类业务结果。后续需新增类型化执行服务，显式收集返回值并保存结果；通用Registry可以分发完成通知，不能靠回调偷偷修改共享字典来传递信号。

调用去重键建议为：run_id + hook_name + 输入快照/结果版本 + hook规则版本。重复收到同一事件不会重复发任务；输入版本改变时创建新的检查记录，不覆盖旧记录。每次调用有有限超时和额度，不在Hook里无限重试。

## 3 风险监测 Hook

### 3.1 输入范围

仅扫描本次轮次中患者本人表达及必要的邻接上下文。患者提交、来源归属明确的病情卡也可纳入；平台自动通知不能因role=patient就被视为患者自主表达。医生的问题、第三方引用和历史检索片段不能直接作为患者本次风险表达。

输入至少包括当前消息的稳定ID、角色、消息性质、时间、可读文本、文本版本、来源位置及材料完整性。已转写媒体可以扫描转写文本，并保留转写来源；未转写、归属不明或缺失内容进入覆盖缺口，不能假设无信号。

### 3.2 检测步骤

1. 按真实消息性质识别候选患者文本，建立明确的扫描范围。
2. 依据版本化信号规则检索候选语句，再检查邻接上下文。
3. 处理否定、引用、第三人称、过去经历及时间范围；不能仅看到关键词就断言为患者当前信号。
4. 对满足规则的明确表达创建risk candidate，逐字绑定原句、消息ID、角色、时间和来源。
5. 无法可靠判断语义归属或时间范围时，保留uncertain情况和理由，不强行产生确定性命中。
6. 将候选信号及扫描覆盖情况返回应用，由应用写入通信池并通知管理Agent。

具体风险词表、语境判断条件与类别定义是独立版本化规则，不在本设计中假定为已经验证的临床标准。Hook不输出临床风险等级或诊断，也不由模型自行增加风险类别。

证据绑定可复用evidence_locator的定位服务；应用以受控risk_monitor上下文执行，只允许读取本次患者来源内容。缺失时间可保留已定位文本并标注问题，不能伪造时间。未定位到原文的模型判断不能作为明确候选信号发出。

### 3.3 返回内容

RiskScanResult包含：

- scan_outcome：detected、not_detected、uncertain或unavailable。
- signals：候选ID、规则ID/版本、信号类型、逐字证据绑定、上下文消息引用、建议关注指标。
- scanned_message_count、unscannable_message_count：由应用统计，不由模型随意填写。
- uncertainty_refs与issues：未解析媒体、文本缺失或语义不确定等缺口。

每个signal的status固定为candidate。建议关注指标仅为D6.1/D6.2，仍需评价Agent判断各指标是否适用，不能因为Hook命中就预先判定两项应低分。

示例（字段示意，不是真实咨询）：

```json
{
  "hook_name": "risk_monitor",
  "status": "completed",
  "scan_outcome": "detected",
  "signals": [{
    "candidate_id": "risk-candidate-001",
    "status": "candidate",
    "rule_id": "configured-signal-rule",
    "rule_version": "1.0.0",
    "signal_type": "configured-signal-type",
    "evidence_refs": ["evidence-current-patient-001"],
    "context_message_ids": ["current-patient-001"],
    "target_metric_ids": ["D6.1", "D6.2"]
  }]
}
```

该示例只列出关键字段；完整字段约束见结果Schema草案，evidence_refs必须能在通信池解析到原句、编号、时间、角色、来源和文本版本，不能只有一个不可解析的ID。

### 3.4 通知与专项任务

应用保存risk_scan和risk_signal记录，发布risk.signal.detected。管理Agent读取signals，在候选计划中为已有D6任务添加focus_event_ids、risk_candidate_ids和evidence_refs；确定性路由器继续检查D6.1归属empathy_relationship、D6.2归属professional_service。

同一规则对同一原句重复命中要去重；一个轮次有多个信号时合并到对应D6任务的关注列表，不重复生成多个D6评分项。风险任务不能由Hook直接写成已完成或已低分。

未命中时保留D6默认任务；Hook失败时同样保留D6，报告明确risk_scan_unavailable并按复核策略处理。风险提示是平台内部的待关注线索，不自动触发外部联系或处罚。

## 4 分歧检测 Hook

### 4.1 输入门槛与当前实现的区别

只比较同一轮次、同一规则快照下的当前有效Finding版本及其已通过的核验记录。先按finding_id确认核验对应的是该版本，核查原文定位、语义支持、适用性以及涉及评分时的评分规则状态；存在针对该事实的未决核验问题则不进入可比较集合。

旧版被supersedes关系替代的Finding不与新版作为两个独立评价互相比较。历史咨询和其他轮次结果不混入；规则版本不同则返回comparison_ineligible，不擅自换算或对比。

当前review.py里将unsupported/uncertain核验意见送往修正或仲裁，属于“评价与核验意见不一致”的处理分支，不等于本Hook。该分支应保留；本Hook新增的是“已核验结果之间的冲突检测”，两类问题在记录和报告中分别标注。

### 4.2 比较单位

为Finding补充event_refs、claim_refs及适用的观察范围。比较的是可核验的主张，不是笼统比较两段理由或两个分数。主张可复用现有FactClaim结构，至少标明：主体角色、行为、对象/诉求、时间/事件范围、肯定或否定、限定条件及证据引用。

管理Agent的事件仅是候选关联。检测前需确认Finding实际涉及的消息和范围，不能因为管理Agent给了相同event_id就断言是同一事实。关联不足时返回uncertain_pair。

相关指标关系由独立版本化conflict_rules配置，例如同一核心诉求是否被回应的事实，会同时出现在实质服务与诉求回应等判断中。该配置不重复定义Skill评分标准，也不要求当前Skill作者擅自增加接口未支持的字段。

### 4.3 检测步骤

1. 筛选已核验、当前有效的结果，列出被排除的结果及原因。
2. 根据同一事件/主张对象或相关指标关系构造候选结果对，记录比较覆盖范围。
3. 优先使用结构化主张和规则检测相互排斥的断言；必要时以受限语义检查辅助识别候选冲突。
4. 比较前核对主体、对象、时间、适用条件和材料范围，排除由于范围不同形成的表面差异。
5. 返回candidate_conflict、compatible或uncertain。前者记录为ConflictCandidate，后者保留uncertain_pairs而非强行判冲突。
6. 返回标记给应用；Hook不决定谁正确、不改分、不自行发重评任务。

| 情况 | 处理 |
| --- | --- |
| 同一事件、同一诉求，一项断言已回应，另一项断言未回应，且限定条件一致 | 标记候选事实冲突 |
| D2回应及时，但D4共情不足 | 可同时成立，不因分数不同标冲突 |
| D3解释清晰，但D5建议不够个体化 | 可同时成立，不自动标冲突 |
| 两项引用相同语句，但评价不同服务特征 | 仅共享证据不是冲突 |
| 初评结论被一次复评替代 | 使用有效版本比较，旧版本只留追溯 |
| 一项核验supported，另一项unsupported | 不进入本Hook的有效比较；后者走既有核验修正分支 |
| 相同指标名，但来自不同咨询或不同规则版本 | 不直接比较，明确范围不符 |

因此当前的Check.status=supported只是必要条件之一，不能代替完整的版本、范围、适用性和证据检查。无配置评分锚点的指标可以比较已核验的行为事实，但不能比较不存在或不可靠的分数。

### 4.4 输出与后续处理

ConflictScanResult包含eligible_finding_count、compared_pair_count、conflicts、uncertain_pairs、excluded_findings和issues。

每个ConflictCandidate包含conflict_id、两个finding_id、相关metric_ids、event_refs、两条claim_ref、evidence_refs、冲突理由、规则ID/版本，status固定为candidate。不能包含winner、final_score、adopted_finding等裁决字段。

冲突去重键绑定run_id、有效finding版本、claim_refs及规则版本。同一输入重复触发不重复创建冲突或任务；复评产生新版本时形成新检测记录，并关联旧冲突，不能覆盖其历史。

应用将候选冲突写入共享通信池，再按已确认流程交给分歧仲裁Agent。仲裁提出裁决/重评建议，编排器检查归属、范围及每指标一次重评额度，再调用原评价Agent。复评经证据核验后，只重查受影响的结果对。额度耗尽仍未解决时转人工复核，不由Hook自行循环。

旧冲突是否解决由应用依据新核验结果和仲裁决定记录；Hook可以报告新版结果对未再检测到候选冲突，但不独立关闭人工案件。

## 5 共享通信池与失败处理

建议新增hook_run、hook_result、risk_signal和conflict_detection记录种类，保留run_id、hook版本、规则版本、输入快照/结果版本、源引用、覆盖计数、去重键和状态。需要关注的原句放在受控证据记录中，普通日志只存引用与安全错误码。

| 状态 | 应用行为 |
| --- | --- |
| 风险扫描completed且无信号 | 记录已检查范围；D6默认任务继续执行，不宣布患者无风险 |
| 风险扫描partial/failed/not_configured | 显式记录覆盖缺口或不可用；D6继续，复核门控按策略处理 |
| 分歧检查completed且无冲突 | 只说明在本次有效比较范围内未发现候选冲突 |
| 没有可比较结果对 | skipped/no_eligible_pairs，不写成全部评价一致 |
| 分歧检测partial/failed/not_configured | 不能宣称所有结果一致；保留个别核验结论，报告标记检查缺口并进入复核 |

Hook失败不抹掉已完成的评价，也不能被通用回调错误吞掉。涉及一致性检查缺失时，不发布“全部确认”的汇总结论；总结Agent不能用固定文字掩盖检测不可用。

## 6 与现有代码的接入计划

| 模块 | 后续改动 |
| --- | --- |
| application/hooks/registry.py | 保留通知分发；增加类型化业务Hook执行与结果收集 |
| 新risk_monitor.py | 当前患者文本筛选、候选检测、上下文校验、原文绑定与去重 |
| 新disagreement_detector.py | 有效Finding筛选、比较对构建、结构化/语义冲突标记 |
| management.py | 接收risk_candidates与扫描状态；把专项关注关联到既有D6任务 |
| structured.py | 在管理前触发风险Hook，在核验后触发分歧Hook，显式处理失败 |
| review.py | 保留核验修正分支，增加已核验结果冲突的仲裁入口与增量重查 |
| communication.py/local_jobs.py | 保存Hook执行、候选信号、冲突和版本关系 |
| 结果与复核门控 | 区分未发现、未检查、检查失败；保留未决事项，不新增评分 |

风险规则、指标关系规则与指标Skill分别版本化，运行时固定同一任务的规则快照。Hook不能改写已有Skill、扩大历史访问范围或增加重评额度。

## 7 验收清单

1. 风险扫描发生在管理和评价前；仅本次患者来源内容进入命中判断。
2. 系统通知、医生提问、引用、否定及过去经历不因关键词出现被直接当作当前明确命中。
3. 每个明确候选都能定位原句、消息、时间与来源；未解析内容计入覆盖缺口。
4. 风险未命中、扫描失败与未配置都不移除D6默认任务；多次命中不产生重复评分项。
5. 管理Agent收到信号但不能据此预先判定医生低质量或两项D6必然适用。
6. 分歧Hook只比较当前有效且通过相应核验门槛的版本，排除历史、其他轮次和失效版本。
7. 同一事件的互斥主张可被标记；及时性与共情、清晰性与个体化的差异不被误报为冲突。
8. 返回值只有候选冲突与理由，不包含胜方、改分或最终采纳决定。
9. 相同事件重复投递不会重复派单；复评后只重查受影响关系；一次额度不被Hook重置。
10. 无可比结果、扫描失败、部分覆盖与明确未发现分别显示，原始记录和规则版本可追溯。

结果Schema草案见 `docs/contracts/two-hooks-v1.results.schema.json`。本轮只完成设计，未实现检测规则、未调用模型或检索咨询数据，也未改变现有运行链路。

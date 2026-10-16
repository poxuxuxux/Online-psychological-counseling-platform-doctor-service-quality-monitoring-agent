# 时间计算 历史检索与证据定位 Tool 设计

版本：1.0-design。日期：2026-10-15。状态：接口与接入设计，尚未实现这三个正式Handler或接通Agent主流程。

本设计遵循项目确认的职责：时间Tool计算D2两个响应间隔；历史Tool仅在复诊时提取相关既往片段并保留日期与来源；证据Tool在三个评价Agent提交判断时绑定本次对话编号、逐字原文及时间。三个Tool都不打分、不做临床判断、不替代证据核验Agent。

## 1 工具边界与调用位置

| 名称 | 业务作用 | 调用身份与时点 |
| --- | --- | --- |
| time_calculator | D2.1首次响应、D2.2交互响应的确定性时间计算 | process_response评价阶段；evidence_verification可重算 |
| history_retrieval | 复诊历史背景检索，不读旧分数 | application在历史访问策略/上下文构建阶段调用；manager可提出一次补充检索请求 |
| evidence_locator | 绑定当前判断的消息、原句、角色、时间和来源位置 | 三个评价Agent提交初评/复评时强制执行；核验Agent可以再次定位 |

application是受控应用服务身份，不是模型可以声明的角色。allowed_agents由后端注册，不能从模型arguments读取。结果Agent使用已核验、已绑定的结果，不重新检索或定位；仲裁使用既有证据，必要时通过编排器请求补充定位。

风险监测Hook也可由受控应用复用证据定位服务：上下文绑定origin_kind=risk_candidate和候选ID，只能定位本次患者来源文本。该身份和来源由应用设置，不开放给模型填写；不改变三个评价Agent提交时必须定位的规则。

固定流程：

```text
规范化与轮次切分
  → 可信初复诊标记 + 历史访问策略
  → 仅复诊时调用 history_retrieval
  → 构造 current_round / historical_background 分区上下文
  → 管理Agent识别情境、提出任务（可提出补充历史请求）
  → 三个评价Agent
      → 过程响应Agent提出需回应的问题与回复配对
      → time_calculator返回时间事实，过程响应Agent据Skill完成判断
      → 三个Agent返回DraftFinding
      → evidence_locator逐项绑定引用后，形成已定位的Finding
  → 共享通信池保存Tool调用、时间事实、证据绑定和Finding
  → 证据核验Agent按同一Skill检查证据是否支持结论
  → 分歧处置/复评再次经过相同Tool与绑定步骤
```

“提交时调用”是后端必须执行的提交门槛，不能让模型绕过。第一版由编排器通过ToolDispatcher执行注册的Handler，模型只提出参数与引用候选；不必先实现任意多轮function-calling循环。未来即使模型发起原生tool_call，仍经过同一Dispatcher和权限检查。

## 2 共同接口与可信上下文

调用签名草案：`dispatch(context: ToolCallContext, tool_name: str, arguments: dict) -> ToolResult`。

ToolCallContext由应用注入：run_id、task_id、caller_agent_id、current_round_id、source_snapshot_id、rule_snapshot_ref、可信consultation_round、受控patient_link_ref、授权策略和历史截止时间。身份、患者关联、时间戳、访问范围都不进入模型可编辑的工具参数。

统一返回外壳：

```json
{
  "tool_call_id": "tool-call-001",
  "tool_name": "time_calculator",
  "tool_version": "1.0.0",
  "status": "completed",
  "data": {},
  "issues": [],
  "source_snapshot_id": "snapshot-current-001"
}
```

status含义：completed（完成计算/检索/绑定）、partial（有有效部分但存在缺口）、skipped（策略不满足而未访问数据）、denied（越权请求）、failed（工具或数据处理失败）。completed只表示工具动作完成，不表示指标服务质量好，也不表示引用支持结论。

ToolSpec需要增加输入/输出Schema、工具版本、超时预算和白名单。Dispatcher校验参数、执行权限及返回结构，写入tool_call/tool_result通信记录。调用失败只记录安全错误码，不能把包含身份、密钥或原始异常正文的内容写入通用日志。具体超时和调用额度由应用配置，不能由Skill或模型提高。

## 3 时间计算 Tool

### 3.1 输入与事实来源

首次响应请求：`{"metric_id":"D2.1"}`。起点和首次医生回复由工具在当前订单/轮次快照内查找，模型不能指定一个更有利的起点或跳过更早的回复。

交互响应请求：

```json
{
  "metric_id": "D2.2",
  "question_message_ids": ["current-p1", "current-p2"],
  "reply_message_id": "current-d1"
}
```

question_message_ids表示同一待回应单元的患者连续补充；reply_message_id是过程响应Agent提出的对应医生回复，可以为null表示尚无明确配对。语义上的“这条回复回应了哪个问题”由Agent提出并由后续核验检查，Tool只校验角色、范围、时间顺序并计算间隔，不能因为时间相邻就宣布回应充分。

时间来自订单表/服务事件和消息快照。预处理保留原时间、来源时区、秒/毫秒单位与规范化UTC时间。时区/单位/两个来源冲突未解决时，不使用猜测时间计算。结果保留采用的起点依据与策略版本。

### 3.2 D2.1首次响应

公式：首次医生实际回复时间－订单进入咨询阶段的时间。

起点优先使用已映射、含业务语义的订单consultation_started_at。若只有“已购买图文问诊服务”通知，可在配置明确允许时计算代理间隔，并标记basis=purchase_notification_proxy、quality=proxy；不能静默把它当成权威订单字段。缺少起点时为partial且duration_seconds=null。

首次实际回复必须属于同一订单/确认轮次，且确为医生发送的对话消息。等待接诊、已接诊、退诊通知不算回复；“你好”可算一次实际响应，但是否构成实质服务另由D1.1判断。

文本、语音、图片等真实医生消息，只要发送行为和类型可可靠确认，都可用于首次响应计时，不需要先理解内容。若更早的消息无法区分真人回复还是自动通知，不能跳过它，把较晚文本声称为首次回复；返回不确定状态。

### 3.3 D2.2交互响应

默认从同一待回应单元最早一条需要回应的患者消息开始，到所配对的医生回复结束。同时保存最后补充时间，便于核验。不能因患者补发一句话就重置等待时间。不同问题分别记录；一条医生回复可以关联多个问题，但不能人为合并独立问题。

无对应回复时返回duration_seconds=null和no_matched_reply，不填0或无限大。是否属于“没有回复”需要完整观察窗口、服务状态与语义判断；被截断记录只能说未观察到回复。

### 3.4 返回数据

data包含metric_id、response_unit_id、start/end的事件或消息引用、时间、role、basis、duration_seconds、quality、pairing_basis、service_state与policy_version。

```json
{
  "metric_id": "D2.1",
  "start": {"ref": "purchase-event-a", "timestamp": "2024-05-29T12:50:39+08:00"},
  "end": {"message_id": "doctor-reply-a", "timestamp": "2024-05-29T13:41:24+08:00"},
  "duration_seconds": 3045,
  "basis": "purchase_notification_proxy",
  "quality": "proxy",
  "policy_version": "response-time-v1"
}
```

常见缺口：missing_order_start、timestamp_conflict、ambiguous_first_reply、no_matched_reply、cross_round_reference、invalid_speaker、reply_before_question、withdrawn_order。退诊后回复可保留原始时间差，但必须标注服务状态异常，不据此直接给D2分数。默认计算实际经过时间，不擅自扣除夜间、周末或节假日。

工具只产生秒数等事实。是否及时、达到几分，由D2 Skill决定。评分阈值缺失时可以展示时间，不能凭模型常识补造分档。

## 4 历史检索 Tool

### 4.1 先执行门控

必须同时满足：可信元数据标记follow_up、有可靠患者关联、当前任务获准读取该范围的历史。

- initial：编排器不调用，记录skipped/not_follow_up；若收到误调用，Handler防御性返回skipped，不访问仓储。
- unknown：不能用聊天语气猜测为复诊，返回skipped/visit_type_unknown。
- patient_link_ref缺失：返回skipped/patient_link_unavailable，不按姓名、年龄或相似症状串联患者。
- 无授权或请求超出范围：返回denied，不泄露是否存在其他患者记录。
- follow_up已授权但查不到：返回completed、fragments=[]，不能与检索服务失败混淆。

初次历史查询由应用在上下文构建前按本次诉求形成检索词。管理Agent可提出补充query，但不能修改患者、时间范围、授权或允许的医生关联范围。新医生是否可读取同一患者在其他医生处的历史，由平台策略决定，不默认跨医生开放。

### 4.2 请求与返回

请求：`{"query":"近期睡眠变化与此前沟通的记录计划","top_k":3}`。top_k建议默认3、上限8；总返回字符预算由服务端配置。模型不传patient_id、数据库查询语句或任意会话ID集合。

只检索当前轮次开始之前、在当前授权范围内的历史片段。先按患者关联、时间和授权过滤，再做相关性排序，不能先全库相似检索再检查权限。第一版可用受控文本检索，不要求立即建设向量数据库；检索适配器保留替换接口。

当前轮次起点无法确认时，返回skipped/history_cutoff_unavailable，不猜测历史边界。缺少日期或来源的历史片段不进入模型上下文，记录被排除数量与原因；历史文本也应使用获准的脱敏版本。

每个fragment必须包含fragment_id、历史round_id、source_ref、consultation_date、message_refs、role、消息时间、原文片段、命中依据和retrieval_version。日期表示片段所属咨询日期，不用报告生成日期替代。返回跨消息片段时逐条保留编号和时间，不拼接为伪造原句。

示例：

```json
{
  "fragments": [{
    "fragment_id": "history-fragment-1",
    "round_id": "historical-round-1",
    "source_ref": "authorized-history-source-1",
    "consultation_date": "2024-05-20",
    "messages": [{
      "message_id": "historical-message-1",
      "role": "doctor",
      "timestamp": "2024-05-20T10:00:00+08:00",
      "text": "请记录这一周的睡眠时间。"
    }],
    "match_reason": "与本次询问的睡眠记录计划相关",
    "usage": "background_only"
  }],
  "retrieval_version": "history-v1",
  "truncated": false
}
```

检索仓储只读取既往原始消息及必要来源元数据，不读取旧评分、历史Finding、旧结论或总结报告。返回DTO不包含score等字段。上下文明确分区：current_round与historical_background。历史内容可以帮助理解背景，不能作为本次医生服务行为的直接评分证据，也不能直接把旧分数带入本次汇总。

## 5 证据定位 Tool

### 5.1 提交阶段强制执行

三个评价Agent先提交DraftFinding，含指标判断及候选引用。应用生成draft_finding_id，注入当前任务上下文并调用evidence_locator。Tool确认引用后，后端填写不可由模型伪造的证据元数据，再把Finding和证据绑定记录写入通信池。

复评也必须重新绑定，创建新证据引用；不得覆盖初评引用。核验Agent随后使用同一指标Skill检查适用性、证据支撑、评分档位和人工复核条件。定位成功只证明“这段话存在”，不证明“结论正确”。

请求：

```json
{
  "items": [{
    "message_id": "current-doctor-message-1",
    "quote": "通常几点入睡，夜里会醒几次？"
  }]
}
```

模型不提供role、timestamp、source_ref或历史消息内容，这些全部从当前冻结快照读取。界面中的[281]等序号仅供展示，不能作为跨会话唯一ID；持久引用使用后端生成的稳定message_id，同时保留display_sequence。

### 5.2 逐字定位规则

1. 每个item只对应一条当前消息；禁止用省略号拼接不同消息。
2. 优先精确匹配连续原文；允许的空白/全半角规范化需有版本和原字符偏移映射，返回的quote仍是原文，不是规范化后重写的句子。
3. 同一消息中有多个相同片段时返回ambiguous及候选位置，或要求start_offset明确指定；不能擅自选定一个语境位置。
4. 改写、近义词替换、历史消息或不属于当前轮次的ID不得绑定成功。
5. 缺时间时可完成文字定位，timestamp=null并返回missing_timestamp；非时间指标是否仍可评价由Skill决定，不能编造时间，也不必把所有文字证据一律作废。
6. 媒体证据使用带来源的转写片段及媒体偏移；未转写内容不能凭图片/音频URL生成原句。

原句是当前模型可见文本版本中的逐字内容。使用脱敏文本时同时保留text_version与受控原始记录映射，不能把未脱敏身份信息自动返给模型。原始未脱敏内容仅通过后台授权查看。offset采用Unicode code point，start包含、end不包含；前端如用UTF-16索引需转换。

### 5.3 返回绑定结果

```json
{
  "bindings": [{
    "evidence_id": "evidence-001",
    "round_id": "current-round",
    "message_id": "current-doctor-message-1",
    "display_sequence": 12,
    "role": "doctor",
    "timestamp": "2024-05-29T13:41:24+08:00",
    "quote": "通常几点入睡，夜里会醒几次？",
    "source_ref": "current-message-source-1",
    "text_version": "redacted-text-v1",
    "match_status": "matched",
    "span": {"start": 0, "end": 14, "unit": "unicode_code_point"}
  }],
  "item_issues": []
}
```

上例只示意字段；真实offset必须由工具按真实原文计算。部分引用错误时，保留成功项并逐项返回错误，整体partial；引用错误不能静默消失，后续核验必须看到缺口。空items拒绝请求，不能被当成“全部引用有效”。

“医生没有做某事”不能绑定一条不存在的原句。这类判断还需保存观察范围、轮次完整性及相关上下文引用，交由核验Agent判断；不能仅凭未检索到一句话就证明行为缺失。时间计算事实则绑定tool_call_id和起止消息/事件引用，不伪装成医生说过的原话。

## 6 与现有代码和Skill的对接

| 现有模块 | 后续实现方式 |
| --- | --- |
| preprocessing/rounds.py | 复用时间差计算，补充权威订单起点、非文本真实响应、数据质量与服务状态规则 |
| evaluation/evidence_verifier.py | 复用原文匹配基础；增加精确位置和来源返回，移到提交前定位；语义核验仍独立 |
| tools/registry.py、dispatcher.py | 注册恰好三个业务Tool，增加Schema、可信上下文、权限及返回校验 |
| structured.py | D2分两步调用；三Agent提交前强制证据绑定，再进入verify/review_once |
| management.py | 只提出历史补充需求，无法绕过follow_up与授权门控 |
| communication.py、local_jobs.py | 新增tool_call、tool_result、evidence_binding种类，保存参数引用、结果快照和关联关系 |

Skill中现有required_tools的evidence_locator/time_calculator名称沿用。历史检索由全局访问策略控制，不能由某个Skill通过声明工具需求而绕过授权。Skill负责评分标准和证据要求；Tool负责可复现事实，不把语义标准写死在计算函数里。

历史仓储与当前轮次仓储分别通过端口访问，禁止Handler直接拼接用户SQL或读取模型指定路径。缓存键至少包含工具版本、输入引用、源快照版本和相关策略版本；历史缓存还要包含授权范围，权限变化后不能沿用旧授权结果。

## 7 实现顺序与验收案例

实现顺序：统一Tool上下文/Dispatcher → evidence_locator与提交门槛 → time_calculator与D2事实注入 → history_retrieval门控和仓储 → 三Tool的通信池记录与API展示。

关键验收：

- 接诊通知不计实际回复；真实语音消息的首次响应时间可计算；类型不明时不跳过。
- D2.1正确使用订单起点；代理通知单独标识；D2.2患者补充不重置起点。
- 缺时间、时间倒序、跨订单、退诊后回复和被截断会话不产生伪造的0分或0秒。
- 初诊/unknown不访问历史仓储；无可信关联或权限时拒绝；未来消息和当前轮次不进入历史。
- 历史片段均含日期与来源，历史分数、Finding和旧报告不出现在结果中。
- 三个Agent的初评和复评均经过定位；返回原句、编号、角色、时间、偏移和快照版本。
- 历史引用、拼接引文、多处命中、空引用、时间缺失都返回明确状态。
- Tool定位通过但结论不被证据支持时，核验Agent仍能拒绝，不直接计分。
- 所有Tool调用按run隔离、可追溯，伪造调用身份或修改时间戳不能改变结果。

请求Schema草案见 `docs/contracts/three-tools-v1.functions.json`，仅定义模型可提出的参数，隐藏的可信上下文不在其中。这一轮没有修改运行时Handler、没有调用百炼、没有发送或重新导入咨询数据；功能实现仍需下一阶段完成。

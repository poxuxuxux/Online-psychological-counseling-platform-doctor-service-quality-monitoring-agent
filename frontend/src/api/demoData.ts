import type {
  AuditEvent,
  DashboardData,
  EvaluationRun,
  Message,
  MetricDefinition,
  MetricResult,
  ReviewCase,
} from '../types/domain'

export const metricCatalog: MetricDefinition[] = [
  { id: 'D1.1', name: '实质性服务履行', dimension: 'D1 服务可靠性', owner: '专业服务评价 Agent' },
  { id: 'D1.2', name: '服务内容一致性', dimension: 'D1 服务可靠性', owner: '专业服务评价 Agent' },
  { id: 'D2.1', name: '首次响应及时性', dimension: 'D2 服务响应性', owner: '过程与响应评价 Agent' },
  { id: 'D2.2', name: '交互响应及时性', dimension: 'D2 服务响应性', owner: '过程与响应评价 Agent' },
  { id: 'D3.1', name: '症状信息探询', dimension: 'D3 专业信息沟通', owner: '专业服务评价 Agent' },
  { id: 'D3.2', name: '病史与治疗信息核对', dimension: 'D3 专业信息沟通', owner: '专业服务评价 Agent' },
  { id: 'D3.3', name: '心理社会背景探询', dimension: 'D3 专业信息沟通', owner: '专业服务评价 Agent' },
  { id: 'D3.4', name: '关键诉求回应', dimension: 'D3 专业信息沟通', owner: '专业服务评价 Agent' },
  { id: 'D3.5', name: '信息解释清晰性', dimension: 'D3 专业信息沟通', owner: '专业服务评价 Agent' },
  { id: 'D4.1', name: '情绪识别与回应', dimension: 'D4 情感共情性', owner: '共情与关系评价 Agent' },
  { id: 'D4.2', name: '反映式理解', dimension: 'D4 情感共情性', owner: '共情与关系评价 Agent' },
  { id: 'D4.3', name: '尊重与非评判性', dimension: 'D4 情感共情性', owner: '共情与关系评价 Agent' },
  { id: 'D5.1', name: '咨询目标协商', dimension: 'D5 咨询协作性', owner: '过程与响应评价 Agent' },
  { id: 'D5.2', name: '患者意见征询', dimension: 'D5 咨询协作性', owner: '过程与响应评价 Agent' },
  { id: 'D5.3', name: '建议个体化程度', dimension: 'D5 咨询协作性', owner: '过程与响应评价 Agent' },
  { id: 'D5.4', name: '建议可执行性', dimension: 'D5 咨询协作性', owner: '过程与响应评价 Agent' },
  { id: 'D6.1', name: '风险信号回应', dimension: 'D6 心理风险应对', owner: '共情与关系评价 Agent' },
  { id: 'D6.2', name: '必要转介与求助提示', dimension: 'D6 心理风险应对', owner: '专业服务评价 Agent' },
]

const dialogueA: Message[] = [
  { id: 'A-01', role: '患者', at: '2026-10-11 09:14', content: '最近一直睡不好，有时会觉得自己撑不下去了。我有点害怕。' },
  { id: 'A-02', role: '医生', at: '2026-10-11 09:18', content: '听起来这段时间很难受。你现在是否有伤害自己的打算？身边有没有可以陪伴你的人？' },
  { id: 'A-03', role: '患者', at: '2026-10-11 09:20', content: '目前没有这样的打算，但我还是担心会变得更严重。' },
  { id: 'A-04', role: '医生', at: '2026-10-11 09:24', content: '谢谢你告诉我。如果你感到无法保证自己的安全，请及时寻求当地紧急医疗帮助。我们也可以继续讨论现在需要的支持。' },
]

const dialogueB: Message[] = [
  { id: 'B-01', role: '患者', at: '2026-10-10 14:07', content: '上次聊过睡眠问题。这两天又变得更难入睡，我想知道下一步该怎么办。' },
  { id: 'B-02', role: '医生', at: '2026-10-10 14:18', content: '我记得上次你提到过睡眠困扰。能说说这两天有哪些新的变化吗？' },
  { id: 'B-03', role: '患者', at: '2026-10-10 14:21', content: '白天也开始受影响了，而且我对之前的建议有些疑问。' },
]

const dialogueC: Message[] = [
  { id: 'C-01', role: '患者', at: '2026-10-09 10:02', content: '最近工作压力大，想聊聊怎么安排下一次咨询。' },
  { id: 'C-02', role: '医生', at: '2026-10-09 10:08', content: '我们可以先明确你最想处理的问题，再一起确定下次咨询的重点。你觉得怎样？' },
]

function results(
  messages: Message[],
  overrides: Record<string, Pick<MetricResult, 'state' | 'reason'> & { messageId?: string }>,
): MetricResult[] {
  return metricCatalog.map((metric) => {
    const override = overrides[metric.id]
    const message = messages.find((entry) => entry.id === override?.messageId)
    return {
      metricId: metric.id,
      state: override?.state ?? '不适用',
      reason: override?.reason ?? '该合成咨询片段未提供本指标适用情境。',
      evidence: message
        ? [{ messageId: message.id, quote: message.content, verification: '支持' }]
        : [],
    }
  })
}

export const demoRuns: EvaluationRun[] = [
  {
    id: 'EV-20261011-003', sessionId: 'S-20261011-03', caseId: 'CASE-018',
    patientRef: 'P-7F2A', doctorRef: 'DR-104', source: '合成演示数据', round: '初诊',
    status: '已完成', createdAt: '2026-10-11 09:30', updatedAt: '2026-10-11 09:34',
    rubricVersion: '竞赛指标 v0.1', evaluatedMetrics: 18, totalMetrics: 18,
    reviewRequired: true, issue: '发现需要人工核查的风险表达；医生回应已记录，待确认。',
    messages: dialogueA, history: [],
    results: results(dialogueA, {
      'D1.1': { state: '达标', reason: '医生对患者当前困扰作出实质性回应。', messageId: 'A-02' },
      'D3.4': { state: '达标', reason: '医生围绕患者的安全担忧进行了进一步询问。', messageId: 'A-02' },
      'D4.1': { state: '达标', reason: '医生注意到患者表达的痛苦并作出回应。', messageId: 'A-02' },
      'D4.3': { state: '达标', reason: '当前回复未见指责或否定性表达。', messageId: 'A-02' },
      'D6.1': { state: '需复核', reason: '患者出现风险表达；医生已进一步询问，仍需人工核查完整语境。', messageId: 'A-02' },
      'D6.2': { state: '需复核', reason: '医生给出紧急求助提示；提示是否充分需由人工复核。', messageId: 'A-04' },
      'D2.1': { state: '证据不足', reason: '缺少订单进入咨询阶段的服务开始事件，无法计算首次响应。' },
    }),
  },
  {
    id: 'EV-20261010-002', sessionId: 'S-20261010-02', caseId: 'CASE-017',
    patientRef: 'P-2C8D', doctorRef: 'DR-107', source: '合成演示数据', round: '复诊',
    status: '已完成', createdAt: '2026-10-10 14:30', updatedAt: '2026-10-10 14:36',
    rubricVersion: '竞赛指标 v0.1', evaluatedMetrics: 18, totalMetrics: 18,
    reviewRequired: true, issue: '患者补充新情况后，本次记录中未见后续医生回复。',
    messages: dialogueB,
    history: [{ sessionId: 'S-20260523-01', date: '2026-05-23', content: '既往咨询涉及睡眠困扰；此处仅展示经授权的背景摘要，不作为本次医生行为评分证据。' }],
    results: results(dialogueB, {
      'D1.1': { state: '达标', reason: '医生围绕本次问题作出询问。', messageId: 'B-02' },
      'D2.2': { state: '需复核', reason: '患者补充新的问题后，本次记录中未见后续医生回复；需核实轮次是否结束。', messageId: 'B-03' },
      'D3.4': { state: '需复核', reason: '患者询问下一步安排，现有记录尚未见完整回应。', messageId: 'B-03' },
      'D4.1': { state: '证据不足', reason: '片段不足以判断后续情绪回应情况。' },
      'D6.1': { state: '不适用', reason: '本次对话未见明确风险信号。' },
      'D6.2': { state: '不适用', reason: '本次对话未见需要紧急转介的明确情境。' },
    }),
  },
  {
    id: 'EV-20261009-001', sessionId: 'S-20261009-01',
    patientRef: 'P-9B41', doctorRef: 'DR-102', source: '合成演示数据', round: '初诊',
    status: '已完成', createdAt: '2026-10-09 10:12', updatedAt: '2026-10-09 10:16',
    rubricVersion: '竞赛指标 v0.1', evaluatedMetrics: 18, totalMetrics: 18,
    reviewRequired: false, issue: '当前片段未形成待人工复核线索。',
    messages: dialogueC, history: [],
    results: results(dialogueC, {
      'D1.1': { state: '达标', reason: '医生回应了本次咨询安排诉求。', messageId: 'C-02' },
      'D3.4': { state: '达标', reason: '医生围绕下一次咨询的重点作出回应。', messageId: 'C-02' },
      'D5.1': { state: '达标', reason: '医生邀请患者共同确定咨询重点。', messageId: 'C-02' },
      'D5.2': { state: '达标', reason: '医生询问患者对安排的意见。', messageId: 'C-02' },
      'D6.1': { state: '不适用', reason: '本次对话未见明确风险信号。' },
      'D6.2': { state: '不适用', reason: '本次对话未见需要紧急转介的明确情境。' },
    }),
  },
  {
    id: 'EV-20261008-004', sessionId: 'S-20261008-04',
    patientRef: 'P-4E06', doctorRef: 'DR-109', source: '合成演示数据', round: '初诊',
    status: '部分完成', createdAt: '2026-10-08 16:40', updatedAt: '2026-10-08 16:44',
    rubricVersion: '竞赛指标 v0.1', evaluatedMetrics: 11, totalMetrics: 18,
    reviewRequired: true, issue: '来源记录不完整，部分指标无法定位原文。',
    messages: [], history: [], results: [],
  },
]

export const demoCases: ReviewCase[] = [
  { id: 'CASE-018', runId: 'EV-20261011-003', title: '风险表达与医生回应待核查', category: '心理风险应对', priority: '高', state: '待处理', createdAt: '2026-10-11 09:34', evidenceState: '原文可定位', hookHint: '候选线索：出现需要关注的风险表达' },
  { id: 'CASE-017', runId: 'EV-20261010-002', title: '后续反馈与关键诉求回应待核查', category: '服务跟进', priority: '中', state: '待处理', createdAt: '2026-10-10 14:36', evidenceState: '需核查轮次边界', hookHint: '风险 Hook 未命中；D6 仍已纳入评价' },
]

export const demoAudit: AuditEvent[] = [
  { id: 'AU-003', at: '2026-10-11 09:34', action: '报告生成', target: 'EV-20261011-003', detail: '合成演示评价完成，案件进入人工复核队列。' },
  { id: 'AU-002', at: '2026-10-10 14:36', action: '复核创建', target: 'CASE-017', detail: '后续反馈问题被标记为待核查。' },
  { id: 'AU-001', at: '2026-10-09 10:16', action: '报告归档', target: 'EV-20261009-001', detail: '合成演示报告归档。' },
]

export const demoState: DashboardData = {
  runs: demoRuns,
  cases: demoCases,
  audit: demoAudit,
}

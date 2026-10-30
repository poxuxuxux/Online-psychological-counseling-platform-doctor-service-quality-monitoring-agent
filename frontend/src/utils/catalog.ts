// 环节：前端展示工具层；用途：提供目录映射、显示计算、导出或复核排序逻辑。
export const agents: Record<string, string> = {
  team_lead: 'Leader · 综合与裁决',
  'evaluator:effectiveness': '评价 Agent 1 · 问题解决与实效',
  'evaluator:empathy': '评价 Agent 2 · 情绪处境与沟通',
  'evaluator:collaboration': '评价 Agent 3 · 响应协作与落地',
  professional_service: '专业服务评价',
  process_response: '过程与响应评价',
  empathy_relationship: '共情与关系评价',
  'evaluator:D1': '主责评价 Agent · D1+D3',
  'evaluator:D2': '主责评价 Agent · D2+D5',
  'evaluator:D4': '主责评价 Agent · D4+D6',
}
export const dimensions = [
  { id: 'D1', name: '服务履行' },
  { id: 'D2', name: '响应及时性' },
  { id: 'D3', name: '专业信息与回应' },
  { id: 'D4', name: '共情与关系' },
  { id: 'D5', name: '协作与建议' },
  { id: 'D6', name: '风险回应与转介' },
]
export const dimensionGroups = [
  { id: 'D1+D3', name: '服务履行与专业信息探询', dimensionIds: ['D1', 'D3'] },
  { id: 'D2+D5', name: '响应及时性与咨询建议', dimensionIds: ['D2', 'D5'] },
  { id: 'D4+D6', name: '共情关系与风险转介', dimensionIds: ['D4', 'D6'] },
]
export const metrics = [
  ['D1.1', '实质性服务履行', 'professional_service'],
  ['D1.2', '服务内容一致性', 'professional_service'],
  ['D2.1', '首次响应及时性', 'process_response'],
  ['D2.2', '交互响应及时性', 'process_response'],
  ['D3.1', '症状信息探询', 'professional_service'],
  ['D3.2', '病史与治疗信息核对', 'professional_service'],
  ['D3.3', '心理社会背景探询', 'professional_service'],
  ['D3.4', '关键诉求回应', 'professional_service'],
  ['D3.5', '信息解释清晰性', 'professional_service'],
  ['D4.1', '情绪识别与回应', 'empathy_relationship'],
  ['D4.2', '反映式理解', 'empathy_relationship'],
  ['D4.3', '尊重与非评判性', 'empathy_relationship'],
  ['D5.1', '咨询目标协商', 'process_response'],
  ['D5.2', '患者意见征询', 'process_response'],
  ['D5.3', '建议个体化程度', 'process_response'],
  ['D5.4', '建议可执行性', 'process_response'],
  ['D6.1', '风险信号回应', 'empathy_relationship'],
  ['D6.2', '必要转介与求助提示', 'professional_service'],
].map(([id, name, agent]) => ({ id: id!, name: name!, agent: agent! }))
// The deployed demo uses dimension IDs with a different, provisional mapping. Never relabel these as formal metrics.
const demoNames: Record<string, string> = {
  D1: '专业信息采集（演示）',
  D2: '响应与咨询节奏（演示）',
  D3: '方案与专业支持（演示）',
  D4: '共情与关系建立（演示）',
  D5: '流程说明与跟进（演示）',
}
export function metricName(id: string): string {
  return metrics.find((m) => m.id === id)?.name || demoNames[id] || id
}
export function agentName(id: string): string {
  return agents[id] || id
}
export const labels: Record<string, string> = {
  completed: '运行完成',
  partial: '部分完成',
  failed: '运行失败',
  initial: '初诊',
  follow_up: '复诊',
  unknown: '未标注',
  valid: '已定位',
  missing: '引用缺失',
  quote_mismatch: '引文不匹配',
  source_mismatch: '来源不匹配',
  uncertain: '无法判断',
  matched: '匹配',
  mismatched: '不匹配',
  supported: '支持',
  contradicted: '矛盾',
  insufficient_evidence: '证据不足',
  unsupported: '不支持',
  not_needed: '无需仲裁',
  resolved: '已解决',
  unresolved: '尚未解决',
  not_configured: '尚未接入',
  applicable: '适用',
  not_applicable: '不适用',
  insufficient_context: '证据不足',
  evaluator: '主责评价 Agent',
  verifier: '证据核验 Agent',
  arbiter: '分歧仲裁 Agent',
  re_evaluated: '修订评价',
  verification: '核验意见',
  manual_review: '转人工复核',
}
export function label(value: string | null | undefined): string {
  return value ? labels[value] || value : '尚未返回'
}
export function time(value?: string | null, full = false): string {
  if (!value) return '时间未提供'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间无效'
  return new Intl.DateTimeFormat(
    'zh-CN',
    full
      ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }
      : { hour: '2-digit', minute: '2-digit', hour12: false },
  ).format(date)
}

export type MetricState = '达标' | '需复核' | '不适用' | '证据不足'
export type RunState = '排队中' | '运行中' | '已完成' | '部分完成' | '失败'
export type CaseState = '待处理' | '处理中' | '已处理'
export type ReviewDecision = '确认' | '驳回' | '修正' | '无法判断' | '升级处理'

export interface MetricDefinition {
  id: string
  name: string
  dimension: string
  owner: string
}

export interface EvidenceRef {
  messageId: string
  quote: string
  verification: '支持' | '矛盾' | '证据不足'
}

export interface MetricResult {
  metricId: string
  state: MetricState
  reason: string
  evidence: EvidenceRef[]
}

export interface Message {
  id: string
  role: '患者' | '医生'
  at: string
  content: string
}

export interface HistoryExcerpt {
  sessionId: string
  date: string
  content: string
}

export interface EvaluationRun {
  id: string
  sessionId: string
  caseId?: string
  patientRef: string
  doctorRef: string
  source: string
  round: '初诊' | '复诊'
  status: RunState
  createdAt: string
  updatedAt: string
  rubricVersion: string
  evaluatedMetrics: number
  totalMetrics: number
  reviewRequired: boolean
  issue: string
  results: MetricResult[]
  messages: Message[]
  history: HistoryExcerpt[]
}

export interface ReviewCase {
  id: string
  runId: string
  title: string
  category: string
  priority: '高' | '中' | '低'
  state: CaseState
  createdAt: string
  evidenceState: string
  hookHint: string
  decision?: ReviewDecision
  decisionReason?: string
}

export interface AuditEvent {
  id: string
  at: string
  action: string
  target: string
  detail: string
}

export interface DashboardData {
  runs: EvaluationRun[]
  cases: ReviewCase[]
  audit: AuditEvent[]
}

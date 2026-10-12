import { demoState, metricCatalog } from './demoData'
import type {
  AuditEvent,
  DashboardData,
  EvaluationRun,
  MetricDefinition,
  ReviewCase,
  ReviewDecision,
} from '../types/domain'

export const dataMode: 'demo' | 'api' =
  import.meta.env.VITE_DATA_MODE === 'demo' ||
  (!import.meta.env.VITE_DATA_MODE && import.meta.env.DEV)
    ? 'demo'
    : 'api'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const demoSessionKey = 'quality-console-demo-session'
let apiAuthenticated = false

function clone<T>(value: T): T {
  return structuredClone(value)
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? '后端业务接口尚未接入；请联系后端同学确认 API 契约。'
        : `请求失败（${response.status}）`,
    )
  }
  return response.json() as Promise<T>
}

export const service = {
  isAuthenticated(): boolean {
    return dataMode === 'demo'
      ? sessionStorage.getItem(demoSessionKey) === '1'
      : apiAuthenticated
  },

  async signIn(username: string, password: string): Promise<void> {
    if (dataMode === 'demo') {
      sessionStorage.setItem(demoSessionKey, '1')
      return
    }
    await apiRequest('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    apiAuthenticated = true
  },

  async signOut(): Promise<void> {
    if (dataMode === 'demo') {
      sessionStorage.removeItem(demoSessionKey)
      return
    }
    await apiRequest('/api/v1/auth/logout', { method: 'POST' })
    apiAuthenticated = false
  },

  async dashboard(): Promise<DashboardData> {
    if (dataMode === 'demo') return clone(demoState)
    return apiRequest('/api/v1/dashboard/overview')
  },

  async runs(): Promise<EvaluationRun[]> {
    if (dataMode === 'demo') return clone(demoState.runs)
    return apiRequest('/api/v1/evaluations')
  },

  async run(id: string): Promise<EvaluationRun> {
    if (dataMode === 'demo') {
      const result = demoState.runs.find((entry) => entry.id === id)
      if (!result) throw new Error('没有找到该评价任务。')
      return clone(result)
    }
    return apiRequest(`/api/v1/evaluations/${encodeURIComponent(id)}`)
  },

  async createDemoEvaluation(templateId: string): Promise<EvaluationRun> {
    if (dataMode !== 'demo') throw new Error('真实任务创建需要后端任务接口。')
    const template = demoState.runs.find((entry) => entry.id === templateId)
    if (!template) throw new Error('没有找到演示样例。')
    const run: EvaluationRun = {
      ...clone(template),
      id: `DEMO-${String(demoState.runs.length + 1).padStart(3, '0')}`,
      caseId: undefined,
      source: '合成演示 · 样例报告',
      reviewRequired: false,
      issue: '由内置合成样例复制的界面演示报告，未调用评价模型。',
      createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
      updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    }
    demoState.runs.unshift(run)
    demoState.audit.unshift({
      id: `AU-${Date.now()}`,
      at: run.createdAt,
      action: '演示任务创建',
      target: run.id,
      detail: '使用合成样例生成界面演示报告，未调用真实模型。',
    })
    return clone(run)
  },

  async cases(): Promise<ReviewCase[]> {
    if (dataMode === 'demo') return clone(demoState.cases)
    return apiRequest('/api/v1/review-cases')
  },

  async reviewCase(id: string): Promise<ReviewCase> {
    if (dataMode === 'demo') {
      const result = demoState.cases.find((entry) => entry.id === id)
      if (!result) throw new Error('没有找到该复核案件。')
      return clone(result)
    }
    return apiRequest(`/api/v1/review-cases/${encodeURIComponent(id)}`)
  },

  async decideCase(id: string, decision: ReviewDecision, reason: string): Promise<ReviewCase> {
    if (dataMode === 'demo') {
      const result = demoState.cases.find((entry) => entry.id === id)
      if (!result) throw new Error('没有找到该复核案件。')
      if (result.state === '已处理') throw new Error('此案件已处理，不能重复提交。')
      result.state = '已处理'
      result.decision = decision
      result.decisionReason = reason.trim()
      demoState.audit.unshift({
        id: `AU-${Date.now()}`,
        at: new Date().toLocaleString('zh-CN', { hour12: false }),
        action: '人工复核',
        target: result.id,
        detail: `${decision}：${reason.trim()}`,
      })
      return clone(result)
    }
    return apiRequest(`/api/v1/review-cases/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason: reason.trim() }),
    })
  },

  async metrics(): Promise<MetricDefinition[]> {
    if (dataMode === 'demo') return clone(metricCatalog)
    return apiRequest('/api/v1/skills')
  },

  async audit(): Promise<AuditEvent[]> {
    if (dataMode === 'demo') return clone(demoState.audit)
    return apiRequest('/api/v1/audit-events')
  },
}

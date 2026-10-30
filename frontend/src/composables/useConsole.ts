// 环节：前端状态逻辑层；用途：封装页面复用状态与 API 联动逻辑。
import { computed, ref } from 'vue'
import { api } from '../api/endpoints/evaluations'
import { hasPrivateAccessToken } from '../api/client/http'
import type { ConsultationItem, ConsultationDetail } from '../api/contracts/consultations'
import type { Session, Report, Ready, Recent } from '../api/contracts/evaluation'
import { previewReport, previewSession } from '../data/preview'
import { reportRows } from '../utils/trust'
import { overallScore } from '../utils/trust'

export type BatchRiskLevel = 'high' | 'medium' | 'low' | 'unknown'
export type BatchRun = {
  mode?: 'service' | 'preview'
  batch_id: string
  created_at: string
  total: number
  succeeded: number
  failed: number
  high: number
  medium: number
  low: number
  unknown: number
  quality_summary: string
  sessions: { session_id: string; status: string; risk_level: BatchRiskLevel; pending_count: number }[]
}
const batchStorageKey = 'xin-heng-batch-runs-v2'
function savedBatchRuns(): BatchRun[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(batchStorageKey) || '[]')
    return Array.isArray(parsed) ? (parsed as BatchRun[]).slice(0, 10) : []
  } catch {
    return []
  }
}
function persistBatchRuns(runs: BatchRun[]) {
  try {
    localStorage.setItem(batchStorageKey, JSON.stringify(runs.slice(0, 10)))
  } catch {
    // The current page still shows this batch if browser storage is unavailable.
  }
}

export function useConsole(initialMode?: 'service' | 'preview') {
  const mode = ref<'service' | 'preview'>(initialMode || (location.protocol === 'file:' ? 'preview' : 'service'))
  const session = ref<Session | null>(null),
    report = ref<Report | null>(null),
    ready = ref<Ready | null>(null),
    recent = ref<Recent | null>(null)
  const loading = ref(false),
    running = ref(false),
    checking = ref(false)
  const batchProgress = ref({ total: 0, completed: 0, succeeded: 0, failed: 0, currentId: '' })
  const batchRuns = ref<BatchRun[]>(savedBatchRuns())
  const consultations = ref<ConsultationItem[]>([])
  const totalConsultations = ref(0),
    listOffset = ref(0),
    listQuery = ref('')
  const listing = ref(false),
    listError = ref(''),
    listSource = ref<'preview' | 'database' | 'uploaded' | 'access_required' | 'unavailable'>('unavailable')
  let selectionEpoch = 0,
    listEpoch = 0
  const previewDetails = new Map<string, ConsultationDetail>()
  const uploadedDetails = new Map<string, ConsultationDetail>()
  const errors = ref({ session: '', run: '', recent: '', ready: '' })
  const connected = ref(false),
    lastChecked = ref(''),
    lastRun = ref('')
  let epoch = 0
  const rows = computed(() => reportRows(report.value))
  const pending = computed(() =>
    rows.value.filter((r) => !['verified', 'agent_scored', 'not_applicable'].includes(r.verdict.code)),
  )
  async function refreshRecent() {
    const token = epoch
    if (mode.value === 'preview') return
    try {
      const result = await api.recent()
      if (token === epoch) {
        recent.value = result
        errors.value.recent = ''
      }
    } catch (error) {
      if (token === epoch) errors.value.recent = (error as Error).message
    }
  }
  async function checkService() {
    if (checking.value || mode.value === 'preview') return
    checking.value = true
    const token = epoch
    const [healthResult, readyResult] = await Promise.allSettled([api.health(), api.ready()])
    if (token === epoch) {
      connected.value = healthResult.status === 'fulfilled' && healthResult.value.status === 'ok'
      ready.value = readyResult.status === 'fulfilled' ? readyResult.value : null
      errors.value.ready = readyResult.status === 'rejected' ? readyResult.reason.message : ''
      lastChecked.value = new Date().toISOString()
      checking.value = false
    }
  }
  function previewData() {
    if (!previewDetails.size)
      for (let index = 0; index < 3; index++) {
        const next = previewSession(index)
        previewDetails.set(next.session_id, { session: next, report: previewReport(next) })
      }
    return [...previewDetails.values()]
  }
  async function selectConsultation(id: string) {
    if (running.value) return
    const token = epoch,
      selectionToken = ++selectionEpoch
    session.value = null
    report.value = null
    loading.value = true
    errors.value.session = ''
    errors.value.run = ''
    try {
      const detail =
        mode.value === 'preview'
          ? previewData().find((d) => d.session.session_id === id)
          : uploadedDetails.get(id) ??
            await api.consultation(id)
      if (
        !detail ||
        detail.session.session_id !== id ||
        (detail.report && detail.report.session_id !== id)
      )
        throw new Error('咨询 ID 与返回记录不一致，已阻止展示。')
      if (token === epoch && selectionToken === selectionEpoch) {
        session.value = detail.session
        report.value = detail.report
      }
    } catch (error) {
      if (token === epoch && selectionToken === selectionEpoch)
        errors.value.session = (error as Error).message
    } finally {
      if (token === epoch && selectionToken === selectionEpoch) loading.value = false
    }
  }
  async function refreshConsultations(
    offset = 0,
    query = listQuery.value,
    startDate?: string,
    endDate?: string,
  ) {
    if (running.value) return
    const token = epoch,
      listToken = ++listEpoch
    listing.value = true
    listError.value = ''
    try {
      const matchesRange = (value: string | null | undefined) => {
        if (!startDate || !endDate) return true
        const day = value?.slice(0, 10) || ''
        return day >= startDate && day <= endDate
      }
      if (mode.value === 'preview') {
        const data = previewData().filter((d) =>
          d.session.session_id.includes(query.trim()) &&
          matchesRange(d.session.messages[0]?.timestamp),
        )
        consultations.value = data.slice(offset, offset + 5).map((d) => ({
          session_id: d.session.session_id,
          consultation_round: d.session.consultation_round,
          message_count: d.session.messages.length,
          updated_at: d.session.messages[0]?.timestamp || '',
          evaluation_status: d.report?.status || null,
        }))
        totalConsultations.value = data.length
        listSource.value = 'preview'
      } else if (uploadedDetails.size) {
        const data = [...uploadedDetails.values()].filter((d) =>
          d.session.session_id.toLowerCase().includes(query.trim().toLowerCase()) &&
          matchesRange(d.session.imported_at || d.session.messages[0]?.timestamp),
        )
        consultations.value = data.slice(offset, offset + 5).map((d) => ({
          session_id: d.session.session_id,
          consultation_round: d.session.consultation_round,
          message_count: d.session.messages.length,
          updated_at: d.session.imported_at || new Date().toISOString(),
          evaluation_status: d.report?.status || null,
        }))
        totalConsultations.value = data.length
        listSource.value = 'uploaded'
      } else if (hasPrivateAccessToken()) {
        const result = await api.consultations(offset, query, 5, startDate, endDate)
        if (token !== epoch || listToken !== listEpoch) return
        consultations.value = result.items
        totalConsultations.value = result.total
        listSource.value = 'database'
      } else {
        consultations.value = []
        totalConsultations.value = 0
        listSource.value = 'access_required'
      }
      if (token === epoch && listToken === listEpoch) {
        listOffset.value = offset
        listQuery.value = query.trim()
      }
    } catch (error) {
      if (token === epoch && listToken === listEpoch) {
        listError.value = (error as Error).message
        consultations.value = []
        totalConsultations.value = 0
        listSource.value = 'unavailable'
      }
    } finally {
      if (token === epoch && listToken === listEpoch) listing.value = false
    }
  }
  async function loadSession() {
    if (loading.value || running.value) return
    const token = epoch
    loading.value = true
    errors.value.session = ''
    try {
      await refreshConsultations()
      if (token === epoch && consultations.value[0])
        await selectConsultation(consultations.value[0].session_id)
    } catch (error) {
      if (token === epoch) errors.value.session = (error as Error).message
    } finally {
      if (token === epoch) loading.value = false
    }
  }
  async function addUploadedSessions(items: Session[]) {
    for (const item of items) uploadedDetails.set(item.session_id, { session: item, report: null })
    await refreshConsultations(0, '')
    if (items[0]) await selectConsultation(items[0].session_id)
  }
  async function runAll(targetId?: string) {
    if (running.value || loading.value || listing.value) return
    const token = epoch
    const selectedSessionId = session.value?.session_id
    running.value = true
    errors.value.run = ''
    batchProgress.value = { total: 0, completed: 0, succeeded: 0, failed: 0, currentId: '' }
    try {
      let allSessions: Session[] = []
      let realSessionIds: string[] = []
      if (mode.value === 'preview') {
        allSessions = previewData().map((detail) => detail.session)
      } else if (uploadedDetails.size) {
        allSessions = [...uploadedDetails.values()].map((detail) => detail.session)
      } else {
        if (!hasPrivateAccessToken())
          throw new Error('请先在“服务连接”中输入私有数据访问令牌。')
        const serviceReady = await api.ready()
        ready.value = serviceReady
        if (serviceReady.model?.configured === false)
          throw new Error('后端尚未配置模型密钥。请在 Railway 后端服务设置 DEEPSEEK_API_KEY、DASHSCOPE_API_KEY 或 GLM_API_KEY。')
        // 仅获取真实会话 ID；逐条读取详情，避免在浏览器同时保留大量敏感原文。
        for (let offset = 0; ; offset += 100) {
          const page = await api.consultations(offset, '', 100)
          realSessionIds.push(...page.items.map((item) => item.session_id))
          if (offset + page.items.length >= page.total || page.items.length === 0) break
        }
      }
      if (token !== epoch) return
      const ids = targetId
        ? [targetId]
        : allSessions.length ? allSessions.map((item) => item.session_id) : realSessionIds
      if (!ids.length) throw new Error(mode.value === 'preview' ? '当前没有离线样例。' : '数据库没有真实咨询记录。请先导入会话数据，再开始评估。')
      if (new Set(ids).size !== ids.length)
        throw new Error('咨询目录包含重复 ID，已阻止批量评估。')
      batchProgress.value.total = ids.length
      const failures: string[] = []
      const completedReports: Report[] = []
      const sessionOutcomes: BatchRun['sessions'] = []
      for (const id of ids) {
        if (token !== epoch) return
        batchProgress.value.currentId = id
        try {
          const item = allSessions.length
            ? allSessions.find((session) => session.session_id === id)!
            : (await api.consultation(id)).session
          if (item.session_id !== id) throw new Error('咨询 ID 与返回记录不一致，已阻止评价。')
          const result = mode.value === 'preview'
            ? previewReport(item)
            : uploadedDetails.has(id) ? await api.evaluateGuest(item) : await api.evaluate(item)
          if (result.session_id !== item.session_id)
            throw new Error('返回报告与提交的咨询 ID 不一致。')
          if (mode.value === 'preview')
            previewDetails.set(item.session_id, { session: item, report: result })
          else if (uploadedDetails.has(id))
            uploadedDetails.set(id, { session: item, report: result })
          if (result.status !== 'failed') completedReports.push(result)
          const reportRowsForSession = reportRows(result)
          const pendingCount = reportRowsForSession.filter(
            (row) => !['verified', 'agent_scored', 'not_applicable'].includes(row.verdict.code),
          ).length
          sessionOutcomes.push({
            session_id: item.session_id,
            status: result.status,
            risk_level: result.status === 'failed' ? 'unknown' : result.risk?.level ?? 'unknown',
            pending_count: pendingCount,
          })
          if (selectedSessionId === item.session_id) report.value = result
          consultations.value = consultations.value.map((listed) =>
            listed.session_id === item.session_id
              ? { ...listed, evaluation_status: result.status }
              : listed,
          )
          if (result.status === 'failed') {
            batchProgress.value.failed++
            failures.push(`${item.session_id}：后端评价失败（${result.team?.stop_reason || '原因未提供'}）`)
          } else {
            batchProgress.value.succeeded++
          }
          lastRun.value = new Date().toISOString()
        } catch (error) {
          batchProgress.value.failed++
          failures.push(`${id}：${(error as Error).message}`)
          sessionOutcomes.push({ session_id: id, status: 'failed', risk_level: 'unknown', pending_count: 0 })
        } finally {
          batchProgress.value.completed++
        }
      }
      batchProgress.value.currentId = ''
      if (failures.length) errors.value.run = `有 ${failures.length} 条未完成：${failures.join('；')}`
      const high = sessionOutcomes.filter((item) => item.risk_level === 'high').length
      const medium = sessionOutcomes.filter((item) => item.risk_level === 'medium').length
      const low = sessionOutcomes.filter((item) => item.risk_level === 'low').length
      const unknown = sessionOutcomes.filter((item) => item.risk_level === 'unknown').length
      const totalRows = completedReports.flatMap((result) => reportRows(result))
      const scoredItems = totalRows.filter((row) => ['verified', 'agent_scored'].includes(row.verdict.code)).length
      const pendingItems = totalRows.filter((row) => !['verified', 'agent_scored', 'not_applicable'].includes(row.verdict.code)).length
      const trustedScores = completedReports.map(overallScore).filter((score): score is number => score !== null)
      const hasDemoFallback = completedReports.some((result) =>
        result.limitations.some((item) => item.includes('固定演示规则')),
      )
      const qualitySummary = completedReports.length === 0
        ? '本批没有会话完成评价，暂时无法判断平台服务质量。'
        : trustedScores.length === completedReports.length
          ? `本批 ${completedReports.length} 轮均通过总分门槛，质量评分均值为 ${(trustedScores.reduce((sum, score) => sum + score, 0) / trustedScores.length * 20).toFixed(1)} 分（满分 100）。后端判定服务质量高风险 ${high} 轮，风险未知 ${unknown} 轮。`
          : `本批完成 ${completedReports.length} 轮评价，${scoredItems} 项已计分，${pendingItems} 项待复核；后端判定服务质量高风险 ${high} 轮，风险未知 ${unknown} 轮。${hasDemoFallback ? '当前含固定演示规则评分，只用于流程演示。' : ''}由于本批未达到总分门槛，暂不能给出服务质量达标结论。`
      const batchRun: BatchRun = {
        mode: mode.value,
        batch_id: `batch-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        created_at: new Date().toISOString(),
        total: ids.length,
        succeeded: batchProgress.value.succeeded,
        failed: batchProgress.value.failed,
        high,
        medium,
        low,
        unknown,
        quality_summary: qualitySummary,
        sessions: sessionOutcomes,
      }
      batchRuns.value = [batchRun, ...batchRuns.value].slice(0, 10)
      if (!uploadedDetails.size) persistBatchRuns(batchRuns.value)
      if (mode.value === 'service') await refreshRecent()
    } catch (error) {
      if (token === epoch) errors.value.run = (error as Error).message
    } finally {
      if (token === epoch) running.value = false
    }
  }
  async function setMode(next: 'service' | 'preview') {
    if (running.value || next === mode.value) return
    epoch++
    selectionEpoch++
    listEpoch++
    mode.value = next
    session.value = null
    report.value = null
    ready.value = null
    recent.value = null
    consultations.value = []
    totalConsultations.value = 0
    listOffset.value = 0
    listQuery.value = ''
    listing.value = false
    listError.value = ''
    listSource.value = 'unavailable'
    batchProgress.value = { total: 0, completed: 0, succeeded: 0, failed: 0, currentId: '' }
    errors.value = { session: '', run: '', recent: '', ready: '' }
    connected.value = false
    loading.value = false
    checking.value = false
    await loadSession()
    if (next === 'service') await Promise.allSettled([checkService(), refreshRecent()])
  }
  async function initialize() {
    await Promise.allSettled([loadSession(), checkService(), refreshRecent()])
  }
  return {
    mode,
    session,
    report,
    ready,
    recent,
    loading,
    running,
    batchProgress,
    batchRuns,
    checking,
    errors,
    connected,
    lastChecked,
    lastRun,
    rows,
    pending,
    consultations,
    totalConsultations,
    listOffset,
    listQuery,
    listing,
    listError,
    listSource,
    selectConsultation,
    refreshConsultations,
    addUploadedSessions,
    initialize,
    setMode,
    loadSession,
    runAll,
    checkService,
    refreshRecent,
  }
}

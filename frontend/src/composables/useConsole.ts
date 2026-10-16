import { computed, ref } from 'vue'
import { api } from '../api/endpoints/evaluations'
import { ApiError } from '../api/client/http'
import type { ConsultationItem, ConsultationDetail } from '../api/contracts/consultations'
import type { Session, Report, Ready, Recent } from '../api/contracts/evaluation'
import { previewReport, previewSession } from '../data/preview'
import { reportRows } from '../utils/trust'

export function useConsole() {
  const mode = ref<'service' | 'preview'>(location.protocol === 'file:' ? 'preview' : 'service')
  const session = ref<Session | null>(null),
    report = ref<Report | null>(null),
    ready = ref<Ready | null>(null),
    recent = ref<Recent | null>(null)
  const loading = ref(false),
    running = ref(false),
    checking = ref(false)
  const consultations = ref<ConsultationItem[]>([])
  const totalConsultations = ref(0),
    listOffset = ref(0),
    listQuery = ref('')
  const listing = ref(false),
    listError = ref(''),
    listSource = ref<'preview' | 'database' | 'demo' | 'unavailable'>('unavailable')
  let selectionEpoch = 0,
    listEpoch = 0
  const previewDetails = new Map<string, ConsultationDetail>()
  const errors = ref({ session: '', run: '', recent: '', ready: '' })
  const connected = ref(false),
    lastChecked = ref(''),
    lastRun = ref('')
  let epoch = 0
  const rows = computed(() => reportRows(report.value))
  const pending = computed(() =>
    rows.value.filter((r) => !['verified', 'not_applicable'].includes(r.verdict.code)),
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
          : listSource.value === 'demo'
            ? { session: await api.demo(), report: null }
            : await api.consultation(id)
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
  async function refreshConsultations(offset = 0, query = listQuery.value) {
    if (running.value) return
    const token = epoch,
      listToken = ++listEpoch
    listing.value = true
    listError.value = ''
    try {
      if (mode.value === 'preview') {
        const data = previewData().filter((d) => d.session.session_id.includes(query.trim()))
        consultations.value = data.slice(offset, offset + 5).map((d) => ({
          session_id: d.session.session_id,
          consultation_round: d.session.consultation_round,
          message_count: d.session.messages.length,
          updated_at: d.session.messages[0]?.timestamp || '',
          evaluation_status: d.report?.status || null,
        }))
        totalConsultations.value = data.length
        listSource.value = 'preview'
      } else {
        let result
        try {
          result = await api.consultations(offset, query.trim())
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error
          // Older deployed services still have a demo route; never invent database entries.
          result = null
        }
        if (token !== epoch || listToken !== listEpoch) return
        if (result?.database_configured && (result.total > 0 || query.trim() || offset > 0)) {
          consultations.value = result.items
          totalConsultations.value = result.total
          listSource.value = 'database'
        } else {
          const demo = await api.demo()
          if (token !== epoch || listToken !== listEpoch) return
          const matches = demo.session_id.includes(query.trim())
          consultations.value =
            matches && offset === 0
              ? [
                  {
                    session_id: demo.session_id,
                    consultation_round: demo.consultation_round,
                    message_count: demo.messages.length,
                    updated_at: demo.imported_at || '',
                    evaluation_status: null,
                  },
                ]
              : []
          totalConsultations.value = matches ? 1 : 0
          listSource.value = 'demo'
        }
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
  async function run() {
    if (!session.value || running.value || loading.value) return
    const token = epoch
    const submittedId = session.value.session_id
    running.value = true
    errors.value.run = ''
    try {
      const result =
        mode.value === 'preview' ? previewReport(session.value) : await api.evaluate(session.value)
      if (result.session_id !== submittedId)
        throw new Error('返回报告与本次会话不一致，已阻止展示。')
      if (token === epoch) {
        report.value = result
        lastRun.value = new Date().toISOString()
        if (mode.value === 'preview')
          previewDetails.set(submittedId, { session: session.value!, report: result })
        consultations.value = consultations.value.map((item) =>
          item.session_id === submittedId ? { ...item, evaluation_status: result.status } : item,
        )
        await refreshRecent()
      }
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
    initialize,
    setMode,
    loadSession,
    run,
    checkService,
    refreshRecent,
  }
}

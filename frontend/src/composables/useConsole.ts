import { computed, ref } from 'vue'
import { api } from '../api/endpoints/evaluations'
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
  async function loadSession() {
    if (loading.value || running.value) return
    const token = epoch
    loading.value = true
    errors.value.session = ''
    try {
      const next = mode.value === 'preview' ? previewSession() : await api.demo()
      if (token === epoch) {
        session.value = next
        report.value = null
        errors.value.run = ''
      }
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
      const result = mode.value === 'preview' ? previewReport() : await api.evaluate(session.value)
      if (result.session_id !== submittedId)
        throw new Error('返回报告与本次会话不一致，已阻止展示。')
      if (token === epoch) {
        report.value = result
        lastRun.value = new Date().toISOString()
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
    mode.value = next
    session.value = null
    report.value = null
    ready.value = null
    recent.value = null
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
    initialize,
    setMode,
    loadSession,
    run,
    checkService,
    refreshRecent,
  }
}

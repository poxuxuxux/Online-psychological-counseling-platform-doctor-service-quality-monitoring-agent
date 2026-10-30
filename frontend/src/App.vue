<!-- 环节：前端应用入口层；用途：启动并组合 Vue 工作台界面。 -->
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import Icon from './components/base/Icon.vue'
import StatusBadge from './components/base/StatusBadge.vue'
import ConversationPanel from './components/conversation/ConversationPanel.vue'
import ConsultationList from './components/conversation/ConsultationList.vue'
import {
  comparePriority,
  priorityLevels,
  priorityNames,
  type PriorityLevel,
} from './utils/reviewPriority'
import FindingDetail from './components/feedback/FindingDetail.vue'
import ReviewScoreDialog, { type ReviewScoreSubmission } from './components/feedback/ReviewScoreDialog.vue'
import OverviewPage from './pages/OverviewPage.vue'
import ProfilePage from './pages/ProfilePage.vue'
import EvaluationWorkspace from './components/workspace/EvaluationWorkspace.vue'
import OfflineReportsPage from './pages/OfflineReportsPage.vue'
import ServiceReportsPage from './pages/ServiceReportsPage.vue'
import OfflineReviewPage from './pages/OfflineReviewPage.vue'
import { useConsole } from './composables/useConsole'
import { agentName, dimensions, label, metrics, time } from './utils/catalog'
import { overallScore } from './utils/trust'
import { downloadJson } from './utils/export'
import { api } from './api/endpoints/evaluations'
import { setPrivateAccessToken } from './api/client/http'
import { SessionSchema } from './api/contracts/evaluation'
import { dateRangeKey, isDateInRange, rangeDayCount, type DateRange } from './composables/dateRange'
const separateBackend = Boolean(import.meta.env.VITE_API_URL)
const privateToken = ref('')
const privateAccessEnabled = ref(false)
const importing = ref(false)
const importMessage = ref('')
const uploadPhase = ref<'idle' | 'uploading' | 'complete'>('idle')
const uploadInput = ref<HTMLInputElement | null>(null)
async function importSessions(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files || [])]
  input.value = ''
  if (!files.length) return
  importing.value = true
  uploadPhase.value = 'uploading'
  const accepted: import('./api/contracts/evaluation').Session[] = []
  const failures: string[] = []
  for (const file of files) {
    try {
      if (file.size > 2_000_000) throw new Error('单个文件超过 2 MB，请按会话拆分。')
      const parsed = SessionSchema.safeParse(JSON.parse(await file.text()))
      if (!parsed.success) throw new Error('不是符合后端 Session 格式的 JSON。')
      if (parsed.data.source_id === 'synthetic-demo') throw new Error('演示数据不能作为真实会话导入。')
      if (accepted.some((item) => item.session_id === parsed.data.session_id))
        throw new Error('本次上传包含重复咨询 ID。')
      accepted.push(parsed.data)
    } catch (error) {
      failures.push(`${file.name}：${(error as Error).message}`)
    }
  }
  if (accepted.length && mode.value === 'preview') await setMode('service')
  if (accepted.length) await addUploadedSessions(accepted)
  importMessage.value = `已完成 ${accepted.length}/${files.length} 份。${failures.length ? failures.join('；') : ''}`
  uploadPhase.value = accepted.length ? 'complete' : 'idle'
  importing.value = false
}
async function applyPrivateAccess() {
  setPrivateAccessToken(privateToken.value)
  privateAccessEnabled.value = !!privateToken.value.trim()
  privateToken.value = ''
  session.value = null
  report.value = null
  await refreshWorkspaceList(0, '')
  if (consultations.value[0]) await selectConsultation(consultations.value[0].session_id)
  await refreshRecent()
}
const {
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
  initialize,
  setMode,
  loadSession,
  runAll,
  checkService,
  refreshRecent,
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
} = useConsole('preview')
const nav = [
  { id: 'overview', name: '数据总览', icon: 'pulse' },
  { id: 'workspace', name: '评估工作台', icon: 'workspace' },
  { id: 'reports', name: '质检报告', icon: 'report' },
  { id: 'review', name: '人工复核', icon: 'shield' },
  { id: 'profile', name: '医生画像', icon: 'trend' },
  { id: 'rubrics', name: '评价指标', icon: 'list' },
  { id: 'service', name: '服务连接', icon: 'settings' },
]
const page = ref('overview'),
  mobileOpen = ref(false),
  sidebarCollapsed = ref(false),
  selectedId = ref(''),
  filter = ref('all'),
  query = ref(''),
  highlightedIds = ref<string[]>([])
const dateRange = ref<DateRange>({ start: '2024-06-01', end: '2024-06-30' })
provide(dateRangeKey, dateRange)
const dateRangeDraft = ref<DateRange>({ ...dateRange.value })
const dateRangeControl = ref<HTMLElement | null>(null)
const datePickerOpen = ref(false)
const dateRangeError = ref('')
const dateRangeText = computed(() => `${dateRange.value.start} → ${dateRange.value.end}`)
const dateRangeCompact = computed(() => `${dateRange.value.start.slice(5)}–${dateRange.value.end.slice(5)}`)
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
function toggleDatePicker() {
  dateRangeDraft.value = { ...dateRange.value }
  dateRangeError.value = ''
  datePickerOpen.value = !datePickerOpen.value
}
function setDatePreset(days: number) {
  if (!dateRangeDraft.value.end) return
  const end = new Date(`${dateRangeDraft.value.end}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() - days + 1)
  dateRangeDraft.value.start = end.toISOString().slice(0, 10)
}
function applyDateRange() {
  const range = dateRangeDraft.value
  const days = rangeDayCount(range)
  if (!days) {
    dateRangeError.value = '请选择有效的开始日期和结束日期。'
    return
  }
  if (days > 365) {
    dateRangeError.value = '一次最多查询 365 天，请缩短日期范围。'
    return
  }
  dateRange.value = { ...range }
  dateRangeError.value = ''
  datePickerOpen.value = false
}
function closeDatePickerOnOutside(event: PointerEvent) {
  if (datePickerOpen.value && !dateRangeControl.value?.contains(event.target as Node))
    datePickerOpen.value = false
}
function refreshWorkspaceList(offset = 0, term = listQuery.value) {
  return refreshConsultations(offset, term, dateRange.value.start, dateRange.value.end)
}
const globalSearch = ref<HTMLInputElement | null>(null)
const searchTerm = ref('')
function submitSearch() {
  const term = searchTerm.value.trim()
  navigate('workspace')
  query.value = term
}
const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
const serviceReviewDialogOpen = ref(false)
const drafts = ref<
  {
    evaluation_id: string
    finding_id: string
    decision: string
    reason: string
    created_at: string
    review_mode?: 'keep' | 'adjust'
    scores?: Record<string, number>
    total_score?: number
  }[]
>([])
const selected = computed(
  () => rows.value.find((r) => r.finding.finding_id === selectedId.value) || rows.value[0],
)
const queue = computed(() =>
  pending.value
    .sort(comparePriority),
)
const priorityFilter = ref<PriorityLevel | 'all'>('all')
const priorityCounts = computed(() =>
  Object.fromEntries(
    priorityLevels.map((level) => [
      level,
      (batchRuns.value.find((item) => item.mode === mode.value && isDateInRange(item.created_at, dateRange.value))?.sessions || [])
        .filter((item) => item.risk_level === level).length,
    ]),
  ),
)
const latestBatch = computed(() => batchRuns.value.find((item) => item.mode === mode.value && isDateInRange(item.created_at, dateRange.value)) || null)
const reviewSessions = computed(() => {
  const sessionDay = session.value?.messages[0]?.timestamp
  const fallbackItems = session.value && isDateInRange(sessionDay, dateRange.value) ? [{
    session_id: session.value.session_id,
    status: report.value?.status || 'partial',
    risk_level: report.value?.risk?.level ?? 'unknown' as const,
    pending_count: pending.value.length,
  }] : []
  const items = latestBatch.value?.sessions || fallbackItems
  const keyword = reviewMetricQuery.value.trim().toLowerCase()
  return items.filter((item) =>
    (priorityFilter.value === 'all' || item.risk_level === priorityFilter.value) &&
    item.session_id.toLowerCase().includes(keyword),
  )
})
const finalScore = computed(() => {
  const score = overallScore(report.value)
  return score === null ? null : score * 20
})
const reviewScoreMetrics = computed(() => metrics.map((metric) => ({
  code: metric.id,
  name: metric.name,
  score: rows.value.find((row) => row.finding.metric_id === metric.id)?.finding.score ?? null,
})))
const reviewMetricQuery = ref('')
const collapsedServiceMetricGroups = ref<string[]>([])
const activeServiceMetricCode = ref<string | null>(null)
const serviceMetricFilter = ref<'all' | 'attention'>('all')
const serviceReviewEvidenceIds = computed(() => [...new Set(
  rows.value.flatMap((row) => row.finding.evidence.flatMap((evidence) => evidence.message_ids)),
)])
const serviceReviewGroups = computed(() => dimensions.map((dimension) => {
  const items = metrics
    .filter((metric) => metric.id.startsWith(dimension.id))
    .map((metric) => {
      const row = rows.value.find((item) => item.finding.metric_id === metric.id)
      return { ...metric, score: row?.finding.score ?? null, row }
    })
  const scored = items.flatMap((item) => item.score === null ? [] : [item.score])
  return {
    ...dimension,
    items,
    average: scored.length ? scored.reduce((sum, value) => sum + value, 0) / scored.length : null,
  }
}))
const workspaceResultGroups = computed(() => serviceReviewGroups.value.map((group) => {
  const items = group.items.filter((item) => {
    const matchesDimension = filter.value === 'all' || filter.value === 'pending' || filter.value === group.id
    const matchesPending = filter.value !== 'pending' || (item.row
      ? pending.value.some((row) => row.finding.metric_id === item.id)
      : report.value?.status === 'failed')
    const text = `${item.id} ${item.name} ${item.row?.finding.rationale || ''}`.toLowerCase()
    return matchesDimension && matchesPending && text.includes(query.value.trim().toLowerCase())
  })
  const scored = items.flatMap((item) => item.score === null ? [] : [item.score])
  return {
    ...group,
    items,
    average: scored.length ? scored.reduce((sum, value) => sum + value, 0) / scored.length : null,
  }
}).filter((group) => group.items.length))
const visibleServiceReviewGroups = computed(() => serviceReviewGroups.value.map((group) => {
  const items = group.items.filter((item) =>
    serviceMetricFilter.value === 'all' || (item.score !== null && item.score < 3),
  )
  const scored = items.flatMap((item) => item.score === null ? [] : [item.score])
  return {
    ...group,
    items,
    average: scored.length ? scored.reduce((sum, value) => sum + value, 0) / scored.length : null,
  }
}).filter((group) => group.items.length))
const activeServiceMetric = computed(() =>
  serviceReviewGroups.value.flatMap((group) => group.items)
    .find((metric) => metric.id === activeServiceMetricCode.value) || null,
)
function toggleServiceMetricGroup(id: string) {
  collapsedServiceMetricGroups.value = collapsedServiceMetricGroups.value.includes(id)
    ? collapsedServiceMetricGroups.value.filter((group) => group !== id)
    : [...collapsedServiceMetricGroups.value, id]
}
function selectServiceMetric(id: string) {
  activeServiceMetricCode.value = activeServiceMetricCode.value === id ? null : id
}
function selectWorkspaceMetric(id: string) {
  selectServiceMetric(id)
  const row = rows.value.find((item) => item.finding.metric_id === id)
  if (row) select(row.finding.finding_id)
}
const resultIssueLabels: Record<string, string> = {
  metric_submission_rejected: '指标结果连续未通过后端校验',
  leader_planning_incomplete: '评价计划未完成，未能进入完整评分流程',
  insufficient_scored_coverage: '有效计分项不足，无法生成总分',
  finding_schema_error: '指标结果的数据格式不符合要求',
  'Score needs a Skill anchor and source-grounded claims': '评分缺少量表依据或原文证据',
  'Risk flag requires original evidence': '风险判断缺少原文证据',
  'Required reliable time facts missing': '缺少可靠的响应时间数据',
}
function resultIssueLabel(issue: string) {
  return resultIssueLabels[issue] || issue
}
function executionIssueLabel(issue: string) {
  return resultIssueLabels[issue] || issue.replaceAll('_', ' ')
}
function executionStageLabel(stage: string) {
  const labels: Record<string, string> = {
    leader_plan: '评价规划',
    initial_evaluation: '指标初评',
    leader_weight_scenario: '权重情境分析',
    leader_weight_distribution: '权重分布分析',
    leader_weight_relevance: '指标相关性分析',
  }
  return labels[stage] || stage.replaceAll('_', ' ')
}
const reviewOverallScore = computed(() => {
  const score = report.value?.quality_profile?.overall_score
  return score === null || score === undefined ? null : score * 20
})
const scoredCount = computed(() => rows.value.filter((r) => ['verified', 'agent_scored'].includes(r.verdict.code)).length)
const currentTitle = computed(() => nav.find((n) => n.id === page.value)?.name || '评估工作台')
const isDemoMapping = computed(() => rows.value.some((r) => /^D[1-6]$/.test(r.finding.metric_id)))
const localReview = computed(() => mode.value === 'preview' || listSource.value === 'uploaded')
const actionableDrafts = computed(() =>
  drafts.value.filter((d) => d.evaluation_id === report.value?.evaluation_id),
)
watch(
  () => [page.value, mode.value, dateRange.value.start, dateRange.value.end],
  ([activePage, activeMode]) => {
    if (activePage === 'workspace' && activeMode === 'service')
      void refreshWorkspaceList(0, listQuery.value)
  },
)
function focusMain() {
  document.getElementById('main')?.focus()
}
function rubricIcon(dimensionId: string) {
  return ({ D1: 'report', D2: 'zap', D3: 'message', D4: 'heart', D5: 'sparkle', D6: 'shield' } as Record<string, string>)[dimensionId] || 'list'
}
function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    globalSearch.value?.focus()
  }
  if (event.key === 'Escape' && mobileOpen.value) {
    mobileOpen.value = false
    nextTick(() => document.querySelector<HTMLButtonElement>('.mobile-menu')?.focus())
  }
  if (event.key === 'Escape' && datePickerOpen.value) datePickerOpen.value = false
}
function navigate(id: string) {
  page.value = id
  location.hash = id
  mobileOpen.value = false
  query.value = ''
}
function readHash() {
  const value = location.hash.slice(1)
  page.value = nav.some((n) => n.id === value) ? value : 'overview'
  mobileOpen.value = false
}
function notify(text: string) {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 5000)
}
function select(id: string) {
  selectedId.value = id
  highlightedIds.value = []
}
async function focusEvidence(ids: string[]) {
  if (!session.value) return notify('当前没有对应会话，无法定位证据。')
  const existing = ids.filter((id) => session.value!.messages.some((m) => m.message_id === id))
  if (existing.length !== ids.length) notify('部分引用消息在本次会话中不存在，请核对证据来源。')
  if (!existing.length) return
  highlightedIds.value = existing
  await nextTick()
  const target = document.getElementById(`message-${existing[0]}`)
  target?.scrollIntoView({
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    block: 'nearest',
  })
  target?.focus({ preventScroll: true })
}
async function start() {
  await runAll()
  if (batchProgress.value.total > 0) {
    selectedId.value = rows.value[0]?.finding.finding_id || ''
    notify(
      mode.value === 'preview'
        ? `已评估 ${batchProgress.value.succeeded}/${batchProgress.value.total} 条离线样例，未运行模型。`
        : `已评估 ${batchProgress.value.succeeded}/${batchProgress.value.total} 条真实咨询；请逐条查看报告与待复核项。`,
    )
  }
}
async function switchMode() {
  await setMode(mode.value === 'service' ? 'preview' : 'service')
  drafts.value = []
  highlightedIds.value = []
  selectedId.value = ''
}
async function openConsultation(id: string) {
  selectedId.value = ''
  highlightedIds.value = []
  await selectConsultation(id)
  await nextTick()
  document.getElementById('conversation-title')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}
async function openReportSession(id: string) {
  navigate('workspace')
  await openConsultation(id)
}
async function evaluateConsultation(id: string) {
  await selectConsultation(id)
  await runAll(id)
  if (report.value?.session_id === id) {
    selectedId.value = rows.value[0]?.finding.finding_id || ''
    await nextTick()
    document.getElementById('conversation-title')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }
}
function exportReport() {
  if (!report.value) return
  downloadJson(
    { mode: mode.value, exported_at: new Date().toISOString(), report: report.value },
    `心衡-${report.value.evaluation_id}.json`,
  )
  notify('已导出报告；包含证据引文，请按授权范围保管。')
}
async function saveDraft(review: ReviewScoreSubmission) {
  if (
    !report.value ||
    !selected.value ||
    review.totalScore < 0 || review.totalScore > 100 || review.note.trim().length < 10
  )
    return false
  const decision = review.decision === 'keep' ? '确认' : '建议修正'
  const reason = [
    `人工复核方式：${review.decision === 'keep' ? '维持原判' : '修改评分'}`,
    `复核总分：${review.totalScore.toFixed(1)}/100`,
    Object.keys(review.scores).length
      ? `指标修改：${Object.entries(review.scores).map(([code, score]) => `${code} 原 AI ${reviewScoreMetrics.value.find((metric) => metric.code === code)?.score?.toFixed(1) ?? '未评分'} → ${score.toFixed(1)}`).join('；')}`
      : '',
    `复核意见：${review.note}`,
  ].filter(Boolean).join('；')
  const input = {
    evaluation_id: report.value.evaluation_id,
    finding_id: selected.value.finding.finding_id,
    decision,
    reason,
  }
  try {
    const saved = localReview.value
      ? { ...input, created_at: new Date().toISOString() }
      : await api.addReview(input)
    drafts.value.push({ ...saved, review_mode: review?.decision, scores: review?.scores, total_score: review?.totalScore })
  } catch (error) {
    notify(`复核提交失败：${(error as Error).message}`)
    return false
  }
  serviceReviewDialogOpen.value = false
  notify(localReview.value ? '复核意见仅在当前页面保留。' : '复核意见已写入服务器，可刷新查看。')
  return true
}
watch(selectedId, () => { serviceReviewDialogOpen.value = false })
watch(sidebarCollapsed, (collapsed) => {
  try {
    window.localStorage.setItem('metric-integration-sidebar-collapsed', String(collapsed))
  } catch { /* 本地存储不可用时只保留当前会话状态。 */ }
})
watch(page, (value) => {
  if (
    value === 'review' &&
    pending.value.length &&
    !pending.value.some((r) => r.finding.finding_id === selectedId.value)
  )
    selectedId.value = [...pending.value].sort(comparePriority)[0]!.finding.finding_id
})
watch(queue, (value) => {
  if (page.value === 'review')
    selectedId.value =
      value.find((r) => r.finding.finding_id === selectedId.value)?.finding.finding_id ||
      value[0]?.finding.finding_id ||
      ''
})
watch(
  () => report.value?.evaluation_id,
  async (evaluationId) => {
    highlightedIds.value = []
    selectedId.value = ''
    serviceReviewDialogOpen.value = false
    drafts.value = []
    if (mode.value === 'service' && !localReview.value && evaluationId) {
      try {
        const saved = await api.reviews(evaluationId)
        if (report.value?.evaluation_id === evaluationId) drafts.value = saved.items
      } catch { /* PostgreSQL 不可用时表单提交仍会给出明确错误。 */ }
    }
  },
)
onMounted(() => {
  try {
    sidebarCollapsed.value = window.localStorage.getItem('metric-integration-sidebar-collapsed') === 'true'
  } catch { /* 浏览器禁用本地存储时仍可正常收缩侧栏。 */ }
  readHash()
  window.addEventListener('hashchange', readHash)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('pointerdown', closeDatePickerOnOutside)
  void initialize()
})
onUnmounted(() => {
  window.removeEventListener('hashchange', readHash)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointerdown', closeDatePickerOnOutside)
  clearTimeout(toastTimer)
})
</script>

<template>
  <a href="#main" class="skip-link" @click.prevent="focusMain">跳到主要内容</a>
  <div :class="['app-shell', { 'is-overview': page === 'overview', 'is-sidebar-collapsed': sidebarCollapsed }]">
    <button
      v-if="mobileOpen"
      class="nav-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    ></button>
    <aside :class="['sidebar', { open: mobileOpen }]">
      <a href="#overview" class="brand" @click.prevent="navigate('overview')"
        ><span class="brand-symbol"
          ><svg viewBox="0 0 40 40" width="30" height="30" aria-hidden="true">
            <path
              d="M20 33.5C13.4 29 7.5 24.4 7.5 18.4A7.1 7.1 0 0 1 20 13.6a7.1 7.1 0 0 1 12.5 4.8c0 6-5.9 10.6-12.5 15.1Z"
              fill="currentColor"
            />
            <path
              d="M20 13.6c-.4-4.6 2.4-7.6 7.3-8.6.5 4.8-2.4 7.9-7.3 8.6Z"
              fill="currentColor"
              opacity=".55"
            /></svg></span
        ><span class="brand-text"
          ><strong>心衡</strong><small>服务质量工作台</small></span
        ></a
      >
      <nav aria-label="主导航">
        <a
          v-for="item in nav"
          :key="item.id"
          :href="`#${item.id}`"
          :class="['nav-item', { active: page === item.id }]"
          :aria-current="page === item.id ? 'page' : undefined"
          :aria-label="item.name"
          :title="sidebarCollapsed ? item.name : undefined"
          @click.prevent="navigate(item.id)"
          ><Icon :name="item.icon" /><span class="nav-label">{{ item.name }}</span
          ><span v-if="item.id === 'review' && pending.length" class="nav-count">{{
            pending.length
          }}</span></a
        >
      </nav>
      <button
        class="sidebar-collapse-toggle"
        type="button"
        :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        :aria-expanded="!sidebarCollapsed"
        :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleSidebar"
      >
        <Icon name="chevron" :size="17" />
      </button>
      <svg class="sidebar-botanical" viewBox="0 0 240 280" fill="none" aria-hidden="true">
        <path
          d="M12 280C48 224 72 178 113 122S164 53 194 5"
          stroke="currentColor"
          stroke-width="2"
        />
        <path
          d="M74 188C19 188 9 152 25 126c30 2 55 30 49 62ZM101 143C142 147 172 118 166 95c-32-7-62 18-65 48ZM129 99C87 94 81 66 91 43c26 0 43 24 38 56ZM156 59C185 62 212 37 207 18c-27-4-49 18-51 41ZM47 234C6 240-5 207 1 187c26-4 47 21 46 47Z"
          fill="currentColor"
        />
      </svg>
      <div class="sidebar-bottom">
        <div class="operator">
          <span class="operator-avatar">检</span>
          <div><strong>管理员</strong><small>{{ mode === 'preview' ? '离线交互样例' : connected ? '服务已连接' : '等待服务连接' }}</small></div>
          <Icon name="chevron" :size="15" class="operator-caret" />
        </div>
        <div class="sidebar-service">
          <span :class="['connection-dot', { online: connected }]" aria-hidden="true"></span>
          <span class="sidebar-service-text">{{ mode === 'preview' ? '离线样例' : '服务已连接' }}</span>
        </div>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <button
          class="icon-button mobile-menu"
          aria-label="打开导航"
          :aria-expanded="mobileOpen"
          @click="mobileOpen = !mobileOpen"
        >
          <Icon name="menu" />
        </button>
        <form class="top-search" role="search" @submit.prevent="submitSearch">
          <Icon name="search" :size="19" />
          <input
            ref="globalSearch"
            v-model="searchTerm"
            type="search"
            placeholder="搜索患者 / 医生 / 任务编号…"
            aria-label="搜索会话编号"
          />
          <kbd class="top-kbd">⌘ K</kbd>
        </form>
        <div class="topbar-actions">
          <div ref="dateRangeControl" class="date-range-control">
            <button
              type="button"
              class="top-date"
              aria-haspopup="dialog"
              :aria-expanded="datePickerOpen"
              :aria-label="`选择统计日期范围，当前 ${dateRangeText}`"
              @click="toggleDatePicker"
            >
              <Icon name="calendar" :size="17" /><span class="date-range-full">{{ dateRangeText }}</span><span class="date-range-compact">{{ dateRangeCompact }}</span>
            </button>
            <form
              v-if="datePickerOpen"
              class="date-range-popover"
              role="dialog"
              aria-label="选择统计日期范围"
              @click.stop
              @submit.prevent="applyDateRange"
            >
              <strong>选择统计日期范围</strong>
              <div class="date-range-fields">
                <label>开始日期<input v-model="dateRangeDraft.start" type="date" required /></label>
                <span aria-hidden="true">至</span>
                <label>结束日期<input v-model="dateRangeDraft.end" type="date" required /></label>
              </div>
              <div class="date-range-presets" aria-label="快捷范围">
                <button type="button" @click="setDatePreset(7)">近 7 天</button>
                <button type="button" @click="setDatePreset(30)">近 30 天</button>
                <button type="button" @click="setDatePreset(90)">近 90 天</button>
              </div>
              <p v-if="dateRangeError" class="date-range-error" role="alert">{{ dateRangeError }}</p>
              <div class="date-range-actions">
                <button type="button" class="date-range-cancel" @click="datePickerOpen = false">取消</button>
                <button type="submit" class="date-range-apply">应用范围</button>
              </div>
            </form>
          </div>
          <button
            class="top-circle"
            :aria-label="`待复核 ${pending.length} 项`"
            @click="navigate('review')"
          >
            <Icon name="bell" :size="19" /><i v-if="pending.length" class="top-dot" />
          </button>
          <button
            class="mode-switch-button"
            :disabled="running || loading"
            :aria-label="mode === 'preview' ? '连接后端' : '切换到离线数据'"
            :title="mode === 'preview' ? '连接后端' : '切换到离线数据'"
            @click="switchMode"
          >
            {{ mode === 'preview' ? '连接后端' : '离线数据' }}
          </button>
          <div class="top-user">
            <span class="top-avatar" aria-hidden="true">检</span>
            <span class="top-user-name">管理员</span>
            <Icon name="chevron" :size="14" />
          </div>
        </div>
      </header>
      <main id="main" tabindex="-1" :class="{ 'overview-main': page === 'overview', 'workspace-main': page === 'workspace', 'profile-page-shell': page === 'profile' }">
        <div v-if="mode === 'preview' && !['workspace', 'reports', 'review', 'profile', 'rubrics', 'service'].includes(page)" class="mode-notice">
          <Icon name="info" :size="18" /><span
            >当前为离线交互样例。分数、核验与讨论均为预设合成数据，没有调用模型或写入服务器。</span
          >
        </div>
        <div v-if="!['overview', 'reports', 'workspace', 'review'].includes(page)" class="page-heading">
          <div>
            <h1>{{ currentTitle }}</h1>
            <p v-if="page !== 'workspace'">
              {{
                page === 'overview'
                  ? '汇总可信评分，了解服务质量与各维度表现。'
                  : page === 'workspace'
                    ? '评价已导入的真实咨询，再按订单核查依据。'
                    : page === 'reports'
                      ? '查看服务端运行记录与当前报告。'
                      : page === 'review'
                        ? '回到原文处理未决问题，保留原评价与修正理由。'
                        : page === 'profile'
                          ? '按医生聚合历史评价，追踪总分趋势与确定性预警。'
                          : page === 'rubrics'
                          ? '18 项指标各有唯一主责，原文引用与评分输入分别检查。'
                          : '分别检查服务存活、数据库连接和已接入能力。'
              }}
            </p>
          </div>
          <div v-if="page === 'workspace'" class="heading-actions">
            <button class="button secondary" @click="navigate('reports')">
              <Icon name="clock" :size="17" />历史任务</button>
          </div>
          <button
            v-else-if="page === 'reports'"
            class="button secondary"
            :disabled="mode === 'preview'"
            @click="refreshRecent"
          >
            <Icon name="refresh" :size="17" />刷新记录
          </button>
        </div>

        <OverviewPage
          v-if="page === 'overview'"
          :mode="mode"
          :refresh-key="lastRun"
          @navigate="navigate"
        />
        <EvaluationWorkspace
          v-else-if="page === 'workspace' && mode === 'preview'"
          @history="navigate('reports')"
          @notify="notify"
        />
        <template v-else-if="page === 'workspace' && mode === 'service'">
          <header class="service-workspace-heading">
            <div>
              <div class="service-workspace-title"><h1>评估工作台</h1><span class="service-workspace-badge"><i aria-hidden="true"></i>后端连接</span></div>
              <p>选择咨询会话，查看原文并启动多智能体服务质量评价。</p>
            </div>
            <div class="service-workspace-actions upload-actions">
              <button class="button secondary" type="button" @click="navigate('reports')"><Icon name="clock" :size="17" />历史任务</button>
              <button type="button" class="button secondary upload-button" :disabled="importing || running" @click="uploadInput?.click()">
                <Icon name="upload" :size="17" />{{ importing ? '上传中…' : '上传咨询数据' }}
              </button>
              <input id="workspace-session-import" ref="uploadInput" type="file" accept=".json,application/json" multiple :disabled="importing || running" @change="importSessions" />
              <span v-if="uploadPhase !== 'idle'" class="upload-progress" role="status">
                <Icon :name="uploadPhase === 'uploading' ? 'clock' : 'check'" :size="14" />{{ uploadPhase === 'uploading' ? '上传中' : '完成' }}
              </span>
              <button class="button primary" :disabled="!session || importing || loading || running" aria-label="一键评估列表中的咨询" @click="start">
                <Icon :name="running ? 'clock' : 'play'" :size="17" />{{ running ? `评估中 ${batchProgress.completed}/${batchProgress.total}` : report ? '重新评估' : '一键评估' }}
              </button>
            </div>
          </header>
          <p v-if="importMessage" class="upload-message service-upload-message" role="status">{{ importMessage }}</p>
          <div class="service-workspace-layout">
            <aside class="service-workspace-list">
              <ConsultationList
            :items="consultations"
            :total="totalConsultations"
            :offset="listOffset"
            :query="listQuery"
            :selected-id="session?.session_id"
            :loading="listing"
            :selecting="loading"
            :disabled="running"
            :error="listError"
            :source="listSource"
            @select="openConsultation"
            @evaluate="evaluateConsultation"
            @refresh="refreshWorkspaceList"
          />
            </aside>
            <section class="service-workspace-content">
          <div class="service-workspace-context">
          <div v-if="errors.session" class="alert danger" role="alert">
            <strong>咨询记录加载失败</strong>
            <p>{{ errors.session }}</p>
            <button class="text-button" @click="loadSession">重新加载</button>
            <button class="text-button" :disabled="running || loading" @click="switchMode">查看离线交互样例</button>
          </div>
          <div v-if="errors.run" class="alert danger" role="alert">
            <strong>本次请求未完成</strong>
            <p>{{ errors.run }}</p>
            <button class="text-button" @click="navigate('reports')">先查看最近运行记录</button>
            <p v-if="report" class="small">以下保留的是上一次返回的报告，不是本次请求的新结果。</p>
          </div>
          <section class="process-panel service-process-panel" aria-label="评估任务进度">
            <ol class="process-steps">
              <li :class="['process-step', { complete: !!session, active: !session }]">
                <span class="step-marker"><Icon v-if="session" name="check" :size="16" /><b v-else>1</b></span>
                <span class="step-copy"><strong>上传数据</strong><small>{{ session ? '咨询记录已加载' : '支持 JSON 格式' }}</small></span>
                <Icon class="step-arrow" name="chevron" :size="15" />
              </li>
              <li :class="['process-step', { complete: !!session, active: !!session && !report && !running }]">
                <span class="step-marker"><Icon v-if="session" name="check" :size="16" /><b v-else>2</b></span>
                <span class="step-copy"><strong>数据解析</strong><small>{{ session ? '校验与结构化完成' : '等待选择咨询' }}</small></span>
                <Icon class="step-arrow" name="chevron" :size="15" />
              </li>
              <li :class="['process-step', { complete: !!report, active: running }]">
                <span class="step-marker"><Icon v-if="report" name="check" :size="16" /><b v-else>3</b></span>
                <span class="step-copy"><strong>AI 评价中</strong><small>{{ running ? '正在等待后端结果' : report ? '评价结果已返回' : '多智能体协同评价' }}</small></span>
                <Icon class="step-arrow" name="chevron" :size="15" />
              </li>
              <li :class="['process-step', { complete: !!report, active: !!report }]">
                <span class="step-marker"><Icon v-if="report" name="check" :size="16" /><b v-else>4</b></span>
                <span class="step-copy"><strong>评价完成</strong><small>{{ report ? `${pending.length} 项待复核` : '生成结果与报告' }}</small></span>
              </li>
            </ol>
            <div class="process-progress">
              <div><span>{{ running ? '正在评估咨询' : report ? '本次评价流程' : '等待开始评估' }}</span><strong>{{ running && batchProgress.total ? Math.round((batchProgress.completed / batchProgress.total) * 100) : report ? 100 : 0 }}%</strong></div>
              <span class="progress-track" role="progressbar" aria-label="评估进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="running && batchProgress.total ? Math.round((batchProgress.completed / batchProgress.total) * 100) : report ? 100 : 0"><i :style="{ width: `${running && batchProgress.total ? Math.round((batchProgress.completed / batchProgress.total) * 100) : report ? 100 : 0}%` }"></i></span>
              <small><template v-if="session"><span class="session-identity">{{ session.session_id }}</span> · {{ session.messages.length }} 条消息 · {{ rows.length || 18 }} 项评价指标</template><template v-else>请从会话列表选择咨询，或上传 JSON 文件</template></small>
            </div>
          </section>
          <div v-if="listSource === 'access_required'" class="notice service-workspace-notice">
            上传 JSON 文件即可在本页评估；已有私有数据库记录仍需管理员授权查看。
          </div>
          <details v-if="report?.team" class="surface investigation-trace">
            <summary>本次评价用量 · {{ report.team.model_call_count }} 次模型请求</summary>
            <p v-if="report.team.usage?.usage_reported_requests" class="small">
              输入 {{ report.team.usage.prompt_tokens.toLocaleString() }} token，
              输出 {{ report.team.usage.completion_tokens.toLocaleString() }} token。
              {{ report.team.usage.usage_reported_requests }}/{{ report.team.usage.requests }} 次请求有供应商用量记录。
            </p>
            <p v-else class="small">此报告未采集到供应商 token 用量。重新评价后显示。</p>
          </details>
          <details v-if="report?.investigation" class="surface investigation-trace">
            <summary>调查轨迹 · {{ report.investigation.observations.length }} 步 · {{ report.investigation.stop_reason }}</summary>
            <p class="small">每一步展示业务疑问、执行动作及返回状态；不展示模型内部推理。</p>
            <p v-if="report.investigation.preflight_history?.required" class="small">
              复诊强制历史检索：{{ report.investigation.preflight_history.status }}
              <span v-if="report.investigation.preflight_history.issues.length">（{{ report.investigation.preflight_history.issues.join('、') }}）</span>
            </p>
            <p v-if="report.investigation.model_call_count !== undefined" class="small">
              模型请求：{{ report.investigation.model_call_count }}/{{ report.investigation.model_call_limit }}
            </p>
            <p v-if="report.investigation.metric_statuses" class="small">
              指标状态：{{ Object.values(report.investigation.metric_statuses).filter((x) => x === 'evaluated').length }} 项已评价，
              {{ Object.values(report.investigation.metric_statuses).filter((x) => x === 'not_applicable').length }} 项不适用，
              {{ Object.values(report.investigation.metric_statuses).filter((x) => x === 'insufficient_evidence').length }} 项证据不足，
              {{ Object.values(report.investigation.metric_statuses).filter((x) => x === 'manual_review').length }} 项待人工复核。
            </p>
            <ol>
              <li v-for="step in report.investigation.observations" :key="step.step">
                <strong>{{ step.step }}. {{ step.question }}</strong>
                <span>{{ step.action }} · {{ step.status }}</span>
                <small v-if="step.tool_name">工具：{{ step.tool_name }}</small>
                <small v-if="step.metric_ids?.length">指标：{{ step.metric_ids.join('、') }}</small>
                <small v-if="step.verification?.length">核验：{{ step.verification.map((v) => `${v.metric_id} ${v.status}`).join('、') }}</small>
                <small v-if="step.issues?.length">问题：{{ step.issues.join('、') }}</small>
              </li>
            </ol>
            <p v-if="report.investigation.uncovered_metric_ids.length" class="small">
              未覆盖指标：{{ report.investigation.uncovered_metric_ids.join('、') }}；须人工复核。
            </p>
          </details>
          <p v-if="running" class="run-note" role="status">
            已完成 {{ batchProgress.completed }}/{{ batchProgress.total }} 条；成功
            {{ batchProgress.succeeded }} 条，失败 {{ batchProgress.failed }} 条。
            <span v-if="batchProgress.currentId">当前订单：{{ batchProgress.currentId }}。</span>
            每条订单完成后更新进度，模型内部步骤仍以报告为准。
          </p>
          <p v-else-if="batchProgress.total" class="run-note" role="status">
            本次批量评估完成 {{ batchProgress.completed }}/{{ batchProgress.total }} 条；成功
            {{ batchProgress.succeeded }} 条，失败 {{ batchProgress.failed }} 条。
          </p>
          </div>
          <ConversationPanel :session="session" :highlighted-ids="highlightedIds" :show-view-toggle="true" />
            </section>
            <section class="results-panel workspace-panel ai-panel" aria-labelledby="results-title">
              <div class="panel-title-row">
                <div>
                  <h2 id="results-title">AI 评价结果</h2>
                  <p>
                    {{ report ? `18 项服务质量指标 · ${scoredCount} 项已计分` : '18 项服务质量指标' }}
                  </p>
                </div>
                <span :class="['result-status', report ? report.status : 'pending']"><Icon :name="!report ? 'clock' : report.status === 'failed' ? 'alert' : 'check'" :size="13" />{{ !report ? '等待评估' : report.status === 'failed' ? '评估失败' : report.status === 'partial' ? '部分完成' : '待复核' }}</span>
              </div>
              <div v-if="!report" class="empty-state report-empty">
                <div class="empty-illustration">
                  <Icon name="report" :size="42" /><span><Icon name="shield" :size="24" /></span>
                </div>
                <h3>让每条评价都有依据</h3>
                <p>
                  开始评估后，可查看 Agent 评分、评价理由与对应原话。未解决的问题会保留到复核列表。
                </p>
                <button
                  class="button primary"
                  :disabled="!session || running || loading"
                  @click="start"
                >
                  {{ running ? '正在批量评估…' : '一键自动评估' }}
                </button>
                <div class="empty-capabilities">
                  <span><Icon name="check" :size="15" />唯一指标主责</span
                  ><span><Icon name="check" :size="15" />原文证据追溯</span
                  ><span><Icon name="check" :size="15" />未决问题保留</span>
                </div>
              </div>
              <template v-else>
                <div class="result-summary">
                  <div class="overall-score">
                    <span class="score-icon"><Icon name="medal" :size="20" /></span>
                    <div><small>综合得分</small><strong>{{ finalScore === null ? '—' : finalScore.toFixed(1) }}<em>/ 100</em></strong></div>
                  </div>
                  <div class="ai-conclusion"><strong>AI 评价结论</strong><p>{{ report.summary || '本次评价未提供总结。' }}</p></div>
                </div>
                <div class="summary-counts workspace-result-counts">
                  <span><strong>{{ scoredCount }} / 18</strong>已计分指标</span>
                  <span><strong>{{ pending.length }}</strong>待核查指标</span>
                  <span><strong>{{ finalScore === null ? '—' : finalScore.toFixed(1) }}</strong>综合总分（满分 100）</span>
                </div>
                <p v-if="report.status === 'failed'" class="workspace-result-failure" role="status">
                  <Icon name="alert" :size="15" />本次评价未完成，未生成可信总分。请查看下方校验原因后重试。
                </p>
                <p v-else-if="finalScore === null" class="small score-gate-note">
                  尚不满足综合评分展示条件；前端不会自行平均 Agent 分数。
                </p>
                <p v-if="isDemoMapping" class="mapping-note">
                  当前后端包含维度级演示条目，不能视为 18 项正式指标已全部实现。
                </p>
                <div class="filter-toolbar">
                  <label class="search-field"
                    ><Icon name="search" :size="16" /><input
                      v-model="query"
                      aria-label="搜索评价指标"
                      placeholder="搜索指标或评价理由" /></label
                  ><select v-model="filter" aria-label="筛选评价维度">
                    <option value="all">全部指标</option>
                    <option value="pending">待核查</option>
                    <option v-for="d in dimensions" :key="d.id" :value="d.id">{{ d.id }} {{ d.name }}</option>
                  </select>
                </div>
                <div class="metric-groups workspace-result-groups" aria-label="六维评价结果">
                  <section v-for="group in workspaceResultGroups" :key="group.id" :class="['metric-group', `group-${group.id.toLowerCase()}`]">
                    <button class="metric-group-heading" type="button" :aria-expanded="!collapsedServiceMetricGroups.includes(group.id)" @click="toggleServiceMetricGroup(group.id)">
                      <span class="group-icon"><Icon :name="group.id === 'D1' ? 'shield' : group.id === 'D2' ? 'clock' : group.id === 'D3' ? 'message' : group.id === 'D4' ? 'heart' : group.id === 'D5' ? 'workspace' : 'alert'" :size="15" /></span>
                      <strong>{{ group.id }} {{ group.name }}<small>（{{ group.items.length }} 项）</small></strong>
                      <b>{{ group.average === null ? '—' : group.average.toFixed(1) }}</b><Icon class="group-chevron" name="chevron" :size="13" />
                    </button>
                    <div v-show="!collapsedServiceMetricGroups.includes(group.id)" class="metric-list">
                      <button v-for="item in group.items" :key="item.id" :class="['metric-row', { active: activeServiceMetricCode === item.id }]" type="button" :aria-pressed="activeServiceMetricCode === item.id" :aria-label="`${item.id} ${item.name}，${item.score === null ? '本次未返回评分' : `评分 ${item.score.toFixed(1)} 分`}`" @click="selectWorkspaceMetric(item.id)">
                        <span>{{ item.id }}</span><span class="metric-name">{{ item.name }}</span>
                        <i aria-hidden="true"><b :style="{ width: `${(item.score ?? 0) * 20}%` }"></b></i>
                        <strong>{{ item.score === null ? '—' : item.score.toFixed(1) }}</strong>
                      </button>
                    </div>
                  </section>
                  <p v-if="!workspaceResultGroups.length" class="empty-note padded">没有匹配的指标，请调整搜索或筛选条件。</p>
                </div>
                <div v-if="activeServiceMetric" class="metric-detail">
                  <div><span>{{ activeServiceMetric.id }}</span><strong>{{ activeServiceMetric.name }}</strong><b>{{ activeServiceMetric.score === null ? '未评分' : `${activeServiceMetric.score.toFixed(1)} / 5` }}</b></div>
                  <p>{{ activeServiceMetric.row?.finding.rationale || '本次运行未返回该指标的有效评价。' }}</p>
                  <button v-if="activeServiceMetric.row" type="button" :disabled="!activeServiceMetric.row.finding.evidence.length" @click="focusEvidence(activeServiceMetric.row.finding.evidence.flatMap((evidence) => evidence.message_ids))"><Icon name="link" :size="13" />查看原文证据</button>
                </div>
                <details v-if="activeServiceMetric?.row" class="service-review-evidence"><summary>查看完整核查详情</summary><FindingDetail :row="activeServiceMetric.row" :report="report" :session="session" @focus="focusEvidence" /></details>
                <details class="report-limitations">
                  <summary>评价说明与待核查原因</summary>
                  <ul>
                    <li
                      v-for="(item, i) in [...report.limitations, ...report.review_reasons]"
                      :key="i"
                    >
                      {{ resultIssueLabel(item) }}
                    </li>
                    <li v-if="!report.limitations.length && !report.review_reasons.length">
                      后端没有返回限制项，不代表全部核验已经完成。
                    </li>
                  </ul>
                  <p v-for="a in report.agent_results.filter((a) => a.error)" :key="a.agent_id">
                    {{ agentName(a.agent_id) }}：{{ a.error }}
                  </p>
                </details>
                <details v-if="report.execution_issues?.length" class="report-limitations execution-issues">
                  <summary>运行校验详情 · {{ report.execution_issues.length }} 项</summary>
                  <ul>
                    <li v-for="(issue, index) in report.execution_issues" :key="`${issue.stage}-${issue.metric_id}-${index}`">
                      <strong>{{ executionStageLabel(issue.stage) }}<template v-if="issue.metric_id"> · {{ issue.metric_id }}</template></strong>：{{ executionIssueLabel(issue.error) }}
                      <small v-if="issue.fields.length">字段 {{ issue.fields.map((field) => `${field.path.join('.') || '输入'} (${field.type})`).join('、') }}</small>
                    </li>
                  </ul>
                </details>
              </template>
            </section>
          </div>
        </template>

        <OfflineReportsPage
          v-else-if="page === 'reports' && mode === 'preview'"
          @notify="notify"
        />
        <ServiceReportsPage
          v-else-if="page === 'reports' && mode === 'service'"
          :latest-batch="latestBatch"
          :report="report"
          :recent="recent"
          :recent-error="errors.recent"
          :connected="connected"
          :last-run="lastRun"
          @open-session="openReportSession"
          @export-report="exportReport"
          @navigate="navigate"
          @refresh="refreshRecent"
        />

        <OfflineReviewPage
          v-else-if="page === 'review' && mode === 'preview'"
          @navigate="navigate"
          @notify="notify"
        />
        <template v-else-if="page === 'review' && mode === 'service'">
          <div class="review-page service-review-page">
            <header class="review-heading">
              <div><h1>人工复核</h1><p>核对后端返回的会话原文、AI 评分和相关证据。</p></div>
              <button class="review-action secondary" type="button" :disabled="!actionableDrafts.length" @click="downloadJson({ scope: 'local-draft-not-submitted', drafts: actionableDrafts }, '心衡-复核草稿.json')"><Icon name="download" :size="16" />导出复核草稿</button>
            </header>

            <section class="review-stats service-review-stats" aria-label="复核统计">
              <button type="button" :class="['stat-card', 'total', { active: priorityFilter === 'all' }]" :aria-pressed="priorityFilter === 'all'" @click="priorityFilter = 'all'"><span class="stat-icon"><Icon name="message" :size="20" /></span><div><small>待复核会话</small><strong>{{ latestBatch?.sessions.length ?? (session ? 1 : 0) }}</strong><span>当前评价批次</span></div><i aria-hidden="true"></i></button>
              <button v-for="level in priorityLevels" :key="level" type="button" :class="['stat-card', level, { active: priorityFilter === level }]" :aria-pressed="priorityFilter === level" @click="priorityFilter = level"><span class="stat-icon"><Icon :name="level === 'high' ? 'alert' : level === 'medium' ? 'clock' : 'check'" :size="20" /></span><div><small>{{ priorityNames[level] }}风险会话</small><strong>{{ priorityCounts[level] }}</strong><span>{{ level === 'high' ? '优先核对证据与结论' : level === 'medium' ? '需要进一步确认' : '常规核查' }}</span></div><i aria-hidden="true"></i></button>
            </section>

            <div v-if="report" class="review-layout service-review-grid">
              <section class="review-panel session-panel" aria-labelledby="service-review-list-title">
                <div class="panel-title-row"><div><h2 id="service-review-list-title">待复核会话列表</h2><p>{{ reviewSessions.length }} 条后端会话</p></div><span class="panel-count">{{ latestBatch?.sessions.length ?? reviewSessions.length }}</span></div>
                <div class="review-filters">
                  <label class="review-search"><Icon name="search" :size="16" /><input v-model="reviewMetricQuery" type="search" placeholder="搜索会话 ID" aria-label="搜索待复核会话" /></label>
                  <button type="button" :class="['filter-button', { active: priorityFilter !== 'all' }]" aria-label="切换风险筛选" :aria-pressed="priorityFilter !== 'all'" @click="priorityFilter = priorityFilter === 'all' ? 'high' : 'all'"><Icon name="list" :size="15" /></button>
                </div>
                <div class="risk-tabs" role="group" aria-label="风险筛选">
                  <button type="button" :class="{ active: priorityFilter === 'all' }" :aria-pressed="priorityFilter === 'all'" @click="priorityFilter = 'all'">全部 {{ latestBatch?.sessions.length ?? (session ? 1 : 0) }}</button>
                  <button v-for="level in priorityLevels" :key="level" type="button" :class="{ active: priorityFilter === level }" :aria-pressed="priorityFilter === level" @click="priorityFilter = level">{{ priorityNames[level] }} {{ priorityCounts[level] }}</button>
                </div>
                <div class="review-list">
                  <button v-for="item in reviewSessions" :key="item.session_id" :class="['review-item', `risk-${item.risk_level}`, { selected: session?.session_id === item.session_id }]" :data-priority="item.risk_level" :aria-pressed="session?.session_id === item.session_id" type="button" @click="openConsultation(item.session_id)">
                    <span class="review-item-top"><strong>{{ item.session_id }}</strong><span :class="['risk-badge', item.risk_level]"><i aria-hidden="true"></i>{{ item.risk_level === 'unknown' ? '风险未知' : `${priorityNames[item.risk_level]}风险` }}</span></span>
                    <span class="review-item-meta"><span>{{ item.pending_count }} 项待核查</span><time>{{ label(item.status) }}</time></span>
                  </button>
                  <div v-if="!reviewSessions.length" class="review-empty"><Icon name="search" :size="24" /><strong>没有匹配会话</strong><p>调整关键词或风险筛选。</p><button type="button" @click="reviewMetricQuery = ''; priorityFilter = 'all'">清除筛选</button></div>
                </div>
                <footer class="review-pagination"><span>{{ reviewSessions.length }} 个会话 · {{ reviewSessions.reduce((sum, item) => sum + item.pending_count, 0) }} 项待核查</span></footer>
              </section>

              <ConversationPanel :session="session" :highlighted-ids="highlightedIds" :show-view-toggle="true" :initial-message-count="6" :evidence-message-ids="serviceReviewEvidenceIds" @locate-evidence="focusEvidence([$event])" />

              <aside class="review-side">
                <section class="review-panel result-panel" aria-labelledby="service-review-result-title">
                  <div class="panel-title-row result-heading"><div><h2 id="service-review-result-title">AI 评价结果</h2><p>{{ session?.messages.length ?? 0 }} 条消息 · 18 项指标</p></div><div class="result-heading-actions"><span :class="['result-risk', report.risk?.level || 'unknown']"><i aria-hidden="true"></i>{{ report.risk?.level === 'unknown' || !report.risk ? '风险未知' : `${priorityNames[report.risk.level]}风险` }}</span><button class="result-review-button" type="button" @click="serviceReviewDialogOpen = true"><Icon name="shield" :size="15" />人工复核</button></div></div>
                  <div class="result-summary">
                    <div class="overall-score"><span class="score-icon"><Icon name="medal" :size="20" /></span><div><small>综合得分</small><strong>{{ reviewOverallScore === null ? '—' : reviewOverallScore.toFixed(1) }}<em>/ 100</em></strong></div></div>
                    <div class="ai-conclusion"><strong>AI 评价结论</strong><p>{{ report.summary || report.review_reasons.join('；') || '当前报告没有返回文字结论，可结合各项指标与原文证据核对。' }}</p></div>
                  </div>
                  <div class="metric-toolbar"><strong>18 项评价指标</strong><select v-model="serviceMetricFilter" aria-label="筛选评价指标"><option value="all">全部指标</option><option value="attention">重点关注（低于 3 分）</option></select></div>
                  <div class="metric-groups service-metric-groups">
                    <section v-for="group in visibleServiceReviewGroups" :key="group.id" :class="['metric-group', `group-${group.id.toLowerCase()}`]">
                      <button class="metric-group-heading" type="button" :aria-expanded="!collapsedServiceMetricGroups.includes(group.id)" @click="toggleServiceMetricGroup(group.id)"><span class="group-icon"><Icon :name="group.id === 'D1' ? 'shield' : group.id === 'D2' ? 'clock' : group.id === 'D3' ? 'message' : group.id === 'D4' ? 'heart' : group.id === 'D5' ? 'workspace' : 'alert'" :size="15" /></span><strong>{{ group.id }} {{ group.name }}</strong><b>{{ group.average === null ? '—' : group.average.toFixed(1) }}</b><Icon class="group-chevron" name="chevron" :size="13" /></button>
                      <div v-show="!collapsedServiceMetricGroups.includes(group.id)" class="metric-list">
                        <button v-for="item in group.items" :key="item.id" :class="['metric-row', { active: activeServiceMetricCode === item.id }]" type="button" :aria-pressed="activeServiceMetricCode === item.id" @click="selectServiceMetric(item.id)"><span>{{ item.id }}</span><span class="metric-name">{{ item.name }}</span><i><b :style="{ width: `${(item.score ?? 0) * 20}%` }"></b></i><strong :class="{ low: item.score !== null && item.score < 3 }">{{ item.score === null ? '—' : item.score.toFixed(1) }}</strong></button>
                      </div>
                    </section>
                  </div>
                  <div v-if="activeServiceMetric" class="metric-detail"><div><span>{{ activeServiceMetric.id }}</span><strong>{{ activeServiceMetric.name }}</strong><b>{{ activeServiceMetric.score === null ? '未评分' : `${activeServiceMetric.score.toFixed(1)} / 5` }}</b></div><p>{{ activeServiceMetric.row?.finding.rationale || '当前指标没有返回评分理由。' }}</p><button v-if="activeServiceMetric.row" type="button" :disabled="!activeServiceMetric.row.finding.evidence.length" @click="focusEvidence(activeServiceMetric.row.finding.evidence.flatMap((evidence) => evidence.message_ids))"><Icon name="link" :size="13" />查看原文证据</button></div>
                  <details v-if="activeServiceMetric?.row" class="service-review-evidence"><summary>查看完整核查详情</summary><FindingDetail :row="activeServiceMetric.row" :report="report" :session="session" @focus="focusEvidence" /></details>
                </section>
              </aside>
            </div>
            <div v-else class="surface review-range-empty"><Icon name="shield" :size="28" /><strong>先完成一次评估</strong><p>评估工作台返回结果后，会在这里展示会话原文、AI 评分与复核入口。</p><button class="button primary" type="button" @click="navigate('workspace')">前往评估工作台</button></div>
          </div>
          <ReviewScoreDialog
            v-if="serviceReviewDialogOpen && report"
            :title="session ? `会话 ${session.session_id}` : '本次服务评价'"
            :metrics="reviewScoreMetrics"
            :overall-score="reviewOverallScore"
            :offline="localReview"
            @close="serviceReviewDialogOpen = false"
            @submit="saveDraft"
          />
        </template>

        <ProfilePage
          v-else-if="page === 'profile'"
          :mode="mode"
          :refresh-key="lastRun"
        />

        <template v-else-if="page === 'rubrics'">
          <div class="rubrics-page">
          <div class="rubric-grid">
            <section v-for="d in dimensions" :key="d.id" :class="['surface', 'rubric-section', `rubric-${d.id.toLowerCase()}`]">
              <div class="panel-header">
                <h2>
                  <span class="rubric-dimension-icon"><Icon :name="rubricIcon(d.id)" :size="21" /></span>
                  <span>{{ d.id }} {{ d.name }}</span>
                </h2>
                <small>{{ metrics.filter((m) => m.id.startsWith(d.id)).length }} 项指标</small>
              </div>
              <div
                v-for="m in metrics.filter((m) => m.id.startsWith(d.id))"
                :key="m.id"
                class="rubric-item"
              >
                <span class="metric-code">{{ m.id }}</span>
                <strong>{{ m.name }}</strong>
                <span class="draft-label">已发布</span>
              </div>
            </section>
          </div>
          </div>
        </template>

        <template v-else-if="page === 'service'">
          <div class="service-settings-page">
          <section class="surface connection-panel">
            <div class="panel-header">
              <div>
                <h2>服务可用性</h2>
                <p>检查服务、数据库类型与模型配置。</p>
              </div>
              <button
                class="button secondary"
                :disabled="checking || mode === 'preview'"
                @click="checkService"
              >
                <Icon name="refresh" :size="17" />{{ checking ? '检查中…' : '重新检查' }}
              </button>
            </div>
            <dl class="connection-facts">
              <div>
                <dt>应用进程</dt>
                <dd>
                  <StatusBadge :tone="connected ? 'success' : 'warning'">{{
                    mode === 'preview' ? '离线预览' : connected ? '响应正常' : '尚未确认'
                  }}</StatusBadge>
                </dd>
              </div>
              <div>
                <dt>数据库</dt>
                <dd>
                  <StatusBadge :tone="ready?.database.connected ? 'success' : 'warning'">{{
                    ready?.database.connected
                      ? `连接正常 · ${ready.database.backend === 'postgresql' ? 'PostgreSQL' : ready.database.backend === 'sqlite' ? 'SQLite' : '类型未知'}`
                      : ready?.database.configured
                        ? '已配置，连接未确认'
                        : '未配置或状态未知'
                  }}</StatusBadge>
                </dd>
              </div>
              <div>
                <dt>评价模型</dt>
                <dd>
                  <StatusBadge :tone="ready?.model?.configured ? 'success' : 'warning'">{{
                    ready?.model?.configured ? '已配置' : ready?.model ? '未配置密钥' : '状态未知'
                  }}</StatusBadge>
                </dd>
              </div>
              <div>
                <dt>最近检查</dt>
                <dd>{{ time(lastChecked, true) }}</dd>
              </div>
              <div>
                <dt>接口方式</dt>
                <dd>{{ separateBackend ? '独立后端 API' : '同源 API' }}，不在前端保存密钥</dd>
              </div>
            </dl>
            <p v-if="errors.ready" class="notice danger">{{ errors.ready }}</p>
          </section>
          <section class="surface capability-panel">
            <div class="panel-header"><h2>私有数据访问</h2></div>
            <p class="small">使用管理员配置的访问令牌查看真实订单样本。令牌仅在当前页面内存中保存，刷新后需重新输入。</p>
            <form @submit.prevent="applyPrivateAccess">
              <label for="private-access-token">访问令牌</label>
              <input id="private-access-token" v-model="privateToken" type="password" autocomplete="off" placeholder="输入访问令牌" />
              <button class="button secondary" type="submit" :disabled="running || importing || mode === 'preview'">应用访问设置</button>
              <button v-if="privateAccessEnabled" class="button secondary" type="button" :disabled="running" @click="privateToken = ''; applyPrivateAccess()">清除访问令牌</button>
            </form>
            <p class="small">{{ privateAccessEnabled ? '已设置访问令牌，是否有效以接口响应为准。' : '未设置：真实会话列表不会显示。' }}</p>
          </section>
          <section class="surface capability-panel">
            <div class="panel-header"><h2>功能接入边界</h2></div>
            <div class="capability-row">
              <span
                ><strong>真实会话导入、评价请求与最近记录</strong
                ><small>工作台上传文件无需令牌；管理员数据库记录仍需授权读取。</small></span
              ><StatusBadge>已有接口</StatusBadge>
            </div>
            <div class="capability-row">
              <span
                ><strong>Agent 评价与评分</strong
                ><small>后端直接汇总 Agent 提交且符合输入约束的评分；未设置独立语义核验环节。</small></span
              ><StatusBadge>已接入</StatusBadge>
            </div>
            <div class="capability-row">
              <span
                ><strong>修正讨论与分歧仲裁</strong
                ><small>事实冲突交由 Team Lead 仲裁；报告展示实际产生的记录与未解决状态。</small></span
              ><StatusBadge>按需运行</StatusBadge>
            </div>
            <div class="capability-row">
              <span
                ><strong>真实数据导入与复核提交</strong
                ><small>已提供管理员令牌保护的逐会话导入与复核记录；多用户登录及权限分级仍待接入。</small></span
              ><StatusBadge tone="warning">部分接入</StatusBadge>
            </div>
            <a
              class="button secondary docs-link"
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              >查看后端接口文档<Icon name="arrow" :size="16"
            /></a>
          </section>
          </div>
        </template>
        <footer class="page-footer">
          <span>心衡 · 服务质量辅助评估</span>
          <p>{{ mode === 'preview' ? '当前为离线合成数据演示。' : listSource === 'uploaded' ? '本页上传的会话与报告刷新后会清除。' : '数据库中的真实会话仅供授权访问。' }} 正式结论需核查证据与适用规则，并由授权人员复核。</p>
        </footer>
      </main>
    </div>
    <div v-if="toast" class="toast" role="status" aria-live="polite">
      <Icon name="info" :size="18" />{{ toast
      }}<button class="icon-button" aria-label="关闭提示" @click="toast = ''">
        <Icon name="close" :size="16" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.service-workspace-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin: 0 0 20px;
  color: #19372b;
}
.service-workspace-title { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }
.service-workspace-title h1 { color: #19372b; font-size: 31.5px; font-weight: 700; line-height: 1.35; letter-spacing: -0.02em; }
.service-workspace-heading p { margin-top: 7px; color: #65786d; font-size: 15.5px; line-height: 1.7; }
.service-workspace-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border: 1px solid #d7e8dc;
  border-radius: 999px;
  background: #f4faf5;
  color: #397153;
  font-size: 13.5px;
  font-weight: 500;
}
.service-workspace-badge i { width: 6px; height: 6px; border-radius: 50%; background: #48a677; }
.service-workspace-actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px; }
.service-workspace-actions > .button { min-height: 40px; padding: 9px 15px; border-radius: 8px; font-size: 14.5px; }
.service-workspace-actions input[type='file'] { position: absolute; width: 1px; height: 1px; opacity: 0; }
.service-workspace-actions .upload-progress { display: inline-flex; align-items: center; gap: 5px; padding: 6px 9px; border-radius: 7px; background: #eef7f0; color: #397153; }
.service-upload-message { margin: -6px 0 14px; }
.service-workspace-layout {
  display: grid;
  grid-template-columns: minmax(275px, 0.8fr) minmax(390px, 1.2fr) minmax(390px, 1.1fr);
  grid-template-areas: 'context context context' 'list conversation results';
  grid-template-rows: auto clamp(620px, calc(100vh - 284px), 790px);
  align-items: stretch;
  gap: 16px 18px;
}
.service-workspace-list { grid-area: list; position: static; min-width: 0; min-height: 0; height: 100%; }
.service-workspace-content { display: contents; }
.service-workspace-context { grid-area: context; display: grid; align-content: start; gap: 12px; min-width: 0; }
.service-process-panel {
  display: flex;
  align-items: center;
  gap: 22px;
  min-height: 88px;
  margin-bottom: 0;
  padding: 16px 20px;
  border: 1px solid #dfe9e2;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.88);
}
.service-process-panel .process-steps { display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); flex: 1; min-width: 0; padding: 0; margin: 0; list-style: none; }
.service-process-panel .process-step { position: relative; display: flex; align-items: center; gap: 10px; min-width: 0; }
.service-process-panel .step-marker { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; border: 1px solid #dce5df; border-radius: 50%; background: #f1f4f2; color: #7b8a80; font-size: 13.5px; }
.service-process-panel .step-marker b { font-weight: 600; }
.service-process-panel .process-step.complete .step-marker { border-color: #28a36f; background: #28a36f; color: #fff; }
.service-process-panel .process-step.active .step-marker { border-color: #8bc7a8; background: #eaf6ee; color: #0e6d4b; box-shadow: 0 0 0 4px #f1f8f3; }
.service-process-panel .step-copy { display: grid; min-width: 0; gap: 2px; }
.service-process-panel .step-copy strong { color: #334c3d; font-size: 14.5px; font-weight: 650; white-space: nowrap; }
.service-process-panel .step-copy small { overflow: hidden; color: #7a8b80; font-size: 12.5px; text-overflow: ellipsis; white-space: nowrap; }
.service-process-panel .step-arrow { margin: 0 12px 0 auto; color: #bdc9c0; }
.service-process-panel .process-progress { flex: 0 0 190px; padding-left: 20px; border-left: 1px solid #dfe9e2; }
.service-process-panel .process-progress > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 7px; color: #597060; font-size: 12.5px; }
.service-process-panel .process-progress strong { color: #0e6d4b; font-size: 13.5px; font-variant-numeric: tabular-nums; }
.service-process-panel .progress-track { display: block; height: 5px; overflow: hidden; border-radius: 4px; background: #e8efe9; }
.service-process-panel .progress-track i { display: block; height: 100%; border-radius: inherit; background: #35a875; transition: width 160ms ease-out; }
.service-process-panel .process-progress small { display: block; overflow: hidden; margin-top: 6px; color: #74877a; font-size: 12.5px; text-overflow: ellipsis; white-space: nowrap; }
.service-workspace-notice { margin: 0; }
.service-workspace-content :deep(.service-conversation-panel) {
  grid-area: conversation;
  position: static;
  min-width: 0;
  min-height: 0;
  height: 100%;
  max-height: none;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.service-workspace-content :deep(.service-conversation-panel .conversation-list),
.service-workspace-content :deep(.service-conversation-panel .structured-view) { flex: 1 1 auto; min-height: 0; max-height: none; overflow: auto; }
.service-workspace-content :deep(.service-conversation-panel .message-bubble) { font-size: 14px; line-height: 1.75; }
.service-workspace-layout > .results-panel { grid-area: results; display: flex; flex-direction: column; min-width: 0; min-height: 0; height: 100%; max-height: none; overflow: auto; }
.service-workspace-layout > .results-panel > .panel-title-row { position: sticky; top: 0; z-index: 1; flex: 0 0 auto; background: rgba(255, 255, 255, 0.98); }
.service-workspace-layout > .results-panel > .empty-state { flex: 1; min-height: 0; }
.service-workspace-layout > .results-panel .finding-list { max-height: none; }
.service-workspace-layout > .results-panel .report-summary { margin-top: 14px; }
.service-workspace-layout > .results-panel .result-status.partial { background: #fff2db; color: #9c6b1d; }
.service-workspace-layout > .results-panel .result-status.failed { background: #fbe9e9; color: #a94b53; }
.service-workspace-layout > .results-panel .result-summary { margin: 13px 13px 0; }
.service-workspace-layout > .results-panel .workspace-result-counts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 9px 13px 0;
}
.service-workspace-layout > .results-panel .workspace-result-counts > span {
  display: grid;
  align-content: start;
  gap: 2px;
  width: auto;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid #e5eee8;
  border-radius: 7px;
  background: #f7fbf8;
  color: #687d6e;
  font-size: 11.5px;
}
.service-workspace-layout > .results-panel .workspace-result-counts > span + span { border-right: 1px solid #e5eee8; }
.service-workspace-layout > .results-panel .workspace-result-counts strong {
  color: #1d7550;
  font-size: 16px;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
}
.workspace-result-failure {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 9px 13px 0;
  padding: 8px 10px;
  border: 1px solid #f0d8d9;
  border-radius: 7px;
  background: #fff5f5;
  color: #a34f56;
  font-size: 12px;
  line-height: 1.55;
}
.workspace-result-failure :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.service-workspace-layout > .results-panel .score-gate-note { margin: 8px 13px 0; font-size: 12px; }
.service-workspace-layout > .results-panel .workspace-result-groups {
  flex: 0 0 auto;
  max-height: min(46vh, 440px);
  overflow-y: auto;
}
.service-workspace-layout > .results-panel .workspace-result-groups .metric-row { grid-template-columns: 42px minmax(0, 1fr) 62px 36px; }
.service-workspace-layout > .results-panel .execution-issues li { margin-bottom: 8px; }
.service-workspace-layout > .results-panel .execution-issues small { display: block; margin-top: 3px; color: #6d8173; overflow-wrap: anywhere; }
@media (max-width: 1350px) {
  .service-workspace-layout {
    grid-template-columns: minmax(250px, 0.76fr) minmax(360px, 1.24fr);
    grid-template-areas: 'context context' 'list conversation' 'results results';
    grid-template-rows: auto 640px auto;
    gap: 16px;
  }
  .service-workspace-layout > .results-panel { height: auto; min-height: 540px; max-height: none; }
  .service-workspace-layout > .results-panel .workspace-result-groups { max-height: min(62vh, 560px); }
  .service-process-panel { align-items: stretch; flex-direction: column; gap: 13px; }
  .service-process-panel .process-progress { display: grid; grid-template-columns: 160px minmax(100px, 1fr) 190px; align-items: center; flex: none; gap: 12px; padding: 11px 0 0; border-top: 1px solid #dfe9e2; border-left: 0; }
  .service-process-panel .process-progress > div,
  .service-process-panel .process-progress small { margin: 0; }
  .service-process-panel .process-progress small { white-space: nowrap; }
}
@media (max-width: 1020px) {
  .service-workspace-heading { align-items: flex-start; flex-direction: column; gap: 16px; }
  .service-workspace-actions { justify-content: flex-start; }
  .service-process-panel .process-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 10px; }
  .service-process-panel .step-arrow { display: none; }
  .service-process-panel .process-progress { grid-template-columns: 150px minmax(0, 1fr); }
  .service-process-panel .process-progress small { display: none; }
  .service-workspace-layout > .results-panel { min-height: 540px; }
}
@media (max-width: 760px) {
  .service-workspace-layout {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'context' 'list' 'conversation' 'results';
    grid-template-rows: auto;
  }
  .service-workspace-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); width: 100%; }
  .service-workspace-actions > .button { min-width: 0; padding-inline: 10px; }
  .service-workspace-actions > .button.primary { grid-column: 1 / -1; }
  .service-process-panel { padding: 15px; border-radius: 12px; }
  .service-process-panel .process-steps { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .service-process-panel .process-step { min-height: 35px; }
  .service-process-panel .step-copy small { white-space: normal; }
  .service-process-panel .process-progress { grid-template-columns: minmax(0, 1fr); gap: 7px; }
  .service-workspace-layout > .service-workspace-list { height: auto; }
  .service-workspace-content :deep(.service-conversation-panel) { height: auto; min-height: 0; max-height: none; }
  .service-workspace-layout > .results-panel { min-height: 0; }
  .service-workspace-layout > .results-panel .result-summary { grid-template-columns: 1fr; }
  .service-workspace-layout > .results-panel .overall-score { padding: 0 0 9px; border-right: 0; border-bottom: 1px solid #d9e8dc; }
  .service-workspace-layout > .results-panel .workspace-result-counts { grid-template-columns: 1fr; }
  .service-workspace-layout > .results-panel .workspace-result-counts > span { border-right: 0; }
  .service-workspace-layout > .results-panel .workspace-result-groups { max-height: 60vh; }
  .service-workspace-layout > .results-panel .workspace-result-groups .metric-row { grid-template-columns: 40px minmax(0, 1fr) 48px 34px; }
}
@media (max-width: 560px) {
  .service-workspace-title h1 { font-size: 28.5px; }
}
</style>

<style scoped src="./styles/review.css"></style>

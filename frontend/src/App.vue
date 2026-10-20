<!-- 环节：前端应用入口层；用途：启动并组合 Vue 工作台界面。 -->
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import Icon from './components/base/Icon.vue'
import StatusBadge from './components/base/StatusBadge.vue'
import ConversationPanel from './components/conversation/ConversationPanel.vue'
import ConsultationList from './components/conversation/ConsultationList.vue'
import {
  comparePriority,
  priorityLevels,
  priorityNames,
  reviewPriority,
  type PriorityLevel,
} from './utils/reviewPriority'
import FindingDetail from './components/feedback/FindingDetail.vue'
import OverviewPage from './pages/OverviewPage.vue'
import { useConsole } from './composables/useConsole'
import { agentName, dimensionGroups, dimensions, label, metricName, metrics, time } from './utils/catalog'
import { overallScore } from './utils/trust'
import { downloadJson } from './utils/export'
import { api } from './api/endpoints/evaluations'
import { setPrivateAccessToken } from './api/client/http'
import { SessionSchema } from './api/contracts/evaluation'
const separateBackend = Boolean(import.meta.env.VITE_API_URL)
const privateToken = ref('')
const privateAccessEnabled = ref(false)
const importing = ref(false)
const importMessage = ref('')
async function importSessions(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files || [])]
  input.value = ''
  if (!files.length) return
  if (!privateAccessEnabled.value) {
    importMessage.value = '请先输入私有数据访问令牌。'
    return
  }
  importing.value = true
  let imported = 0
  const failures: string[] = []
  for (const file of files) {
    try {
      if (file.size > 2_000_000) throw new Error('单个文件超过 2 MB，请按会话拆分。')
      const parsed = SessionSchema.safeParse(JSON.parse(await file.text()))
      if (!parsed.success) throw new Error('不是符合后端 Session 格式的 JSON。')
      if (parsed.data.source_id === 'synthetic-demo') throw new Error('演示数据不能作为真实会话导入。')
      await api.importSession(parsed.data)
      imported++
    } catch (error) {
      failures.push(`${file.name}：${(error as Error).message}`)
    }
  }
  importMessage.value = `已导入 ${imported}/${files.length} 份。${failures.length ? failures.join('；') : ''}`
  importing.value = false
  if (imported) {
    await refreshConsultations(0, '')
    if (consultations.value[0]) await selectConsultation(consultations.value[0].session_id)
  }
}
async function applyPrivateAccess() {
  setPrivateAccessToken(privateToken.value)
  privateAccessEnabled.value = !!privateToken.value.trim()
  privateToken.value = ''
  session.value = null
  report.value = null
  await refreshConsultations(0, '')
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
} = useConsole()
const nav = [
  { id: 'overview', name: '数据总览', icon: 'pulse' },
  { id: 'workspace', name: '评估工作台', icon: 'workspace' },
  { id: 'reports', name: '质检报告', icon: 'report' },
  { id: 'review', name: '人工复核', icon: 'shield' },
  { id: 'rubrics', name: '评价指标', icon: 'list' },
  { id: 'service', name: '服务连接', icon: 'settings' },
]
const page = ref('overview'),
  mobileOpen = ref(false),
  selectedId = ref(''),
  filter = ref('all'),
  query = ref(''),
  historyQuery = ref(''),
  highlightedIds = ref<string[]>([])
const toast = ref(''),
  exportConsent = ref(false)
let toastTimer: ReturnType<typeof setTimeout> | undefined
const draftDecision = ref(''),
  draftReason = ref(''),
  reviewCode = ref('')
const drafts = ref<
  {
    evaluation_id: string
    finding_id: string
    decision: string
    reason: string
    created_at: string
  }[]
>([])
const selected = computed(
  () => rows.value.find((r) => r.finding.finding_id === selectedId.value) || rows.value[0],
)
const visibleRows = computed(() =>
  rows.value.filter(
    (r) =>
      (filter.value === 'all' ||
        (filter.value === 'pending'
          ? pending.value.includes(r)
          : r.finding.metric_id.startsWith(filter.value))) &&
      `${r.finding.metric_id} ${metricName(r.finding.metric_id)} ${r.finding.rationale}`.includes(
        query.value,
      ),
  ),
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
      (batchRuns.value[0]?.sessions || []).filter((item) => item.risk_level === level).length,
    ]),
  ),
)
const latestBatch = computed(() => batchRuns.value[0] || null)
const reviewSessions = computed(() => {
  const items = latestBatch.value?.sessions || (session.value ? [{
    session_id: session.value.session_id,
    status: report.value?.status || 'partial',
    risk_level: pending.value.length ? 'medium' as const : 'low' as const,
    pending_count: pending.value.length,
  }] : [])
  return items.filter((item) =>
    (priorityFilter.value === 'all' || item.risk_level === priorityFilter.value) &&
    item.session_id.toLowerCase().includes(query.value.trim().toLowerCase()),
  )
})
const history = computed(
  () =>
    recent.value?.items.filter((r) =>
      `${r.evaluation_id} ${r.session_id}`.includes(historyQuery.value),
    ) || [],
)
const finalScore = computed(() => {
  const score = overallScore(report.value)
  return score === null ? null : score * 20
})
const verifiedCount = computed(() => rows.value.filter((r) => r.verdict.code === 'verified').length)
const currentTitle = computed(() => nav.find((n) => n.id === page.value)?.name || '评估工作台')
const isDemoMapping = computed(() => rows.value.some((r) => /^D[1-6]$/.test(r.finding.metric_id)))
const actionableDrafts = computed(() =>
  drafts.value.filter((d) => d.evaluation_id === report.value?.evaluation_id),
)
function focusMain() {
  document.getElementById('main')?.focus()
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && mobileOpen.value) {
    mobileOpen.value = false
    nextTick(() => document.querySelector<HTMLButtonElement>('.mobile-menu')?.focus())
  }
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
}
function exportReport() {
  if (!report.value) return
  downloadJson(
    { mode: mode.value, exported_at: new Date().toISOString(), report: report.value },
    `心衡-${report.value.evaluation_id}.json`,
  )
  notify('已导出报告；包含证据引文，请按授权范围保管。')
}
async function saveDraft() {
  if (
    !report.value ||
    !selected.value ||
    !draftDecision.value ||
    draftReason.value.trim().length < 5
  )
    return
  const input = {
    evaluation_id: report.value.evaluation_id,
    finding_id: selected.value.finding.finding_id,
    decision: draftDecision.value,
    reason: draftReason.value.trim(),
  }
  try {
    const saved = mode.value === 'preview'
      ? { ...input, created_at: new Date().toISOString() }
      : await api.addReview(input, reviewCode.value)
    drafts.value.push(saved)
  } catch (error) {
    notify(`复核提交失败：${(error as Error).message}`)
    return
  }
  draftDecision.value = ''
  draftReason.value = ''
  notify(mode.value === 'preview' ? '离线样例仅本页暂存。' : '复核意见已写入服务器，可刷新查看。')
}
async function loadReviews() {
  if (!report.value || mode.value !== 'service') return
  try {
    const result = await api.reviews(report.value.evaluation_id, reviewCode.value)
    drafts.value = result.items
    notify('已读取服务器复核记录。')
  } catch (error) {
    notify(`读取复核记录失败：${(error as Error).message}`)
  }
}
watch(selectedId, () => {
  draftDecision.value = ''
  draftReason.value = ''
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
    exportConsent.value = false
    highlightedIds.value = []
    selectedId.value = ''
    draftDecision.value = ''
    draftReason.value = ''
    drafts.value = []
    if (mode.value === 'service' && evaluationId) {
      try {
        const saved = await api.reviews(evaluationId, reviewCode.value)
        if (report.value?.evaluation_id === evaluationId) drafts.value = saved.items
      } catch { /* PostgreSQL 不可用时表单提交仍会给出明确错误。 */ }
    }
  },
)
onMounted(() => {
  readHash()
  window.addEventListener('hashchange', readHash)
  window.addEventListener('keydown', onKeydown)
  void initialize()
})
onUnmounted(() => {
  window.removeEventListener('hashchange', readHash)
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(toastTimer)
})
</script>

<template>
  <a href="#main" class="skip-link" @click.prevent="focusMain">跳到主要内容</a>
  <div class="app-shell">
    <button
      v-if="mobileOpen"
      class="nav-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    ></button>
    <aside :class="['sidebar', { open: mobileOpen }]">
      <a href="#overview" class="brand" @click.prevent="navigate('overview')"
        ><span class="brand-symbol"
          ><svg viewBox="0 0 40 40" width="34" height="34" fill="none" aria-hidden="true">
            <path
              d="M7 24c2.5-11 7.5-14 13-14s10.5 3 13 14"
              stroke="currentColor"
              stroke-width="2.6"
              stroke-linecap="round"
            />
            <path
              d="M10 27c3-6 6-9 10-9s7 3 10 9"
              stroke="currentColor"
              stroke-width="2.6"
              stroke-linecap="round"
            />
            <circle cx="20" cy="28" r="2.2" fill="currentColor" /></svg></span
        ><span><strong>心衡</strong><small>心理咨询服务质量平台</small></span></a
      >
      <div class="workspace-label">质量管理</div>
      <nav aria-label="主导航">
        <a
          v-for="item in nav"
          :key="item.id"
          :href="`#${item.id}`"
          :class="['nav-item', { active: page === item.id }]"
          :aria-current="page === item.id ? 'page' : undefined"
          @click.prevent="navigate(item.id)"
          ><Icon :name="item.icon" /><span>{{ item.name }}</span
          ><span v-if="item.id === 'review' && pending.length" class="nav-count">{{
            pending.length
          }}</span></a
        >
      </nav>
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
        <div class="sidebar-service">
          <span :class="['connection-dot', { online: connected }]" aria-hidden="true"></span
          >{{ mode === 'preview' ? '离线交互预览' : connected ? '服务已连接' : '等待服务连接' }}
        </div>
        <p>每个结论，都能回到原文。</p>
        <div class="sidebar-trust">
          <Icon name="shield" :size="21" />
          <div><strong>循证评价</strong><span>原文核验与修正留痕</span></div>
        </div>
        <div class="operator">
          <span class="operator-avatar">检</span>
          <div><strong>质检工作台</strong><small>咨询服务质量评估</small></div>
        </div>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumb">
          <button
            class="icon-button mobile-menu"
            aria-label="打开导航"
            :aria-expanded="mobileOpen"
            @click="mobileOpen = !mobileOpen"
          >
            <Icon name="menu" /></button
          ><span>工作空间</span><Icon name="chevron" :size="14" /><strong>{{
            currentTitle
          }}</strong>
        </div>
        <div class="topbar-actions">
          <StatusBadge :tone="mode === 'preview' ? 'warning' : 'neutral'">{{
            mode === 'preview' ? '离线样例' : privateAccessEnabled ? '私有数据模式' : '待授权'
          }}</StatusBadge
          ><button
            class="text-button mode-button"
            :disabled="running || loading"
            @click="switchMode"
          >
            {{ mode === 'preview' ? '连接后端服务' : '查看离线样例' }}</button
          ><span class="top-avatar" aria-label="质检工作空间"
            ><Icon name="shield" :size="18"
          /></span>
        </div>
      </header>
      <main id="main" tabindex="-1" :class="{ 'overview-main': page === 'overview' }">
        <div v-if="mode === 'preview'" class="mode-notice">
          <Icon name="info" :size="18" /><span
            >当前为离线交互样例。分数、核验与讨论均为预设合成数据，没有调用模型或写入服务器。</span
          >
        </div>
        <div class="page-heading">
          <div>
            <h1>{{ currentTitle }}</h1>
            <p>
              {{
                page === 'overview'
                  ? '汇总可信评分，了解服务质量与各维度表现。'
                  : page === 'workspace'
                    ? '评价已导入的真实咨询，再按订单核查依据。'
                    : page === 'reports'
                      ? '查看服务端运行记录与当前报告。'
                      : page === 'review'
                        ? '回到原文处理未决问题，保留原评价与修正理由。'
                        : page === 'rubrics'
                          ? '18 项指标各有唯一主责，事实核验与评分依据分别检查。'
                          : '分别检查服务存活、数据库连接和已接入能力。'
              }}
            </p>
          </div>
          <div v-if="page === 'workspace'" class="heading-actions">
            <button class="button secondary" :disabled="loading || running" @click="loadSession">
              <Icon name="refresh" :size="17" />{{ loading ? '加载中…' : '重新加载列表' }}</button
            ><button
              class="button primary"
              :disabled="!session || loading || running"
              @click="start"
            >
              <Icon :name="running ? 'clock' : 'play'" :size="17" />{{
                running ? `正在评估 ${batchProgress.completed}/${batchProgress.total}…` : '一键自动评估'
              }}
            </button>
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
        <template v-else-if="page === 'workspace'">
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
            @refresh="refreshConsultations"
          />
          <div v-if="listSource === 'access_required'" class="notice">
            真实会话需要访问令牌。<button class="text-button" @click="navigate('service')">前往服务连接设置</button>
          </div>
          <div v-else-if="listSource === 'database' && !totalConsultations && !listing" class="notice">
            当前数据库没有已导入的真实会话。<button class="text-button" @click="navigate('service')">前往服务连接导入</button>
          </div>
          <div v-if="errors.session" class="alert danger" role="alert">
            <strong>咨询记录加载失败</strong>
            <p>{{ errors.session }}</p>
            <button class="text-button" @click="loadSession">重新加载</button
            ><button class="text-button" :disabled="running || loading" @click="switchMode">
              查看离线交互样例
            </button>
          </div>
          <div v-if="errors.run" class="alert danger" role="alert">
            <strong>本次请求未完成</strong>
            <p>{{ errors.run }}</p>
            <button class="text-button" @click="navigate('reports')">先查看最近运行记录</button>
            <p v-if="report" class="small">以下保留的是上一次返回的报告，不是本次请求的新结果。</p>
          </div>
          <section class="session-strip surface" aria-label="本次会话信息">
            <div class="session-symbol"><Icon name="list" :size="23" /></div>
            <div class="session-identity">
              <span>当前咨询轮次</span
              ><strong>{{ session?.session_id || (loading ? '正在加载…' : '尚未加载') }}</strong>
            </div>
            <div class="session-property">
              <span>会话类型</span><strong>{{ label(session?.consultation_round) }}</strong>
            </div>
            <div class="session-property">
              <span>消息数量</span
              ><strong>{{ session?.messages.length ?? '—' }}<small> 条</small></strong>
            </div>
            <div class="session-property">
              <span>来源</span
              ><strong>{{
                mode === 'preview'
                  ? '离线合成样例'
                  : listSource === 'database'
                    ? '数据库记录'
                    : '尚未选择记录'
              }}</strong>
            </div>
          </section>
          <section class="run-track" aria-label="评价处理状态">
            <div :class="['track-step', { complete: !!session }]">
              <span>1</span>
              <div>
                <strong>会话准备</strong
                ><small>{{ session ? '咨询记录已加载' : '等待选择咨询' }}</small>
              </div>
            </div>
            <Icon name="chevron" :size="16" />
            <div :class="['track-step', { waiting: running, complete: !!report }]">
              <span>2</span>
              <div>
                <strong>专业评价</strong
                ><small>{{
                  running ? '正在等待后端结果' : report ? label(report.status) : '等待开始'
                }}</small>
              </div>
            </div>
            <Icon name="chevron" :size="16" />
            <div class="track-step">
              <span>3</span>
              <div>
                <strong>证据核验</strong
                ><small>{{ report ? `${verifiedCount} 项核验通过` : '等待核验结果' }}</small>
              </div>
            </div>
            <Icon name="chevron" :size="16" />
            <div class="track-step">
              <span>4</span>
              <div>
                <strong>修正与仲裁</strong><small>{{ label(report?.arbitration_status) }}</small>
              </div>
            </div>
            <Icon name="chevron" :size="16" />
            <div class="track-step">
              <span>5</span>
              <div>
                <strong>报告与复核</strong
                ><small>{{ report ? `${pending.length} 项待核查` : '等待报告' }}</small>
              </div>
            </div>
          </section>
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
          <div class="workspace-grid">
            <ConversationPanel :session="session" :highlighted-ids="highlightedIds" />
            <section class="results-panel surface" aria-labelledby="results-title">
              <div class="panel-header">
                <div>
                  <h2 id="results-title">服务质量评价</h2>
                  <p>
                    {{
                      report
                        ? `${rows.length} 项评价 · ${verifiedCount} 项核验通过`
                        : '三个专业视角，共同回到原文'
                    }}
                  </p>
                </div>
                <StatusBadge :tone="report ? 'warning' : 'neutral'">{{
                  report ? '结论待核查' : '等待评估'
                }}</StatusBadge>
              </div>
              <div v-if="!report" class="empty-state report-empty">
                <div class="empty-illustration">
                  <Icon name="report" :size="42" /><span><Icon name="shield" :size="24" /></span>
                </div>
                <h3>让每条评价都有依据</h3>
                <p>
                  开始评估后，可查看评价理由、对应原话和核验状态。未解决的证据问题会保留到复核列表。
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
              <template v-else
                ><div class="report-summary">
                  <p>{{ report.summary }}</p>
                  <div class="summary-counts">
                    <span
                      ><strong>{{ verifiedCount }}</strong
                      >核验通过</span
                    ><span
                      ><strong>{{ pending.length }}</strong
                      >待核查</span
                    ><span
                      ><strong>{{ finalScore === null ? '—' : finalScore.toFixed(1) }}</strong
                      >确定性总分（满分100）</span
                    >
                  </div>
                  <p class="small">
                    {{
                      finalScore === null
                        ? '尚不满足确定性评分展示条件；初评分不进行前端平均。'
                        : '总分来自后端评分汇总器。'
                    }}
                  </p>
                </div>
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
                    <option value="all">全部结果</option>
                    <option value="pending">待核查</option>
                    <option v-for="d in dimensions" :key="d.id" :value="d.id">{{ d.name }}</option>
                  </select>
                </div>
                <div class="finding-list" aria-label="评价结果列表">
                  <button
                    v-for="r in visibleRows"
                    :key="r.finding.finding_id"
                    :class="[
                      'finding-row',
                      { selected: selected?.finding.finding_id === r.finding.finding_id },
                    ]"
                    :aria-pressed="selected?.finding.finding_id === r.finding.finding_id"
                    @click="select(r.finding.finding_id)"
                  >
                    <span class="finding-row-main"
                      ><span class="finding-code">{{ r.finding.metric_id }}</span
                      ><strong>{{ metricName(r.finding.metric_id) }}</strong
                      ><span class="finding-agent">{{ agentName(r.agentId) }}</span></span
                    ><span class="finding-row-end"
                      ><StatusBadge :tone="r.verdict.tone">{{ r.verdict.text }}</StatusBadge
                      ><span class="list-score"
                        >{{
                          r.finding.applicability === 'applicable' && r.finding.score !== null
                            ? r.finding.score.toFixed(1)
                            : '—'
                        }}<small
                          v-if="
                            r.finding.applicability === 'applicable' && r.finding.score !== null
                          "
                          >{{ r.verdict.code === 'verified' ? '分' : '初评' }}</small
                        ></span
                      ><Icon name="chevron" :size="16"
                    /></span>
                  </button>
                  <p v-if="!visibleRows.length" class="empty-note padded">
                    没有匹配的结果，请调整搜索或筛选条件。
                  </p>
                </div>
                <FindingDetail
                  v-if="selected"
                  :row="selected"
                  :report="report"
                  :session="session"
                  @focus="focusEvidence"
                />
                <details class="report-limitations">
                  <summary>报告限制与待复核原因</summary>
                  <ul>
                    <li
                      v-for="(item, i) in [...report.limitations, ...report.review_reasons]"
                      :key="i"
                    >
                      {{ item }}
                    </li>
                    <li v-if="!report.limitations.length && !report.review_reasons.length">
                      后端没有返回限制项，不代表全部核验已经完成。
                    </li>
                  </ul>
                  <p v-for="a in report.agent_results.filter((a) => a.error)" :key="a.agent_id">
                    {{ agentName(a.agent_id) }}：{{ a.error }}
                  </p>
                </details>
              </template>
            </section>
          </div>
        </template>

        <template v-else-if="page === 'reports'">
          <section v-if="latestBatch" class="surface batch-report" aria-labelledby="batch-report-title">
            <div class="panel-header">
              <div>
                <h2 id="batch-report-title">最近批次质检报告</h2>
                <p>{{ latestBatch.batch_id }} · {{ time(latestBatch.created_at, true) }}</p>
              </div>
              <StatusBadge :tone="latestBatch.failed ? 'warning' : 'success'">
                {{ latestBatch.succeeded }}/{{ latestBatch.total }} 轮完成
              </StatusBadge>
            </div>
            <div class="batch-counts">
              <div><span>检测会话</span><strong>{{ latestBatch.total }}<small> 轮</small></strong></div>
              <div><span>高风险候选</span><strong class="risk-high">{{ latestBatch.high }}</strong></div>
              <div><span>中风险待核查</span><strong class="risk-medium">{{ latestBatch.medium }}</strong></div>
              <div><span>低风险常规</span><strong class="risk-low">{{ latestBatch.low }}</strong></div>
              <div><span>评估失败</span><strong>{{ latestBatch.failed }}</strong></div>
            </div>
            <div class="batch-quality-summary">
              <h3>本批平台服务质量评价</h3>
              <p>{{ latestBatch.quality_summary }}</p>
            </div>
            <details class="batch-session-details">
              <summary>展开本批 {{ latestBatch.sessions.length }} 轮会话结果</summary>
              <ul>
                <li v-for="item in latestBatch.sessions" :key="item.session_id">
                  <button class="text-button" @click="openConsultation(item.session_id)">{{ item.session_id }}</button>
                  <StatusBadge :tone="item.risk_level === 'high' ? 'danger' : item.risk_level === 'medium' ? 'warning' : 'neutral'">
                    {{ item.risk_level === 'unknown' ? '未完成' : `${priorityNames[item.risk_level]}风险` }}
                  </StatusBadge>
                  <span>{{ item.pending_count }} 项待复核</span>
                </li>
              </ul>
            </details>
          </section>
          <section v-else class="surface empty-state compact">
            <Icon name="report" :size="34" />
            <h3>还没有批次报告</h3>
            <p>在工作台点击“一键自动评估”后，这里会汇总本批会话数、风险分布和服务质量评价。</p>
            <button class="button secondary" @click="navigate('workspace')">前往评估工作台</button>
          </section>
          <section class="surface current-report">
            <div class="panel-header">
              <div>
                <h2>当前报告</h2>
                <p>{{ report?.evaluation_id || '完成一次评估后，在这里查看与导出完整结果。' }}</p>
              </div>
              <StatusBadge>{{ report ? label(report.status) : '尚未生成' }}</StatusBadge>
            </div>
            <template v-if="report"
              ><div class="current-report-body">
                <p>{{ report.summary }}</p>
                <dl class="inline-facts">
                  <div>
                    <dt>本次评价条目</dt>
                    <dd>{{ rows.length }}</dd>
                  </div>
                  <div>
                    <dt>待核查</dt>
                    <dd>{{ pending.length }}</dd>
                  </div>
                  <div>
                    <dt>确定性总分（满分100）</dt>
                    <dd>{{ finalScore === null ? '未生成' : finalScore.toFixed(1) }}</dd>
                  </div>
                  <div>
                    <dt>接收时间</dt>
                    <dd>{{ time(lastRun, true) }}</dd>
                  </div>
                </dl>
                <button class="button secondary" @click="navigate('workspace')">
                  查看证据与核验详情<Icon name="arrow" :size="16" />
                </button>
                <div class="export-area">
                  <label
                    ><input
                      v-model="exportConsent"
                      type="checkbox"
                    />我确认可将本报告及证据引文保存到此电脑</label
                  ><button
                    class="button secondary"
                    :disabled="!exportConsent"
                    @click="exportReport"
                  >
                    <Icon name="download" :size="17" />导出报告 JSON
                  </button>
                </div>
              </div></template
            >
            <div v-else class="empty-state compact">
              <Icon name="report" :size="34" />
              <h3>还没有当前报告</h3>
              <button class="button secondary" @click="navigate('workspace')">
                前往评估工作台
              </button>
            </div>
          </section>
          <details class="surface history-panel collapsible-history">
            <summary class="history-collapse-summary">
              <span><strong>最近运行记录</strong><small>按报告保留最近 20 条，可展开查看</small></span>
              <Icon name="chevron" :size="17" />
            </summary>
            <div class="panel-header">
              <div>
                <h2>最近运行记录</h2>
                <p>最多展示后端最近 20 次运行。运行完成不代表证据已核验通过。</p>
              </div>
              <StatusBadge :tone="recent?.database_configured ? 'success' : 'neutral'">{{
                mode === 'preview'
                  ? '离线模式'
                  : recent?.database_configured
                    ? '数据库已配置'
                    : '数据库状态未确认'
              }}</StatusBadge>
            </div>
            <div v-if="errors.recent" class="alert danger" role="alert">{{ errors.recent }}</div>
            <div class="filter-toolbar">
              <label class="search-field"
                ><Icon name="search" :size="17" /><input
                  v-model="historyQuery"
                  aria-label="搜索最近运行"
                  placeholder="搜索会话或报告编号" /></label
              ><span class="small">{{ history.length }} 条摘要</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>报告编号</th>
                    <th>咨询轮次</th>
                    <th>运行状态</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in history" :key="item.evaluation_id">
                    <td class="id-cell">{{ item.evaluation_id }}</td>
                    <td>{{ item.session_id }}</td>
                    <td>
                      <StatusBadge :tone="item.status === 'failed' ? 'danger' : 'neutral'">{{
                        label(item.status)
                      }}</StatusBadge>
                    </td>
                    <td>{{ time(item.created_at, true) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="!history.length" class="empty-note padded">
              {{
                mode === 'preview'
                  ? '离线样例不会写入后端数据库。'
                  : '暂无匹配的运行记录。导入真实会话后可在工作台开始评估。'
              }}
            </p>
            <div class="panel-footer">
              当前接口只返回历史摘要，尚不支持打开旧报告全文。当前报告刷新后不会保留在浏览器。
            </div>
          </details>
        </template>

        <template v-else-if="page === 'review'">
          <div class="notice review-notice">
            <Icon name="info" :size="18" />
            <p>
              人工复核提交接口尚未接入。以下仅暂存本页草稿，刷新会丢失；导出后交由团队接入正式保存流程。不会修改
              Agent 原结论。
            </p>
          </div>
          <div v-if="!report" class="surface empty-state">
            <Icon name="shield" :size="40" />
            <h3>先完成一次评估</h3>
            <p>证据不足、材料冲突和未完成核验的项目将在这里集中展示。</p>
            <button class="button primary" @click="navigate('workspace')">前往评估工作台</button>
          </div>
          <template v-else
            ><section class="priority-summary" aria-label="核查优先级筛选">
              <button
                :class="['priority-count', { active: priorityFilter === 'all' }]"
                @click="priorityFilter = 'all'"
                :aria-pressed="priorityFilter === 'all'"
              >
                <span>全部待复核会话</span><strong>{{ latestBatch?.sessions.length ?? (session ? 1 : 0) }}</strong
                ><small>按会话 ID 分组</small>
              </button>
              <button
                v-for="level in priorityLevels"
                :key="level"
                :class="[
                  'priority-count',
                  `priority-${level}`,
                  { active: priorityFilter === level },
                ]"
                @click="priorityFilter = level"
                :aria-pressed="priorityFilter === level"
              >
                <span>{{ priorityNames[level] }}优先级</span
                ><strong>{{ priorityCounts[level] }}</strong
                ><small>{{
                  level === 'high'
                    ? '优先专业核查'
                    : level === 'medium'
                      ? '补查证据与依据'
                      : '常规核验'
                }}</small>
              </button>
            </section>
            <p class="priority-caption">
              以下数量按会话统计，核查优先级用于安排审核顺序，不代表患者临床危急程度。高：风险响应 /
              转介指标或材料冲突；中：证据、执行或评分依据不足；低：常规待核验。
            </p>
            <div class="review-toolbar">
              <label class="search-field"
                ><Icon name="search" :size="17" /><input
                  v-model="query"
                  aria-label="搜索待复核会话"
                  placeholder="搜索会话 ID" /></label
              ><span>{{ reviewSessions.length }} 个会话 · {{ reviewSessions.reduce((sum, item) => sum + item.pending_count, 0) }} 项待核查</span
              ><button
                class="button secondary"
                :disabled="!actionableDrafts.length"
                @click="
                  downloadJson(
                    { scope: 'local-draft-not-submitted', drafts: actionableDrafts },
                    '心衡-复核草稿.json',
                  )
                "
              >
                <Icon name="download" :size="16" />导出草稿（{{ actionableDrafts.length }}）
              </button>
            </div>
            <div class="review-grid">
              <section class="surface review-queue">
                <div class="panel-header"><div><h2>待复核会话</h2><p>先按会话 ID 选择案件，再查看会话内的具体待核查项。</p></div></div>
                <button
                  v-for="item in reviewSessions"
                  :key="item.session_id"
                  :class="[
                    'session-review-item',
                    { selected: session?.session_id === item.session_id },
                  ]"
                  :data-priority="item.risk_level"
                  :aria-pressed="session?.session_id === item.session_id"
                  @click="openConsultation(item.session_id)"
                >
                  <span class="session-review-heading"><strong>{{ item.session_id }}</strong><StatusBadge :tone="item.risk_level === 'high' ? 'danger' : item.risk_level === 'medium' ? 'warning' : 'neutral'">{{ item.risk_level === 'unknown' ? '未完成' : `${priorityNames[item.risk_level]}风险` }}</StatusBadge></span>
                  <span class="session-review-meta">{{ item.pending_count }} 项待复核 · {{ label(item.status) }}</span>
                </button>
                <p v-if="!reviewSessions.length" class="empty-note padded">当前筛选没有待复核会话。</p>
              </section>
              <section class="surface review-detail">
                <div class="session-case-heading">
                  <h2>{{ session ? `会话 ${session.session_id}` : '选择一个待复核会话' }}</h2>
                  <span v-if="session">本会话 {{ queue.length }} 项待复核</span>
                </div>
                <div v-if="session && queue.length" class="session-finding-list" aria-label="本会话待复核项">
                  <button v-for="r in queue" :key="r.finding.finding_id" :class="['session-finding-item', { selected: selected?.finding.finding_id === r.finding.finding_id }]" @click="select(r.finding.finding_id)">
                    <span class="metric-code">{{ r.finding.metric_id }}</span><strong>{{ metricName(r.finding.metric_id) }}</strong><StatusBadge :tone="r.verdict.tone">{{ r.verdict.text }}</StatusBadge>
                  </button>
                </div>
                <div
                  v-if="
                    selected &&
                    queue.some((r) => r.finding.finding_id === selected.finding.finding_id)
                  "
                  :class="['priority-detail', `priority-${reviewPriority(selected).level}`]"
                >
                  <Icon name="clock" :size="22" />
                  <div>
                    <strong>核查优先级：{{ priorityNames[reviewPriority(selected).level] }}</strong>
                    <p>{{ reviewPriority(selected).reason }}</p>
                  </div>
                </div>
                <FindingDetail
                  v-if="
                    selected &&
                    queue.some((r) => r.finding.finding_id === selected.finding.finding_id)
                  "
                  :row="selected"
                  :report="report"
                  :session="session"
                  @focus="
                    async (ids) => {
                      navigate('workspace')
                      await focusEvidence(ids)
                    }
                  "
                />
                <p v-if="!session || !queue.length" class="empty-note padded">
                  {{ !session ? '从左侧会话列表选择一个案件，查看其复核详情。' : '本会话目前没有待核查项目。' }}
                </p>
                <form
                  v-if="
                    selected &&
                    queue.some((r) => r.finding.finding_id === selected.finding.finding_id)
                  "
                  class="review-form"
                  @submit.prevent="saveDraft"
                >
                  <h3>{{ mode === 'preview' ? '离线复核草稿' : '提交人工复核意见' }}</h3>
                  <label v-if="mode === 'service'" for="review-code">复核访问码（公网部署时填写）</label>
                  <input v-if="mode === 'service'" id="review-code" v-model="reviewCode" type="password" autocomplete="off" />
                  <button v-if="mode === 'service'" type="button" class="text-button" @click="loadReviews">读取已提交意见</button>
                  <label for="decision">处理意见</label
                  ><select id="decision" v-model="draftDecision" required>
                    <option value="" disabled>选择处理意见</option>
                    <option value="确认">确认</option>
                    <option value="驳回">驳回</option>
                    <option value="建议修正">建议修正</option>
                    <option value="无法判断">无法判断</option>
                    <option value="升级复核">升级复核</option></select
                  ><label for="reason">依据与理由</label
                  ><textarea
                    id="reason"
                    v-model="draftReason"
                    required
                    minlength="5"
                    maxlength="2000"
                    rows="4"
                    placeholder="写明所依据的原文、规则或仍缺少的信息（至少 5 字）"
                  ></textarea>
                  <div class="review-form-footer">
                    <small>{{ mode === 'preview' ? '仅本页暂存' : '提交后写入 PostgreSQL 复核日志' }}</small
                    ><button
                      class="button primary"
                      :disabled="!draftDecision || draftReason.trim().length < 5"
                    >
                      {{ mode === 'preview' ? '暂存草稿' : '提交复核' }}
                    </button>
                  </div>
                  <div
                    v-for="(d, i) in actionableDrafts.filter(
                      (d) => d.finding_id === selected?.finding.finding_id,
                    )"
                    :key="i"
                    class="draft-record"
                  >
                    <strong>{{ d.decision }} · {{ time(d.created_at) }}</strong>
                    <p>{{ d.reason }}</p>
                  </div>
                </form>
              </section>
            </div></template
          >
        </template>

        <template v-else-if="page === 'rubrics'">
          <div class="rubric-intro surface">
            <Icon name="shield" :size="30" />
            <div>
              <h2>三组主责评价 Agent</h2>
              <p>
                D1 与 D3、D2 与 D5、D4 与 D6 分别由同一主责 Agent 评价；核验与仲裁仍按需独立执行。
              </p>
            </div>
            <span class="rubric-total">18<small>项指标</small></span>
          </div>
          <div class="notice">
            以下为仓库约定的指标名称与归属。正式评分锚点、权重和发布版本尚需专业审定，本页面不提供虚构的评分规则。
          </div>
          <div class="rubric-grid">
            <section v-for="d in dimensionGroups" :key="d.id" class="surface rubric-section">
              <div class="panel-header">
                <h2>
                  <span>{{ d.id }}</span
                  >{{ d.name }}
                </h2>
                <small>{{ metrics.filter((m) => d.dimensionIds.some((id) => m.id.startsWith(id))).length }} 项</small>
              </div>
              <div
                v-for="m in metrics.filter((m) => d.dimensionIds.some((id) => m.id.startsWith(id)))"
                :key="m.id"
                class="rubric-item"
              >
                <span class="metric-code">{{ m.id }}</span>
                <div>
                  <strong>{{ m.name }}</strong
                  ><small>{{ agentName(m.agent) }}</small>
                </div>
                <span class="draft-label">待发布</span>
              </div>
            </section>
          </div>
        </template>

        <template v-else-if="page === 'service'">
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
            <div v-if="mode === 'service'" class="capability-row">
              <span><strong>导入真实会话 JSON</strong><small>先用本地脚本将原始平台数据整理成每会话一个 Session JSON；文件只在点击选择后经授权上传到后端。</small></span>
              <label class="button secondary" for="session-import">{{ importing ? '导入中…' : '选择会话文件' }}</label>
              <input id="session-import" type="file" accept=".json,application/json" multiple :disabled="!privateAccessEnabled || importing || running" @change="importSessions" />
            </div>
            <p v-if="importMessage" class="small" role="status">{{ importMessage }}</p>
          </section>
          <section class="surface capability-panel">
            <div class="panel-header"><h2>功能接入边界</h2></div>
            <div class="capability-row">
              <span
                ><strong>真实会话导入、评价请求与最近记录</strong
                ><small>需访问令牌；真实记录从数据库列表读取，演示样例仅在离线模式使用。</small></span
              ><StatusBadge>已有接口</StatusBadge>
            </div>
            <div class="capability-row">
              <span
                ><strong>真实模型与完整证据核验</strong
                ><small>演示后端当前使用确定性规则；页面仅展示实际返回的核验字段。</small></span
              ><StatusBadge tone="warning">尚待完善</StatusBadge>
            </div>
            <div class="capability-row">
              <span
                ><strong>修正讨论与分歧仲裁</strong
                ><small>支持结构化记录展示；后端未返回时明确显示缺失状态。</small></span
              ><StatusBadge tone="warning">展示已预留</StatusBadge>
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
        </template>
        <footer class="page-footer">
          <span>心衡 · 服务质量辅助评估</span>
          <p>{{ mode === 'preview' ? '当前为离线合成数据演示。' : '真实会话仅供授权访问。' }} 正式结论需核查证据与适用规则，并由授权人员复核。</p>
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

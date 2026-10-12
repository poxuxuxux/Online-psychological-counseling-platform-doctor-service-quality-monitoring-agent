<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import Icon from './components/base/Icon.vue'
import StatusBadge from './components/base/StatusBadge.vue'
import ConversationPanel from './components/conversation/ConversationPanel.vue'
import FindingDetail from './components/feedback/FindingDetail.vue'
import OverviewPage from './pages/OverviewPage.vue'
import { useConsole } from './composables/useConsole'
import { agentName, dimensions, label, metricName, metrics, time } from './utils/catalog'
import { overallScore } from './utils/trust'
import { downloadJson } from './utils/export'
const {
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
  draftReason = ref('')
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
  pending.value.filter((r) =>
    `${r.finding.metric_id} ${metricName(r.finding.metric_id)}`.includes(query.value),
  ),
)
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
  await run()
  if (report.value && !errors.value.run) {
    selectedId.value = rows.value[0]?.finding.finding_id || ''
    notify(
      mode.value === 'preview'
        ? '已载入离线交互样例，未运行模型。'
        : '报告已返回。请核查证据和未决问题。',
    )
  }
}
async function switchMode() {
  await setMode(mode.value === 'service' ? 'preview' : 'service')
  drafts.value = []
  highlightedIds.value = []
  selectedId.value = ''
}
function exportReport() {
  if (!report.value) return
  downloadJson(
    { mode: mode.value, exported_at: new Date().toISOString(), report: report.value },
    `心衡-${report.value.evaluation_id}.json`,
  )
  notify('已导出报告；包含证据引文，请按授权范围保管。')
}
function saveDraft() {
  if (
    !report.value ||
    !selected.value ||
    !draftDecision.value ||
    draftReason.value.trim().length < 5
  )
    return
  drafts.value.push({
    evaluation_id: report.value.evaluation_id,
    finding_id: selected.value.finding.finding_id,
    decision: draftDecision.value,
    reason: draftReason.value.trim(),
    created_at: new Date().toISOString(),
  })
  draftDecision.value = ''
  draftReason.value = ''
  notify('已暂存本页复核草稿。刷新会丢失，请导出；未提交服务器。')
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
    selectedId.value = pending.value[0]!.finding.finding_id
})
watch(
  () => report.value?.evaluation_id,
  () => {
    exportConsent.value = false
    highlightedIds.value = []
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
            mode === 'preview' ? '离线样例' : '合成数据演示'
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
                    ? '从一轮咨询出发，核查每一条评价的依据。'
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
              <Icon name="refresh" :size="17" />{{ loading ? '加载中…' : '重新加载示例' }}</button
            ><button
              class="button primary"
              :disabled="!session || loading || running"
              @click="start"
            >
              <Icon :name="running ? 'clock' : 'play'" :size="17" />{{
                running ? '正在评估…' : report ? '重新评估' : '开始质量评估'
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
          <div v-if="errors.session" class="alert danger" role="alert">
            <strong>示例加载失败</strong>
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
              ><strong>{{ mode === 'preview' ? '离线合成样例' : '后端合成示例' }}</strong>
            </div>
          </section>
          <section class="run-track" aria-label="评价处理状态">
            <div :class="['track-step', { complete: !!session }]">
              <span>1</span>
              <div>
                <strong>会话准备</strong
                ><small>{{ session ? '已加载合成记录' : '等待加载' }}</small>
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
          <p v-if="running" class="run-note" role="status">
            请求已发送，正在等待完整结果。当前接口没有实时进度；页面不会推测内部步骤。
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
                  {{ running ? '正在等待结果…' : '开始质量评估' }}
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
          <section class="surface history-panel">
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
                  : '暂无匹配的运行记录。可先在工作台完成一次合成数据评估。'
              }}
            </p>
            <div class="panel-footer">
              当前接口只返回历史摘要，尚不支持打开旧报告全文。当前报告刷新后不会保留在浏览器。
            </div>
          </section>
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
            ><div class="review-toolbar">
              <label class="search-field"
                ><Icon name="search" :size="17" /><input
                  v-model="query"
                  aria-label="搜索待复核指标"
                  placeholder="搜索待复核指标" /></label
              ><span>{{ pending.length }} 项待核查</span
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
                <div class="panel-header"><h2>待核查项目</h2></div>
                <button
                  v-for="r in queue"
                  :key="r.finding.finding_id"
                  :class="[
                    'queue-item',
                    { selected: selected?.finding.finding_id === r.finding.finding_id },
                  ]"
                  @click="select(r.finding.finding_id)"
                >
                  <span class="metric-code">{{ r.finding.metric_id }}</span
                  ><strong>{{ metricName(r.finding.metric_id) }}</strong
                  ><StatusBadge :tone="r.verdict.tone">{{ r.verdict.text }}</StatusBadge>
                </button>
                <p v-if="!queue.length" class="empty-note padded">当前筛选没有待核查项目。</p>
              </section>
              <section class="surface review-detail">
                <FindingDetail
                  v-if="selected"
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
                <form v-if="selected" class="review-form" @submit.prevent="saveDraft">
                  <h3>复核意见草稿</h3>
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
                    <small>仅本页暂存，未提交服务器</small
                    ><button
                      class="button primary"
                      :disabled="!draftDecision || draftReason.trim().length < 5"
                    >
                      暂存草稿
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
              <h2>一个指标，一位主责评价 Agent</h2>
              <p>
                核验 Agent 检查原文、事实、适用性和评分依据；仲裁 Agent
                处理仍未解决的语义分歧。它们不再独立给同一指标打第二套分数。
              </p>
            </div>
            <span class="rubric-total">18<small>项指标</small></span>
          </div>
          <div class="notice">
            以下为仓库约定的指标名称与归属。正式评分锚点、权重和发布版本尚需专业审定，本页面不提供虚构的评分规则。
          </div>
          <div class="rubric-grid">
            <section v-for="d in dimensions" :key="d.id" class="surface rubric-section">
              <div class="panel-header">
                <h2>
                  <span>{{ d.id }}</span
                  >{{ d.name }}
                </h2>
                <small>{{ metrics.filter((m) => m.id.startsWith(d.id)).length }} 项</small>
              </div>
              <div
                v-for="m in metrics.filter((m) => m.id.startsWith(d.id))"
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
                <p>服务存活与数据库连接分别检查。</p>
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
                      ? '连接正常'
                      : ready?.database.configured
                        ? '已配置，连接未确认'
                        : '未配置或状态未知'
                  }}</StatusBadge>
                </dd>
              </div>
              <div>
                <dt>最近检查</dt>
                <dd>{{ time(lastChecked, true) }}</dd>
              </div>
              <div>
                <dt>接口方式</dt>
                <dd>同源 API，不在前端保存密钥</dd>
              </div>
            </dl>
            <p v-if="errors.ready" class="notice danger">{{ errors.ready }}</p>
          </section>
          <section class="surface capability-panel">
            <div class="panel-header"><h2>功能接入边界</h2></div>
            <div class="capability-row">
              <span
                ><strong>合成会话、评价请求与最近记录</strong
                ><small>已按现有 API 契约接入，是否可用以实际请求为准。</small></span
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
                ><strong>授权登录、真实数据导入与复核提交</strong
                ><small>等待后端提供授权与保存接口，当前不开放真实数据上传。</small></span
              ><StatusBadge tone="warning">尚未接入</StatusBadge>
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
          <p>合成数据演示。正式结论需核查证据与适用规则，并由授权人员复核。</p>
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

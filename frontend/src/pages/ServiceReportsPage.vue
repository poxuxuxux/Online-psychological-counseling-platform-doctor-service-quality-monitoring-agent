<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Icon from '../components/base/Icon.vue'
import type { BatchRun } from '../composables/useConsole'
import type { Recent, Report } from '../api/contracts/evaluation'
import { isDateInRange, useDateRange } from '../composables/dateRange'

const props = defineProps<{
  latestBatch: BatchRun | null
  report: Report | null
  recent: Recent | null
  recentError: string
  connected: boolean
  lastRun: string | null
}>()

const emit = defineEmits<{
  openSession: [sessionId: string]
  exportReport: []
  navigate: [page: 'workspace']
  refresh: []
}>()

const dateRange = useDateRange()
const query = ref('')
const statusFilter = ref<'all' | 'completed' | 'partial' | 'failed'>('all')
const startDate = ref('')
const endDate = ref('')
const descending = ref(true)
const currentPage = ref(1)
const pageSize = 8
const showExportConsent = ref(false)

const statusText = { completed: '已完成', partial: '部分完成', failed: '失败' } as const
const reportRisk = computed(() => props.report?.risk?.level || 'unknown')
const reportCreatedAt = computed(() => {
  const id = props.report?.evaluation_id
  return props.recent?.items.find((item) => item.evaluation_id === id)?.created_at || props.lastRun
})
const titleText = computed(() => props.latestBatch?.batch_id || props.report?.evaluation_id || '等待生成')
const summaryTime = computed(() => props.latestBatch ? props.latestBatch.created_at : reportCreatedAt.value)
const summaryStatusClass = computed(() => {
  if (props.latestBatch) return props.latestBatch.failed ? 'processing' : 'completed'
  if (!props.report) return 'processing'
  if (props.report.status === 'failed') return 'failed'
  return props.report.status === 'partial' ? 'processing' : 'completed'
})
const summaryStatusText = computed(() => {
  if (props.latestBatch) return `${props.latestBatch.succeeded}/${props.latestBatch.total} 轮完成`
  return props.report ? statusText[props.report.status] : '等待生成'
})
const summaryStats = computed(() => {
  const batch = props.latestBatch
  if (batch) return [
    { key: 'total', label: '检测会话数', value: batch.total, icon: 'message', tone: 'total', note: `${batch.succeeded} 完成 · ${batch.failed} 失败` },
    { key: 'high', label: '高风险', value: batch.high, icon: 'alert', tone: 'high', note: percent(batch.high, batch.total) },
    { key: 'medium', label: '中风险', value: batch.medium, icon: 'alert', tone: 'medium', note: percent(batch.medium, batch.total) },
    { key: 'low', label: '低风险', value: batch.low, icon: 'check', tone: 'low', note: percent(batch.low, batch.total) },
  ]

  const report = props.report
  const riskKnown = report && reportRisk.value !== 'unknown'
  return [
    { key: 'total', label: '检测会话数', value: report ? 1 : '—', icon: 'message', tone: 'total', note: report ? '当前评估会话' : '等待后端数据' },
    { key: 'high', label: '高风险', value: riskKnown ? Number(reportRisk.value === 'high') : '—', icon: 'alert', tone: 'high', note: riskKnown ? '当前评估结果' : '暂无风险统计' },
    { key: 'medium', label: '中风险', value: riskKnown ? Number(reportRisk.value === 'medium') : '—', icon: 'alert', tone: 'medium', note: riskKnown ? '当前评估结果' : '暂无风险统计' },
    { key: 'low', label: '低风险', value: riskKnown ? Number(reportRisk.value === 'low') : '—', icon: 'check', tone: 'low', note: riskKnown ? '当前评估结果' : '暂无风险统计' },
  ]
})
const filteredItems = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return [...(props.recent?.items || [])]
    .filter((item) => {
      const day = item.created_at.slice(0, 10)
      return (statusFilter.value === 'all' || item.status === statusFilter.value) &&
        (!keyword || `${item.evaluation_id} ${item.session_id}`.toLowerCase().includes(keyword)) &&
        isDateInRange(day, dateRange.value) &&
        (!startDate.value || day >= startDate.value) &&
        (!endDate.value || day <= endDate.value)
    })
    .sort((a, b) => descending.value
      ? b.created_at.localeCompare(a.created_at)
      : a.created_at.localeCompare(b.created_at))
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize)))
const visibleItems = computed(() => filteredItems.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))

function formatNumber(value: number | string) {
  return typeof value === 'number' ? value.toLocaleString('zh-CN') : value
}
function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium', timeStyle: 'short', hour12: false,
  }).format(date)
}
function percent(value: number, total: number) {
  return total ? `${((value / total) * 100).toFixed(1)}%` : '—'
}
function resetFilters() {
  query.value = ''
  statusFilter.value = 'all'
  startDate.value = ''
  endDate.value = ''
  currentPage.value = 1
}
watch([query, statusFilter, startDate, endDate, () => dateRange.value.start, () => dateRange.value.end], () => { currentPage.value = 1 })
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })
watch(() => props.report?.evaluation_id, () => { showExportConsent.value = false })
</script>

<template>
  <div class="quality-reports-page service-reports-page">
    <header class="reports-heading">
      <div>
        <div class="reports-title-line">
          <h1>质检报告</h1>
          <span :class="['service-connection-state', { connected }]">
            <i aria-hidden="true"></i>{{ connected ? '后端数据' : '服务待连接' }}
          </span>
        </div>
        <p>查看最近批次质检结果与历史批次报告。</p>
      </div>
      <div class="reports-heading-actions">
        <label class="report-export-consent"><input v-model="showExportConsent" type="checkbox" :disabled="!report" />确认有权限保存报告数据</label>
        <button class="reports-action secondary" type="button" :disabled="!showExportConsent || !report" @click="emit('exportReport')"><Icon name="download" :size="16" />导出当前报告</button>
        <button class="reports-action secondary" type="button" @click="emit('refresh')"><Icon name="refresh" :size="16" />刷新记录</button>
      </div>
    </header>

    <section class="latest-report-panel" aria-labelledby="service-latest-title">
      <div class="latest-report-heading">
        <h2 id="service-latest-title">最近批次报告</h2>
        <div class="latest-report-controls">
          <span :class="['report-status', summaryStatusClass]">
            <Icon :name="summaryStatusClass === 'completed' ? 'check' : summaryStatusClass === 'failed' ? 'alert' : 'refresh'" :size="13" />{{ summaryStatusText }}
          </span>
        </div>
      </div>
      <div class="latest-report-body">
        <div v-if="latestBatch || report" class="latest-report-copy">
          <span class="report-icon"><Icon name="report" :size="26" /></span>
          <div>
            <h3>{{ titleText }}</h3>
            <time>{{ formatTime(summaryTime) }} 生成</time>
          </div>
        </div>
        <div v-else class="latest-report-copy service-latest-empty">
          <span class="report-icon"><Icon name="report" :size="26" /></span>
          <div><h3>还没有服务端批次报告</h3><p>在评估工作台导入真实会话并完成评估后，这里会汇总本批结果。</p><button class="view-report" type="button" @click="emit('navigate', 'workspace')">前往评估工作台</button></div>
        </div>
        <div class="risk-cards" aria-label="批次风险统计">
          <article v-for="card in summaryStats" :key="card.key" :class="['risk-card', `risk-${card.tone}`]">
            <span class="risk-icon"><Icon :name="card.icon" :size="18" /></span>
            <span class="risk-label">{{ card.label }}</span>
            <strong>{{ formatNumber(card.value) }}</strong>
            <small>{{ card.note }}</small>
          </article>
        </div>
      </div>
    </section>

    <section class="history-panel" aria-labelledby="service-history-title">
      <div class="history-heading"><h2 id="service-history-title">历史质检报告</h2><span>{{ filteredItems.length }} 份报告</span></div>
      <div v-if="recentError" class="service-history-error" role="alert"><Icon name="alert" :size="16" />{{ recentError }}</div>
      <div class="history-filters">
        <label class="history-search"><Icon name="search" :size="16" /><input v-model="query" type="search" placeholder="搜索报告编号或会话编号" aria-label="搜索报告" /></label>
        <select v-model="statusFilter" aria-label="按状态筛选"><option value="all">全部状态</option><option value="completed">已完成</option><option value="partial">部分完成</option><option value="failed">失败</option></select>
        <div class="date-filter"><Icon name="calendar" :size="15" /><label><span>开始日期</span><input v-model="startDate" type="date" /></label><Icon name="arrow" :size="13" /><label><span>结束日期</span><input v-model="endDate" type="date" /></label></div>
        <button class="reset-filter" type="button" @click="resetFilters">重置</button>
      </div>
      <div class="history-table-wrap">
        <table class="history-table service-history-table">
          <thead><tr><th>报告编号 / 批次名称</th><th><button type="button" @click="descending = !descending">生成时间<Icon name="chevron" :size="12" :class="{ ascending: !descending }" /></button></th><th>检测会话数</th><th>高风险</th><th>中风险</th><th>低风险</th><th>状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in visibleItems" :key="item.evaluation_id">
            <td><strong>{{ item.evaluation_id }}</strong><span>会话 · {{ item.session_id }}</span></td>
            <td><time>{{ formatTime(item.created_at) }}</time></td><td>1</td><td class="high-count">—</td><td class="medium-count">—</td><td class="low-count">—</td>
            <td><span :class="['table-status', item.status === 'partial' ? 'processing' : item.status]"><i aria-hidden="true"></i>{{ statusText[item.status] }}</span></td>
            <td><button class="view-report" type="button" @click="emit('openSession', item.session_id)">打开会话</button></td>
          </tr></tbody>
        </table>
      </div>
      <div class="history-cards">
        <article v-for="item in visibleItems" :key="item.evaluation_id" class="history-card">
          <div><strong>{{ item.evaluation_id }}</strong><span :class="['table-status', item.status === 'partial' ? 'processing' : item.status]"><i aria-hidden="true"></i>{{ statusText[item.status] }}</span></div>
          <p>会话 · {{ item.session_id }}</p>
          <dl><div><dt>生成时间</dt><dd>{{ formatTime(item.created_at) }}</dd></div><div><dt>检测会话</dt><dd>1</dd></div><div><dt>高 / 中 / 低风险</dt><dd>暂无历史风险统计</dd></div></dl>
          <button class="view-report" type="button" @click="emit('openSession', item.session_id)">在工作台打开会话</button>
        </article>
      </div>
      <div v-if="!visibleItems.length" class="history-empty"><Icon :name="recentError ? 'alert' : 'search'" :size="26" /><strong>{{ recentError ? '暂时无法读取运行记录' : '没有找到匹配报告' }}</strong><p>{{ recentError ? '请检查服务连接后重试。' : '请调整编号、状态或日期范围。' }}</p><button v-if="!recentError" type="button" @click="resetFilters">清除筛选</button></div>
      <footer v-if="filteredItems.length" class="history-pagination">
        <button type="button" aria-label="上一页" :disabled="currentPage === 1" @click="currentPage--"><Icon class="flip-icon" name="chevron" :size="14" /></button>
        <button v-for="page in totalPages" :key="page" type="button" :class="{ active: currentPage === page }" :aria-current="currentPage === page ? 'page' : undefined" @click="currentPage = page">{{ page }}</button>
        <button type="button" aria-label="下一页" :disabled="currentPage === totalPages" @click="currentPage++"><Icon name="chevron" :size="14" /></button>
      </footer>
    </section>
    <p class="reports-note"><Icon name="info" :size="14" />报告摘要由后端返回；旧报告的完整评分与证据请在评估工作台查看，历史列表最多显示 20 条。</p>
  </div>
</template>

<style scoped src="../styles/reports.css"></style>
<style scoped>
.service-reports-page { display: grid; gap: 18px; }
.service-reports-page .reports-heading,
.service-reports-page .latest-report-panel { margin-bottom: 0; }
.service-connection-state { display: inline-flex; align-items: center; gap: 7px; padding: 5px 10px; border: 1px solid #e6e5dc; border-radius: 999px; background: #fbfaf4; color: #806a42; font-size: 13px; font-weight: 600; }
.service-connection-state i { width: 7px; height: 7px; border-radius: 50%; background: #c59642; }
.service-connection-state.connected { border-color: #cde7d6; background: #eff8f1; color: #26764f; }
.service-connection-state.connected i { background: #29a36a; }
.service-reports-page .report-status.failed { background: #fff0ef; color: #ad525a; }
.service-reports-page .report-status.failed svg { color: #c75b63; }
.service-reports-page .reports-action:disabled { cursor: not-allowed; opacity: .55; box-shadow: none; }
.service-reports-page .table-status.failed { color: #b25159; }
.service-reports-page .table-status.failed i { background: #d66d72; }
.service-latest-empty > div > p { max-width: 38ch; margin-top: 7px; color: #637569; font-size: 12.5px; line-height: 1.7; }
.service-latest-empty .view-report { margin-top: 9px; }
.service-history-error { display: flex; align-items: center; gap: 8px; padding: 10px 14px; margin: 12px 20px 0; border: 1px solid #efd4d7; border-radius: 8px; background: #fff6f5; color: #a84c55; font-size: 12.5px; }
.service-history-table { min-width: 900px; }
.service-detail-grid .detail-score { min-height: 150px; }
.service-dimension-row { grid-template-columns: minmax(100px, 1fr) minmax(55px, 1fr) 30px 38px; }
.service-dimension-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.service-dimension-row > small { font-size: 11px; }
.service-report-actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px 14px; padding: 18px 20px 0; margin-top: 16px; border-top: 1px solid #e7eee8; }
.service-report-actions label { display: inline-flex; align-items: center; gap: 7px; color: #63766a; font-size: 12px; }
.service-report-actions input { accent-color: #16815a; }
.sample-item { align-items: start; }
.sample-item .view-report { justify-self: start; margin-top: 4px; }
@media (max-width: 760px) {
  .service-reports-page { gap: 13px; }
  .service-history-error { margin-inline: 14px; }
  .service-report-actions { align-items: stretch; flex-direction: column; }
  .service-report-actions label { align-items: flex-start; }
  .service-report-actions .reports-action { width: 100%; }
  .service-dimension-row { grid-template-columns: minmax(82px, 1fr) minmax(40px, .8fr) 28px 34px; gap: 5px; }
}
</style>

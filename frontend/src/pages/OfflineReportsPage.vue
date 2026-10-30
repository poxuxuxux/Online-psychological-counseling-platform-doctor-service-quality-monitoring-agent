<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Icon from '../components/base/Icon.vue'
import { createQualityReports, reportStatusText, type QualityReport, type QualityReportStatus } from '../data/reportsPreview'
import { isDateInRange, useDateRange } from '../composables/dateRange'

const emit = defineEmits<{ notify: [message: string] }>()
const reports = ref<QualityReport[]>(createQualityReports())
const dateRange = useDateRange()
const latestReport = computed(() => reports.value.find((report) => report.status === 'completed') || reports.value[0]!)
const query = ref('')
const statusFilter = ref<'all' | QualityReportStatus>('all')
const startDate = ref('')
const endDate = ref('')
const descending = ref(true)
const currentPage = ref(1)
const pageSize = 8

const filteredReports = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return reports.value
    .filter((report) => {
      const day = report.createdAt.slice(0, 10)
      return (statusFilter.value === 'all' || report.status === statusFilter.value) &&
        (!keyword || `${report.id} ${report.title}`.toLowerCase().includes(keyword)) &&
        isDateInRange(day, dateRange.value) &&
        (!startDate.value || day >= startDate.value) &&
        (!endDate.value || day <= endDate.value)
    })
    .sort((a, b) => descending.value ? b.createdAt.localeCompare(a.createdAt) : a.createdAt.localeCompare(b.createdAt))
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredReports.value.length / pageSize)))
const visibleReports = computed(() => filteredReports.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const completedReports = computed(() => reports.value.filter((report) => report.status === 'completed').sort((a, b) => a.createdAt.localeCompare(b.createdAt)))

function percent(value: number, total: number) {
  return total ? `${((value / total) * 100).toFixed(1)}%` : '—'
}
function formatNumber(value: number) {
  return value.toLocaleString('zh-CN')
}
function trendValues(field: 'total' | 'high' | 'medium' | 'low') {
  return completedReports.value.slice(-8).map((report) => report[field])
}
function sparkPath(values: number[]) {
  if (!values.length) return ''
  const max = Math.max(...values)
  const min = Math.min(...values)
  return values.map((value, index) => {
    const x = (index / Math.max(1, values.length - 1)) * 112 + 4
    const y = max === min ? 18 : 31 - ((value - min) / (max - min)) * 22
    return `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`
  }).join(' ')
}
function areaPath(values: number[]) {
  const line = sparkPath(values)
  return line ? `${line} L116 36 L4 36 Z` : ''
}
function resetFilters() {
  query.value = ''
  statusFilter.value = 'all'
  startDate.value = ''
  endDate.value = ''
  currentPage.value = 1
}
function exportReport() {
  const content = JSON.stringify({ dataType: 'offline-synthetic-demo', exportedAt: new Date().toISOString(), report: latestReport.value }, null, 2)
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `心衡-${latestReport.value.id}-离线质检报告.json`
  anchor.click()
  URL.revokeObjectURL(url)
  emit('notify', '离线质检报告已导出为 JSON 文件。')
}
watch([query, statusFilter, startDate, endDate, () => dateRange.value.start, () => dateRange.value.end], () => { currentPage.value = 1 })
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })
</script>

<template>
  <div class="quality-reports-page">
    <header class="reports-heading">
      <div><div class="reports-title-line"><h1>质检报告</h1><span class="reports-offline"><i aria-hidden="true"></i>离线演示</span></div><p>查看最近批次质检结果与历史批次报告。</p></div>
      <button class="reports-action secondary" type="button" @click="exportReport"><Icon name="download" :size="16" />导出当前报告</button>
    </header>

    <section class="latest-report-panel" aria-labelledby="latest-report-title">
      <div class="latest-report-heading">
        <h2 id="latest-report-title">最近批次报告</h2>
        <div class="latest-report-controls">
          <span :class="['report-status', latestReport.status]"><Icon name="check" :size="13" />{{ reportStatusText[latestReport.status] }}</span>
        </div>
      </div>
      <div class="latest-report-body">
        <div class="latest-report-copy">
          <span class="report-icon"><Icon name="report" :size="26" /></span>
          <div>
            <h3>{{ latestReport.id }}</h3>
            <time>{{ latestReport.createdAt }} 生成</time>
          </div>
        </div>
        <div class="risk-cards" aria-label="批次风险统计">
          <article v-for="card in [
            { key: 'total', label: '检测会话数', icon: 'message', value: latestReport.total, subtext: '本批全部会话' },
            { key: 'high', label: '高风险', icon: 'alert', value: latestReport.high, subtext: percent(latestReport.high, latestReport.total) },
            { key: 'medium', label: '中风险', icon: 'alert', value: latestReport.medium, subtext: percent(latestReport.medium, latestReport.total) },
            { key: 'low', label: '低风险', icon: 'check', value: latestReport.low, subtext: percent(latestReport.low, latestReport.total) },
          ]" :key="card.key" :class="['risk-card', `risk-${card.key}`]">
            <span class="risk-icon"><Icon :name="card.icon" :size="18" /></span>
            <span class="risk-label">{{ card.label }}</span>
            <strong>{{ formatNumber(card.value) }}</strong>
            <small>{{ card.subtext }}</small>
            <svg class="risk-sparkline" viewBox="0 0 120 36" aria-hidden="true"><path class="spark-area" :d="areaPath(trendValues(card.key as 'total' | 'high' | 'medium' | 'low'))" /><path class="spark-line" :d="sparkPath(trendValues(card.key as 'total' | 'high' | 'medium' | 'low'))" /></svg>
          </article>
        </div>
      </div>
    </section>

    <section class="history-panel" aria-labelledby="history-title">
      <div class="history-heading"><h2 id="history-title">历史质检报告</h2><span>{{ filteredReports.length }} 份报告</span></div>
      <div class="history-filters">
        <label class="history-search"><Icon name="search" :size="16" /><input v-model="query" type="search" placeholder="搜索报告编号或批次名称" aria-label="搜索报告" /></label>
        <select v-model="statusFilter" aria-label="按状态筛选"><option value="all">全部状态</option><option value="completed">已完成</option><option value="processing">处理中</option></select>
        <div class="date-filter"><Icon name="calendar" :size="15" /><label><span>开始日期</span><input v-model="startDate" type="date" /></label><Icon name="arrow" :size="13" /><label><span>结束日期</span><input v-model="endDate" type="date" /></label></div>
        <button class="reset-filter" type="button" @click="resetFilters">重置</button>
      </div>
      <div class="history-table-wrap">
        <table class="history-table">
          <thead><tr><th>报告编号 / 批次名称</th><th><button type="button" @click="descending = !descending">生成时间<Icon name="chevron" :size="12" :class="{ ascending: !descending }" /></button></th><th>检测会话数</th><th>高风险</th><th>中风险</th><th>低风险</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="report in visibleReports" :key="report.id">
              <td><strong>{{ report.id }}</strong><span>{{ report.title }}</span></td>
              <td><time>{{ report.createdAt }}</time></td>
              <td>{{ report.status === 'completed' ? formatNumber(report.total) : '—' }}</td>
              <td class="high-count">{{ report.status === 'completed' ? formatNumber(report.high) : '—' }} <small v-if="report.total">({{ percent(report.high, report.total) }})</small></td>
              <td class="medium-count">{{ report.status === 'completed' ? formatNumber(report.medium) : '—' }} <small v-if="report.total">({{ percent(report.medium, report.total) }})</small></td>
              <td class="low-count">{{ report.status === 'completed' ? formatNumber(report.low) : '—' }} <small v-if="report.total">({{ percent(report.low, report.total) }})</small></td>
              <td><span :class="['table-status', report.status]"><i aria-hidden="true"></i>{{ reportStatusText[report.status] }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="history-cards">
        <article v-for="report in visibleReports" :key="report.id" class="history-card">
          <div><strong>{{ report.id }}</strong><span :class="['table-status', report.status]"><i aria-hidden="true"></i>{{ reportStatusText[report.status] }}</span></div>
          <p>{{ report.title }}</p>
          <dl><div><dt>生成时间</dt><dd>{{ report.createdAt }}</dd></div><div><dt>检测会话</dt><dd>{{ report.status === 'completed' ? formatNumber(report.total) : '—' }}</dd></div><div><dt>高 / 中 / 低风险</dt><dd>{{ report.status === 'completed' ? `${report.high} / ${report.medium} / ${report.low}` : '—' }}</dd></div></dl>
        </article>
      </div>
      <div v-if="!visibleReports.length" class="history-empty"><Icon name="search" :size="26" /><strong>没有找到匹配报告</strong><p>请调整编号、状态或日期范围。</p><button type="button" @click="resetFilters">清除筛选</button></div>
      <footer class="history-pagination">
        <button type="button" aria-label="上一页" :disabled="currentPage === 1" @click="currentPage--"><Icon class="flip-icon" name="chevron" :size="14" /></button>
        <button v-for="page in totalPages" :key="page" type="button" :class="{ active: currentPage === page }" :aria-current="currentPage === page ? 'page' : undefined" @click="currentPage = page">{{ page }}</button>
        <button type="button" aria-label="下一页" :disabled="currentPage === totalPages" @click="currentPage++"><Icon name="chevron" :size="14" /></button>
      </footer>
    </section>
    <p class="reports-note"><Icon name="info" :size="14" />本页报告与趋势均为合成离线数据，未连接后端，不用于真实服务质量结论。</p>
  </div>
</template>

<style scoped src="../styles/reports.css"></style>

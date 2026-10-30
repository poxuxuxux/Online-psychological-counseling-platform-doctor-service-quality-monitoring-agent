<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Icon from '../components/base/Icon.vue'
import ReviewScoreDialog, { type ReviewScoreSubmission } from '../components/feedback/ReviewScoreDialog.vue'
import {
  createReviewSessions,
  riskText,
  type ReviewGroup,
  type ReviewMetric,
  type ReviewRisk,
  type ReviewSession,
} from '../data/reviewPreview'
import { isDateInRange, useDateRange } from '../composables/dateRange'

const emit = defineEmits<{ navigate: [page: 'workspace' | 'reports']; notify: [message: string] }>()
const sessions = ref<ReviewSession[]>(createReviewSessions())
const dateRange = useDateRange()
const query = ref('')
const riskFilter = ref<'all' | ReviewRisk>('all')
const currentPage = ref(1)
const pageSize = 6
const selectedId = ref(sessions.value[0]!.id)
const viewMode = ref<'original' | 'structured'>('original')
const showAllMessages = ref(false)
const activeMetric = ref<ReviewMetric | null>(null)
const collapsedGroups = ref<string[]>([])
const metricFilter = ref<'all' | 'attention'>('all')
const reviewDialogOpen = ref(false)
const reviewResults = ref<Record<string, ReviewScoreSubmission>>({})

const periodSessions = computed(() => sessions.value.filter((item) => isDateInRange(item.updatedAt, dateRange.value)))
const selected = computed(() => periodSessions.value.find((item) => item.id === selectedId.value) || periodSessions.value[0] || sessions.value[0]!)
const riskCounts = computed(() => ({
  high: periodSessions.value.filter((item) => item.risk === 'high').length,
  medium: periodSessions.value.filter((item) => item.risk === 'medium').length,
  low: periodSessions.value.filter((item) => item.risk === 'low').length,
}))
const filteredSessions = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return periodSessions.value.filter((item) =>
    (riskFilter.value === 'all' || item.risk === riskFilter.value) &&
    (!keyword || `${item.id} ${item.doctor} ${item.patient}`.toLowerCase().includes(keyword)),
  )
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredSessions.value.length / pageSize)))
const visibleSessions = computed(() => filteredSessions.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const visibleMessages = computed(() => showAllMessages.value ? selected.value.messages : selected.value.messages.slice(0, 6))
const visibleGroups = computed(() => selected.value.groups.map((group) => ({
  ...group,
  metrics: group.metrics.filter((metric) => metricFilter.value === 'all' || metric.score < 3),
})).filter((group) => group.metrics.length))
const scoreMetrics = computed(() => selected.value.groups.flatMap((group) => group.metrics.map(({ code, name, score }) => ({ code, name, score }))))
const submittedCount = computed(() => periodSessions.value.filter((item) => item.status === 'submitted').length)

function groupAverage(group: ReviewGroup) {
  return (group.metrics.reduce((sum, metric) => sum + metric.score, 0) / group.metrics.length).toFixed(1)
}
function selectSession(id: string) {
  if (id === selectedId.value) return
  selectedId.value = id
  activeMetric.value = null
  highlightedIds.value = []
  showAllMessages.value = false
  viewMode.value = 'original'
  metricFilter.value = 'all'
  reviewDialogOpen.value = false
}
function toggleGroup(id: string) {
  collapsedGroups.value = collapsedGroups.value.includes(id)
    ? collapsedGroups.value.filter((item) => item !== id)
    : [...collapsedGroups.value, id]
}
function chooseMetric(metric: ReviewMetric) {
  activeMetric.value = activeMetric.value?.code === metric.code ? null : metric
}
const highlightedIds = ref<string[]>([])
async function locateEvidence(id: string) {
  viewMode.value = 'original'
  showAllMessages.value = true
  highlightedIds.value = [id]
  await nextTick()
  const target = document.getElementById(`review-${selected.value.id}-${id}`)
  target?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' })
  target?.focus({ preventScroll: true })
}
function resetFilters() {
  query.value = ''
  riskFilter.value = 'all'
  currentPage.value = 1
}
function exportReview() {
  const content = JSON.stringify({
    dataType: 'offline-synthetic-demo',
    exportedAt: new Date().toISOString(),
    session: selected.value,
    review: reviewResults.value[selected.value.id] || null,
  }, null, 2)
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `心衡-${selected.value.id}-复核草稿.json`
  anchor.click()
  URL.revokeObjectURL(url)
  emit('notify', '复核草稿已导出为 JSON 文件。')
}
function submitReview(result: ReviewScoreSubmission) {
  reviewResults.value[selected.value.id] = result
  selected.value.status = 'submitted'
  reviewDialogOpen.value = false
  emit('notify', `${selected.value.id} 复核结果已在本页保存，当前为离线演示。`)
}
watch([query, riskFilter], () => { currentPage.value = 1 })
watch([() => dateRange.value.start, () => dateRange.value.end], () => {
  currentPage.value = 1
  selectedId.value = periodSessions.value[0]?.id || ''
})
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })
</script>

<template>
  <div class="review-page">
    <header class="review-heading">
      <div><h1>人工复核</h1><p>对高风险或不确定的咨询进行人工复核，确保评价的准确性与公正性。</p></div>
      <button class="review-action secondary" type="button" :disabled="!periodSessions.length" @click="exportReview"><Icon name="download" :size="16" />导出复核草稿</button>
    </header>
    <section class="review-stats" aria-label="复核统计">
      <article class="stat-card total"><span class="stat-icon"><Icon name="message" :size="20" /></span><div><small>待复核会话数</small><strong>{{ periodSessions.length - submittedCount }}</strong><span>所选时间范围</span></div><i aria-hidden="true"></i></article>
      <article class="stat-card high"><span class="stat-icon"><Icon name="alert" :size="20" /></span><div><small>高风险会话</small><strong>{{ riskCounts.high }}</strong><span>存在明显风险</span></div><i aria-hidden="true"></i></article>
      <article class="stat-card medium"><span class="stat-icon"><Icon name="clock" :size="20" /></span><div><small>中风险会话</small><strong>{{ riskCounts.medium }}</strong><span>需进一步确认</span></div><i aria-hidden="true"></i></article>
      <article class="stat-card low"><span class="stat-icon"><Icon name="check" :size="20" /></span><div><small>低风险会话</small><strong>{{ riskCounts.low }}</strong><span>基本符合要求</span></div><i aria-hidden="true"></i></article>
    </section>

    <div v-if="periodSessions.length" class="review-layout">
      <section class="review-panel session-panel" aria-labelledby="review-list-title">
        <div class="panel-title-row"><div><h2 id="review-list-title">待复核会话列表</h2><p>{{ filteredSessions.length }} 条本地会话</p></div><span class="panel-count">{{ periodSessions.length }}</span></div>
        <div class="review-filters">
          <label class="review-search"><Icon name="search" :size="16" /><input v-model="query" type="search" placeholder="搜索会话 ID / 患者名 / 医生姓名" aria-label="搜索复核会话" /></label>
          <button class="filter-button" type="button" :class="{ active: riskFilter !== 'all' }" :aria-expanded="riskFilter !== 'all'" @click="riskFilter = riskFilter === 'all' ? 'high' : 'all'"><Icon name="list" :size="15" /></button>
        </div>
        <div class="risk-tabs" role="group" aria-label="风险筛选">
          <button type="button" :class="{ active: riskFilter === 'all' }" :aria-pressed="riskFilter === 'all'" @click="riskFilter = 'all'">全部 {{ periodSessions.length }}</button>
          <button type="button" :class="{ active: riskFilter === 'high' }" :aria-pressed="riskFilter === 'high'" @click="riskFilter = 'high'">高 {{ riskCounts.high }}</button>
          <button type="button" :class="{ active: riskFilter === 'medium' }" :aria-pressed="riskFilter === 'medium'" @click="riskFilter = 'medium'">中 {{ riskCounts.medium }}</button>
          <button type="button" :class="{ active: riskFilter === 'low' }" :aria-pressed="riskFilter === 'low'" @click="riskFilter = 'low'">低 {{ riskCounts.low }}</button>
        </div>
        <div class="review-list">
          <button v-for="item in visibleSessions" :key="item.id" :class="['review-item', `risk-${item.risk}`, { selected: item.id === selectedId }]" type="button" :aria-pressed="item.id === selectedId" @click="selectSession(item.id)">
            <span class="review-item-top"><strong>{{ item.id }}</strong><span :class="['risk-badge', item.risk]"><i aria-hidden="true"></i>{{ riskText[item.risk] }}</span></span>
            <span class="review-item-meta"><span>{{ item.doctor }}</span><time>{{ item.updatedAt }}</time><span>{{ item.messageCount }} 条消息</span></span>
          </button>
          <div v-if="!visibleSessions.length" class="review-empty"><Icon name="search" :size="24" /><strong>没有匹配会话</strong><p>请调整关键词或风险筛选。</p><button type="button" @click="resetFilters">清除筛选</button></div>
        </div>
        <footer class="review-pagination">
          <button type="button" aria-label="上一页" :disabled="currentPage === 1" @click="currentPage--"><Icon class="flip-icon" name="chevron" :size="14" /></button>
          <button v-for="page in totalPages" :key="page" type="button" :class="{ active: currentPage === page }" :aria-current="currentPage === page ? 'page' : undefined" @click="currentPage = page">{{ page }}</button>
          <button type="button" aria-label="下一页" :disabled="currentPage === totalPages" @click="currentPage++"><Icon name="chevron" :size="14" /></button>
        </footer>
      </section>

      <section class="review-panel conversation-panel" aria-labelledby="review-conversation-title">
        <div class="panel-title-row conversation-heading">
          <div><h2 id="review-conversation-title">会话内容</h2><p>{{ selected.id }} · {{ selected.doctor }}</p></div>
          <div class="view-tabs" role="group" aria-label="记录视图">
            <button type="button" :class="{ active: viewMode === 'original' }" :aria-pressed="viewMode === 'original'" @click="viewMode = 'original'">原文</button>
            <button type="button" :class="{ active: viewMode === 'structured' }" :aria-pressed="viewMode === 'structured'" @click="viewMode = 'structured'">结构化视图</button>
          </div>
        </div>
        <div v-if="viewMode === 'original'" class="conversation-list">
          <article v-for="message in visibleMessages" :id="`review-${selected.id}-${message.id}`" :key="message.id" :class="['review-message', message.role, { highlighted: highlightedIds.includes(message.id) }]" tabindex="-1">
            <span class="message-avatar" aria-hidden="true">{{ message.role === 'doctor' ? '医' : '访' }}</span>
            <div class="message-content">
              <div class="message-meta"><strong>{{ message.role === 'doctor' ? '医生' : '患者' }}</strong><time>{{ message.time }}</time></div>
              <p class="message-bubble">{{ message.content }}</p>
              <button v-if="message.evidence" class="evidence-tag" type="button" @click="locateEvidence(message.id)"><Icon name="link" :size="12" />证据 {{ message.evidence }}</button>
            </div>
          </article>
        </div>
        <div v-else class="structured-view">
          <table><thead><tr><th>序号</th><th>角色</th><th>时间</th><th>消息内容</th></tr></thead><tbody><tr v-for="(message, index) in selected.messages" :key="message.id"><td>{{ index + 1 }}</td><td>{{ message.role === 'doctor' ? '医生' : '患者' }}</td><td>{{ message.time }}</td><td>{{ message.content }}</td></tr></tbody></table>
        </div>
        <footer class="conversation-footer">
          <button type="button" @click="showAllMessages = !showAllMessages"><Icon name="chevron" :size="13" :class="{ 'rotate-icon': showAllMessages }" />消息 {{ visibleMessages.length }} / {{ selected.messageCount }}</button>
          <span>查看证据定位</span>
        </footer>
      </section>

      <aside class="review-side">
        <section class="review-panel result-panel" aria-labelledby="review-result-title">
          <div class="panel-title-row result-heading"><div><h2 id="review-result-title">AI 评价结果</h2><p>{{ selected.messageCount }} 条消息 · 18 项指标</p></div><div class="result-heading-actions"><span :class="['result-risk', selected.risk]"><i aria-hidden="true"></i>{{ riskText[selected.risk] }}</span><button class="result-review-button" type="button" @click="reviewDialogOpen = true"><Icon name="shield" :size="15" />人工复核</button></div></div>
          <div class="result-summary">
            <div class="overall-score"><span class="score-icon"><Icon name="medal" :size="20" /></span><div><small>综合得分</small><strong>{{ (selected.score * 20).toFixed(1) }}<em>/ 100</em></strong></div></div>
            <div class="ai-conclusion"><strong>AI 评价结论</strong><p>{{ selected.conclusion }}</p></div>
          </div>
          <div class="metric-toolbar"><strong>18 项评价指标</strong><select v-model="metricFilter" aria-label="筛选评价指标"><option value="all">全部指标</option><option value="attention">重点关注（低于 3 分）</option></select></div>
          <div class="metric-groups">
            <section v-for="group in visibleGroups" :key="group.id" :class="['metric-group', `group-${group.id.toLowerCase()}`]">
              <button class="metric-group-heading" type="button" :aria-expanded="!collapsedGroups.includes(group.id)" @click="toggleGroup(group.id)"><span class="group-icon"><Icon :name="group.icon" :size="15" /></span><strong>{{ group.name }}</strong><b>{{ groupAverage(group) }}</b><Icon class="group-chevron" name="chevron" :size="13" /></button>
              <div v-show="!collapsedGroups.includes(group.id)" class="metric-list">
                <button v-for="metric in group.metrics" :key="metric.code" :class="['metric-row', { active: activeMetric?.code === metric.code }]" type="button" :aria-pressed="activeMetric?.code === metric.code" @click="chooseMetric(metric)">
                  <span>{{ metric.code }}</span><span class="metric-name">{{ metric.name }}</span><i><b :style="{ width: `${metric.score * 20}%` }"></b></i><strong :class="{ low: metric.score < 3 }">{{ metric.score.toFixed(1) }}</strong>
                </button>
              </div>
            </section>
            <div v-if="!visibleGroups.length" class="metric-empty">当前筛选下没有指标。<button type="button" @click="metricFilter = 'all'">查看全部</button></div>
          </div>
          <div v-if="activeMetric" class="metric-detail">
            <div><span>{{ activeMetric.code }}</span><strong>{{ activeMetric.name }}</strong><b>{{ activeMetric.score.toFixed(1) }}</b></div>
            <p>{{ activeMetric.rationale }}</p>
            <button type="button" @click="locateEvidence(activeMetric.evidenceId)"><Icon name="link" :size="13" />查看原文证据</button>
          </div>
        </section>
      </aside>
    </div>
    <div v-else class="surface review-range-empty"><Icon name="calendar" :size="28" /><strong>所选时间范围内没有待复核会话</strong><p>调整顶栏日期范围后，复核列表和统计会同步更新。</p></div>
    <p class="review-page-note"><Icon name="info" :size="14" />本页全部内容为合成离线数据，未连接后端，不用于真实医疗或服务质量结论。</p>
    <ReviewScoreDialog v-if="reviewDialogOpen" :title="selected.id" :metrics="scoreMetrics" :overall-score="selected.score * 20" offline @close="reviewDialogOpen = false" @submit="submitReview" />
  </div>
</template>

<style scoped src="../styles/review.css"></style>

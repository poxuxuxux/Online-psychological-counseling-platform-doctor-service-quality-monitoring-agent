<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowLeft, ArrowRight, CircleAlert, FileCheck2, History, Link2, ShieldCheck } from 'lucide-vue-next'
import { metricCatalog } from '../../../api/demoData'
import { service } from '../../../api/service'
import StatusBadge from '../../../components/base/StatusBadge.vue'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { EvaluationRun } from '../../../types/domain'
import { metricTone, runTone, shortDate } from '../../../utils/display'

const route = useRoute()
const run = ref<EvaluationRun | null>(null)
const loading = ref(true)
const error = ref('')
const activeDimension = ref('全部')
const activeMessage = ref('')
const dimensions = [...new Set(metricCatalog.map((metric) => metric.dimension))]
const visibleResults = computed(() => run.value?.results.filter((item) => activeDimension.value === '全部' || metricCatalog.find((metric) => metric.id === item.metricId)?.dimension === activeDimension.value) ?? [])

async function locate(messageId: string) {
  activeMessage.value = messageId
  await nextTick()
  document.getElementById(`message-${messageId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

onMounted(async () => {
  try { run.value = await service.run(String(route.params.id)) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '任务详情加载失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page-stack">
    <RouterLink to="/evaluations" class="back-link"><ArrowLeft :size="16" />返回评价任务</RouterLink>
    <div v-if="loading" class="loading-state">正在加载任务详情…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div>
    <template v-else-if="run">
      <div class="page-heading page-heading--with-action"><div><span class="eyebrow">EVALUATION REPORT · {{ run.id }}</span><h1>咨询服务评价详情</h1><p>{{ run.round }} · {{ run.sessionId }} · {{ run.doctorRef }} · {{ shortDate(run.createdAt) }}</p></div><StatusBadge :label="run.status" :tone="runTone(run.status)" /></div>
      <div class="detail-summary"><div><span>评价范围</span><strong>一次咨询轮次</strong></div><div><span>已处理指标</span><strong>{{ run.evaluatedMetrics }} / {{ run.totalMetrics }}</strong></div><div><span>指标版本</span><strong>{{ run.rubricVersion }}</strong></div><div><span>人工复核</span><strong>{{ run.reviewRequired ? '需要复核' : '当前无需复核' }}</strong></div></div>
      <div class="notice" :class="run.reviewRequired ? 'notice--amber' : 'notice--blue'"><CircleAlert :size="18" /><div><strong>{{ run.reviewRequired ? '有待核查的评价线索' : '本次样例未触发人工复核' }}</strong><span>{{ run.issue }}</span></div><RouterLink v-if="run.caseId" :to="`/review/${run.caseId}`" class="inline-link">进入复核<ArrowRight :size="15" /></RouterLink></div>
      <div class="detail-grid">
        <section class="panel panel--flush"><div class="panel-heading"><div><span class="eyebrow">18 METRICS · 6 DIMENSIONS</span><h2>指标评价</h2></div><span class="muted-small">不适用与证据不足分别记录</span></div><div class="chip-row"><button v-for="dimension in ['全部', ...dimensions]" :key="dimension" class="chip" :class="{ 'chip--active': activeDimension === dimension }" @click="activeDimension = dimension">{{ dimension }}</button></div><EmptyState v-if="!visibleResults.length" title="暂无可展示指标" description="该任务可能部分完成，尚未生成相应评价。" /><div v-else class="metric-list"><article v-for="item in visibleResults" :key="item.metricId" class="metric-row"><div class="metric-row__head"><span class="metric-code">{{ item.metricId }}</span><strong>{{ metricCatalog.find((metric) => metric.id === item.metricId)?.name }}</strong><StatusBadge :label="item.state" :tone="metricTone(item.state)" /></div><p>{{ item.reason }}</p><div class="metric-row__foot"><span>{{ metricCatalog.find((metric) => metric.id === item.metricId)?.owner }}</span><button v-for="evidence in item.evidence" :key="evidence.messageId" class="evidence-link" @click="locate(evidence.messageId)"><Link2 :size="14" />定位 {{ evidence.messageId }}</button></div></article></div></section>
        <aside class="detail-side"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">CURRENT SESSION</span><h2>本次咨询证据</h2></div><FileCheck2 :size="19" /></div><EmptyState v-if="!run.messages.length" title="原文不可用" description="当前任务资料不完整，不能据此推断医生行为。" /><div v-else class="timeline"><div v-for="message in run.messages" :id="`message-${message.id}`" :key="message.id" class="timeline-item" :class="{ 'timeline-item--doctor': message.role === '医生', 'timeline-item--active': activeMessage === message.id }"><div class="timeline-item__meta"><b>{{ message.role }}</b><span>{{ message.id }} · {{ shortDate(message.at) }}</span></div><p>{{ message.content }}</p></div></div></section><section v-if="run.history.length" class="panel history-panel"><div class="panel-heading"><div><span class="eyebrow">HISTORY CONTEXT</span><h2>复诊历史背景</h2></div><History :size="19" /></div><div v-for="item in run.history" :key="item.sessionId" class="history-item"><strong>{{ item.date }} · {{ item.sessionId }}</strong><p>{{ item.content }}</p></div><div class="history-panel__note"><ShieldCheck :size="15" />历史背景不作为本次评分的直接证据</div></section></aside>
      </div>
    </template>
  </div>
</template>

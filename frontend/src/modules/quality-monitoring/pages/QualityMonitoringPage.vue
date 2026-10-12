<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, ArrowRight, BarChart3, CircleHelp } from 'lucide-vue-next'
import { metricCatalog } from '../../../api/demoData'
import { service } from '../../../api/service'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { EvaluationRun } from '../../../types/domain'

const runs = ref<EvaluationRun[]>([])
const loading = ref(true)
const error = ref('')
const dimensions = [...new Set(metricCatalog.map((metric) => metric.dimension))]
const completed = computed(() => runs.value.filter((run) => run.status === '已完成'))
const rows = computed(() => dimensions.map((dimension) => {
  const ids = metricCatalog.filter((metric) => metric.dimension === dimension).map((metric) => metric.id)
  const result = completed.value.flatMap((run) => run.results.filter((item) => ids.includes(item.metricId)))
  return { dimension, metricCount: ids.length, applicable: result.filter((item) => item.state !== '不适用').length, review: result.filter((item) => item.state === '需复核').length, insufficient: result.filter((item) => item.state === '证据不足').length, total: result.length }
}))

onMounted(async () => {
  try { runs.value = await service.runs() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '质量监测数据加载失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page-stack"><div class="page-heading"><span class="eyebrow">QUALITY MONITORING</span><h1>服务质量监测</h1><p>按六个维度查看合成样例的指标覆盖与待复核情况。</p></div><div class="notice notice--blue"><CircleHelp :size="19" /><div><strong>小样本展示说明</strong><span>当前仅有 {{ completed.length }} 份已完成的合成报告。这里展示指标状态数量，不推断真实质量趋势，也不生成医生排名或总评分。</span></div></div><div v-if="loading" class="loading-state">正在加载维度数据…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div><template v-else><div class="quality-hero"><span class="quality-hero__icon"><Activity :size="27" /></span><div><span class="eyebrow">METRIC COVERAGE</span><strong>六维服务质量画像</strong><p>可靠性、响应性、专业信息沟通、情感共情性、咨询协作性与心理风险应对。</p></div><div class="quality-hero__number"><strong>06</strong><span>评价维度</span></div></div><div v-if="!completed.length" class="panel"><EmptyState title="暂无可分析的完成报告" /></div><div v-else class="dimension-grid"><article v-for="(row, index) in rows" :key="row.dimension" class="dimension-card"><div class="dimension-card__top"><span class="dimension-card__icon"><BarChart3 :size="19" /></span><span>0{{ index + 1 }} / 06</span></div><h2>{{ row.dimension }}</h2><p>{{ row.metricCount }} 项二级指标 · {{ completed.length }} 份报告</p><div class="dimension-card__bar"><span :style="{ width: `${row.total ? (row.applicable / row.total) * 100 : 0}%` }" /></div><div class="dimension-card__stats"><span><b>{{ row.applicable }}</b> 项适用记录</span><span><b>{{ row.review }}</b> 项待复核</span><span><b>{{ row.insufficient }}</b> 项证据不足</span></div></article></div><RouterLink to="/rubric" class="quality-link">查看完整18项指标及 Agent 归属<ArrowRight :size="16" /></RouterLink></template></div>
</template>

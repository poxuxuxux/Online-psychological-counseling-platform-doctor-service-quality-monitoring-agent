<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, CircleAlert, Filter, Search, ShieldAlert } from 'lucide-vue-next'
import { service } from '../../../api/service'
import StatusBadge from '../../../components/base/StatusBadge.vue'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { ReviewCase } from '../../../types/domain'
import { caseTone, shortDate } from '../../../utils/display'

const router = useRouter()
const cases = ref<ReviewCase[]>([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const state = ref('全部状态')
const priority = ref('全部级别')
const filtered = computed(() => cases.value.filter((item) => {
  const text = `${item.id} ${item.title} ${item.runId} ${item.category}`.toLowerCase()
  return (!query.value || text.includes(query.value.toLowerCase())) &&
    (state.value === '全部状态' || item.state === state.value) &&
    (priority.value === '全部级别' || item.priority === priority.value)
}))

onMounted(async () => {
  try { cases.value = await service.cases() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '案件加载失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page-stack">
    <div class="page-heading"><span class="eyebrow">RISK & REVIEW QUEUE</span><h1>风险中心</h1><p>集中处理需要人工核查的服务质量线索，保留证据与处理理由。</p></div>
    <div class="notice notice--amber"><CircleAlert :size="19" /><div><strong>线索不等于结论</strong><span>Hook 候选和 Agent 判断均为待核查信息，不代表临床诊断或已确认违规；D6 两项指标默认评价，不依赖 Hook 是否命中。</span></div></div>
    <div class="risk-stats"><div><ShieldAlert :size="19" /><span>待处理</span><strong>{{ cases.filter((item) => item.state === '待处理').length }}</strong></div><div><span class="risk-stats__dash" /><span>高优先级</span><strong>{{ cases.filter((item) => item.priority === '高' && item.state !== '已处理').length }}</strong></div><div><span class="risk-stats__dash risk-stats__dash--green" /><span>已处理</span><strong>{{ cases.filter((item) => item.state === '已处理').length }}</strong></div></div>
    <div class="panel panel--flush"><div class="list-toolbar"><div class="search-field"><Search :size="17" /><input v-model="query" aria-label="搜索复核案件" placeholder="搜索案件、类别或任务编号" /></div><div class="select-field"><Filter :size="16" /><select v-model="state" aria-label="处理状态"><option>全部状态</option><option>待处理</option><option>处理中</option><option>已处理</option></select></div><div class="select-field"><select v-model="priority" aria-label="优先级"><option>全部级别</option><option>高</option><option>中</option><option>低</option></select></div><span class="list-count">{{ filtered.length }} 条线索</span></div><div v-if="loading" class="loading-state">正在加载案件…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div><EmptyState v-else-if="!filtered.length" title="没有符合条件的案件" description="调整筛选条件后再试。" /><div v-else class="case-list"><article v-for="item in filtered" :key="item.id" class="case-row" @click="router.push(`/review/${item.id}`)"><span class="case-row__icon"><ShieldAlert :size="20" /></span><div class="case-row__main"><div class="case-row__title"><strong>{{ item.title }}</strong><StatusBadge :label="`${item.priority}优先级`" :tone="item.priority === '高' ? 'red' : 'amber'" /></div><p>{{ item.hookHint }}</p><div class="case-row__meta"><span>{{ item.id }}</span><span>{{ item.category }}</span><span>{{ shortDate(item.createdAt) }}</span></div></div><div class="case-row__end"><StatusBadge :label="item.state" :tone="caseTone(item.state)" /><ArrowRight :size="17" /></div></article></div></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Filter, Plus, Search, X } from 'lucide-vue-next'
import { dataMode, service } from '../../../api/service'
import StatusBadge from '../../../components/base/StatusBadge.vue'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { EvaluationRun } from '../../../types/domain'
import { runTone, shortDate } from '../../../utils/display'

const router = useRouter()
const runs = ref<EvaluationRun[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const filter = ref('全部')
const showCreate = ref(false)
const templateId = ref('EV-20261009-001')
const busy = ref(false)
const feedback = ref('')
const filtered = computed(() => runs.value.filter((run) => {
  const query = search.value.trim().toLowerCase()
  const matches = !query || `${run.id} ${run.sessionId} ${run.doctorRef} ${run.patientRef}`.toLowerCase().includes(query)
  return matches && (filter.value === '全部' || run.status === filter.value)
}))

async function load() {
  loading.value = true
  error.value = ''
  try { runs.value = await service.runs() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '任务加载失败。' }
  finally { loading.value = false }
}

async function create() {
  busy.value = true
  feedback.value = ''
  try {
    const run = await service.createDemoEvaluation(templateId.value)
    showCreate.value = false
    await router.push(`/evaluations/${run.id}`)
  } catch (cause) {
    feedback.value = cause instanceof Error ? cause.message : '创建失败。'
  } finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <div class="page-heading page-heading--with-action"><div><span class="eyebrow">EVALUATION RUNS</span><h1>评价任务</h1><p>按一次订单或咨询轮次查看评价进度，追踪每份报告的证据与限制。</p></div><button v-if="dataMode === 'demo'" class="button button--primary" @click="showCreate = true"><Plus :size="18" />创建演示任务</button></div>
    <div class="notice notice--blue"><strong>任务范围</strong><span>每份报告只对应一次咨询轮次；复诊历史作为单独背景展示，不并入本次评分证据。</span></div>
    <div class="panel panel--flush">
      <div class="list-toolbar"><div class="search-field"><Search :size="17" /><input v-model="search" aria-label="搜索任务" placeholder="搜索任务编号、医生编号或会话编号" /></div><div class="select-field"><Filter :size="16" /><select v-model="filter" aria-label="筛选任务状态"><option>全部</option><option>排队中</option><option>运行中</option><option>已完成</option><option>部分完成</option><option>失败</option></select></div><span class="list-count">共 {{ filtered.length }} 项</span></div>
      <div v-if="loading" class="loading-state">正在加载评价任务…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div><EmptyState v-else-if="!filtered.length" title="没有符合条件的任务" description="可调整搜索条件，或使用合成样例创建演示任务。" />
      <div v-else class="table-scroll"><table class="data-table data-table--roomy"><thead><tr><th>评价任务</th><th>咨询轮次</th><th>指标进度</th><th>更新时间</th><th>状态</th><th>复核</th><th></th></tr></thead><tbody><tr v-for="run in filtered" :key="run.id" @click="router.push(`/evaluations/${run.id}`)"><td><strong>{{ run.id }}</strong><small>{{ run.doctorRef }} · {{ run.patientRef }}</small></td><td>{{ run.round }}<small>{{ run.sessionId }}</small></td><td><div class="progress-inline"><span :style="{ width: `${run.totalMetrics ? (run.evaluatedMetrics / run.totalMetrics) * 100 : 0}%` }" /></div><small>{{ run.evaluatedMetrics }} / {{ run.totalMetrics }} 项</small></td><td>{{ shortDate(run.updatedAt) }}</td><td><StatusBadge :label="run.status" :tone="runTone(run.status)" /></td><td><span :class="run.reviewRequired ? 'text-amber' : 'text-muted'">{{ run.reviewRequired ? '需要复核' : '无需复核' }}</span></td><td><ArrowRight :size="16" /></td></tr></tbody></table></div>
    </div>
    <div class="helper-line">提示：演示任务只复制合成样例报告，不运行模型。真实任务创建需由后端提供评价 API。</div>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="create-title"><div class="modal__head"><div><span class="eyebrow">SYNTHETIC CASE</span><h2 id="create-title">创建演示任务</h2></div><button class="icon-button" aria-label="关闭" @click="showCreate = false"><X :size="20" /></button></div><p>选择一份合成案例，复制其预置报告以联调页面。此操作不调用评价模型，也不产生真实质检结论。</p><label class="form-label">合成样例<select v-model="templateId"><option value="EV-20261009-001">咨询目标协商样例 · 初诊</option><option value="EV-20261010-002">后续反馈样例 · 复诊</option><option value="EV-20261011-003">风险回应样例 · 初诊</option></select></label><p v-if="feedback" class="form-error" role="alert">{{ feedback }}</p><div class="modal__actions"><button class="button button--secondary" @click="showCreate = false">取消</button><button class="button button--primary" :disabled="busy" @click="create">{{ busy ? '创建中…' : '创建并查看' }}<ArrowRight :size="16" /></button></div></div></div>
  </div>
</template>

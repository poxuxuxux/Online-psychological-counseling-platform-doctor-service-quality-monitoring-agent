<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight, ArrowUpRight, CheckCircle2, ClipboardList, Clock3,
  FileSearch, ShieldAlert, Sparkles,
} from 'lucide-vue-next'
import { service } from '../../../api/service'
import StatusBadge from '../../../components/base/StatusBadge.vue'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { DashboardData } from '../../../types/domain'
import { runTone, shortDate } from '../../../utils/display'

const router = useRouter()
const data = ref<DashboardData | null>(null)
const loading = ref(true)
const error = ref('')
const total = computed(() => data.value?.runs.length ?? 0)
const completed = computed(() => data.value?.runs.filter((run) => run.status === '已完成').length ?? 0)
const pending = computed(() => data.value?.cases.filter((item) => item.state !== '已处理').length ?? 0)
const partial = computed(() => data.value?.runs.filter((run) => run.status === '部分完成').length ?? 0)
const highCases = computed(() => data.value?.cases.filter((item) => item.priority === '高' && item.state !== '已处理') ?? [])

onMounted(async () => {
  try {
    data.value = await service.dashboard()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '工作台数据加载失败。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page-stack">
    <div class="page-heading page-heading--with-action">
      <div><span class="eyebrow">QUALITY CONTROL OVERVIEW</span><h1>服务质量，一目了然</h1><p>从评价任务到复核线索，掌握本工作空间的质检进展。</p></div>
      <button class="button button--primary" @click="router.push('/evaluations')"><ClipboardList :size="17" />查看评价任务<ArrowRight :size="16" /></button>
    </div>

    <div v-if="loading" class="loading-state">正在加载工作台…</div>
    <div v-else-if="error" class="error-panel" role="alert">{{ error }}</div>
    <template v-else-if="data">
      <div class="overview-banner">
        <div class="overview-banner__icon"><Sparkles :size="23" /></div>
        <div><strong>让评价可解释，让复核有方向</strong><p>本页展示合成演示数据。真实质检结果需要完成后端接入及人工核查。</p></div>
        <span>当前样例 · {{ total }} 条任务</span>
      </div>

      <div class="stat-grid">
        <div class="stat-card"><div class="stat-card__top"><span>评价任务</span><span class="stat-icon stat-icon--blue"><ClipboardList :size="19" /></span></div><strong>{{ total }}</strong><small>当前演示数据中的任务总数</small></div>
        <div class="stat-card"><div class="stat-card__top"><span>已完成</span><span class="stat-icon stat-icon--green"><CheckCircle2 :size="19" /></span></div><strong>{{ completed }}</strong><small>可查看评价指标与证据</small></div>
        <div class="stat-card"><div class="stat-card__top"><span>待复核案件</span><span class="stat-icon stat-icon--amber"><ShieldAlert :size="19" /></span></div><strong>{{ pending }}</strong><small>模型线索等待人工确认</small></div>
        <div class="stat-card"><div class="stat-card__top"><span>部分完成</span><span class="stat-icon stat-icon--purple"><FileSearch :size="19" /></span></div><strong>{{ partial }}</strong><small>存在数据或证据限制</small></div>
      </div>

      <div class="overview-grid">
        <section class="panel panel--flush">
          <div class="panel-heading"><div><span class="eyebrow">RECENT ACTIVITY</span><h2>最近评价任务</h2></div><RouterLink to="/evaluations" class="text-link">查看全部<ArrowUpRight :size="16" /></RouterLink></div>
          <div v-if="!data.runs.length" class="panel-body"><EmptyState title="暂无评价任务" description="导入合成案例并创建任务后，会在这里展示进展。" /></div>
          <div v-else class="table-scroll"><table class="data-table"><thead><tr><th>任务编号 / 咨询轮次</th><th>医生编号</th><th>更新时间</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="run in data.runs.slice(0, 5)" :key="run.id" @click="router.push(`/evaluations/${run.id}`)"><td><strong>{{ run.id }}</strong><small>{{ run.round }} · {{ run.source }}</small></td><td>{{ run.doctorRef }}</td><td>{{ shortDate(run.updatedAt) }}</td><td><StatusBadge :label="run.status" :tone="runTone(run.status)" /></td><td><ArrowUpRight :size="16" /></td></tr></tbody></table></div>
        </section>

        <section class="panel attention-panel">
          <div class="panel-heading"><div><span class="eyebrow">NEEDS ATTENTION</span><h2>待处理重点</h2></div><span class="attention-count">{{ pending }}</span></div>
          <template v-if="highCases.length">
            <div v-for="item in highCases" :key="item.id" class="attention-item">
              <div class="attention-item__top"><StatusBadge :label="`${item.priority}优先级`" tone="red" /><span>{{ shortDate(item.createdAt) }}</span></div>
              <strong>{{ item.title }}</strong><p>线索需要人工核查，不代表已确认的诊断或违规事实。</p>
              <RouterLink :to="`/review/${item.id}`" class="inline-link">打开复核工作台<ArrowRight :size="15" /></RouterLink>
            </div>
          </template>
          <EmptyState v-else title="暂无高优先级待复核案件" />
          <div class="attention-footer"><Clock3 :size="16" />复核决定将保留理由与操作记录</div>
        </section>
      </div>

      <div class="overview-bottom">
        <section class="panel quick-panel"><div><span class="eyebrow">WORKFLOW</span><h2>评价闭环</h2><p>多 Agent 分工评价，证据核验与人工复核共同约束最终结论。</p></div><div class="workflow-mini"><span>01 数据接入</span><i /><span>02 协同评价</span><i /><span>03 证据核验</span><i /><span>04 人工复核</span></div></section>
        <section class="panel sample-panel"><span class="eyebrow">DATA NOTE</span><h2>关于当前数据</h2><p>当前演示案例均为合成对话。样本量较小，页面不展示医生排名、质量趋势结论或模型准确率。</p><RouterLink to="/quality" class="text-link">查看维度覆盖<ArrowUpRight :size="16" /></RouterLink></section>
      </div>
    </template>
  </div>
</template>

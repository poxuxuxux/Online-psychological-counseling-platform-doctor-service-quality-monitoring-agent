<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { metricRunsApi } from '../api/endpoints/metricRuns'
import type { MetricReport, MetricRound, MetricRun } from '../api/contracts/metricRuns'

const props = defineProps<{ preview: boolean }>()
const enabled = ref(false)
const accessCode = ref('')
const followUp = ref(false)
const busy = ref(false)
const polling = ref(false)
const error = ref('')
const runId = ref(sessionStorage.getItem('xin-heng-metric-run-id') || '')
const round = ref<MetricRound | null>(null)
const run = ref<MetricRun | null>(null)
const report = ref<MetricReport | null>(null)
let pendingRoundId = ''
let idempotencyKey = ''
let timer: ReturnType<typeof setInterval> | undefined

const finished = computed(() => ['completed', 'partial', 'failed', 'interrupted'].includes(run.value?.status || ''))
const findings = computed(() => {
  if (!report.value) return []
  const all = report.value.agent_results.flatMap((agent) => agent.findings)
  return report.value.rubric.metrics.map((metric) => {
    const adopted = report.value?.adopted_findings[metric.metric_id]
    const finding = adopted
      ? all.find((item) => item.finding_id === adopted)
      : all.find((item) => item.metric_id === metric.metric_id)
    const check = report.value?.checks.find((item) => item.finding_id === finding?.finding_id)
    return { metric, finding, check }
  })
})

async function refresh() {
  if (polling.value || !runId.value || !accessCode.value || props.preview) return
  polling.value = true
  try {
    const result = await metricRunsApi.status(accessCode.value, runId.value)
    if (result.id !== runId.value) throw new Error('任务编号与服务返回不一致。')
    run.value = result
    error.value = ''
    if (!round.value) round.value = await metricRunsApi.round(accessCode.value, result.round_id)
    if (['completed', 'partial'].includes(result.status) && !report.value) {
      const loaded = await metricRunsApi.report(accessCode.value, runId.value)
      if (loaded.evaluation_id !== result.id || loaded.session_id !== result.round_id)
        throw new Error('报告与当前任务不一致，已阻止展示。')
      report.value = loaded
    }
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    polling.value = false
  }
}

async function start() {
  if (busy.value || props.preview || !enabled.value || !accessCode.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    if (!pendingRoundId) {
      const seeded = await metricRunsApi.seed(accessCode.value, followUp.value)
      pendingRoundId = seeded.round_id
      idempotencyKey = crypto.randomUUID()
    }
    const loaded = await metricRunsApi.round(accessCode.value, pendingRoundId)
    if (loaded.id !== pendingRoundId) throw new Error('合成会话编号不一致。')
    round.value = loaded
    const created = await metricRunsApi.create(accessCode.value, pendingRoundId, idempotencyKey)
    runId.value = created.run_id
    sessionStorage.setItem('xin-heng-metric-run-id', created.run_id)
    run.value = null
    report.value = null
    pendingRoundId = ''
    await refresh()
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  if (props.preview) return
  try {
    enabled.value = (await metricRunsApi.capabilities()).enabled
  } catch {
    enabled.value = false
  }
  timer = setInterval(() => {
    if (runId.value && !finished.value) void refresh()
  }, 4000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="metric-runs-page">
    <section class="surface metric-intro">
      <h2>18 项指标评价 · 合成会话</h2>
      <p>从服务端生成会话、提交异步任务，并读取实际核验结果。当前规则是草稿，未发布评分锚点时不显示分数。</p>
      <p v-if="preview" class="notice">离线预览不运行指标评价。请切换到后端服务。</p>
      <p v-else-if="!enabled" class="notice">此服务尚未启用指标评价接口。需在服务端配置访问码、数据库和 worker。</p>
      <div v-else class="metric-controls">
        <label>
          <span>指标评价访问码</span>
          <input v-model="accessCode" type="password" autocomplete="off" placeholder="输入服务端配置的访问码" />
        </label>
        <label class="metric-check"><input v-model="followUp" type="checkbox" />使用合成复诊轮次</label>
        <button class="button primary" :disabled="busy || !accessCode.trim()" @click="start">
          {{ busy ? '正在提交…' : '开始新评价' }}
        </button>
      </div>
      <p class="metric-note">访问码仅保留在当前页面内存中。任务编号保留在本标签页，刷新后输入访问码即可查询。</p>
    </section>

    <section v-if="runId && enabled && !preview" class="surface metric-task">
      <div class="metric-row">
        <div><h2>评价任务</h2><p class="metric-id">{{ runId }}</p></div>
        <button class="button secondary" :disabled="polling || !accessCode.trim()" @click="refresh">{{ polling ? '查询中…' : '查询进度' }}</button>
      </div>
      <p>状态：<strong>{{ run?.status || '等待查询' }}</strong> · 轮次：{{ run?.round_id || round?.id || '等待查询' }}</p>
      <p v-if="run?.status === 'queued'">任务已入队，等待 worker 领取。</p>
      <p v-if="run?.status === 'running'">模型评价进行中，页面会定时查询。关闭页面不会取消任务。</p>
      <p v-if="run?.status === 'failed' || run?.status === 'interrupted'" class="notice danger">任务未完成。请检查 worker 日志；不会自动重复模型调用。</p>
      <ol v-if="run?.events.length" class="metric-events">
        <li v-for="event in run.events" :key="event.seq">{{ event.stage }} · {{ event.created_at }}</li>
      </ol>
    </section>

    <p v-if="error" class="notice danger" role="alert">{{ error }}</p>

    <section v-if="report" class="surface metric-report">
      <h2>指标报告</h2>
      <p>{{ report.summary }}</p>
      <p>规则版本：{{ report.rubric.version }} · 状态：{{ report.status }} · 待人工核查：{{ report.unresolved_metrics.length }} 项</p>
      <p v-if="report.overall_score === null" class="notice">总分尚不可用；草稿指标没有正式评分锚点。</p>
      <p v-if="report.limitations.length">限制：{{ report.limitations.join('、') }}</p>
      <div class="metric-findings">
        <article v-for="row in findings" :key="row.metric.metric_id" class="metric-finding">
          <div class="metric-row"><h3>{{ row.metric.metric_id }} {{ row.metric.name }}</h3><strong>{{ row.finding?.score ?? '—' }}</strong></div>
          <p>规则：{{ row.metric.scoring_status }} · 核验：{{ row.check?.status || '未返回' }}</p>
          <p v-if="row.finding">{{ row.finding.rationale }}</p>
          <p v-else>此指标未返回评价结论。</p>
          <blockquote v-for="(evidence, index) in row.finding?.evidence || []" :key="index">
            “{{ evidence.quote }}” <small>消息 {{ evidence.message_ids.join('、') }}</small>
          </blockquote>
        </article>
      </div>
    </section>

    <section v-if="round" class="surface metric-transcript">
      <h2>本次合成会话原文</h2>
      <p v-for="message in round.data.messages" :key="message.message_id">
        <strong>{{ message.message_id }} · {{ message.role === 'doctor' ? '医生' : message.role === 'patient' ? '患者' : message.role }}</strong>
        {{ message.content }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.metric-runs-page { display: grid; gap: 20px; }
.metric-runs-page .surface { padding: 26px; }
.metric-runs-page h2 { margin-bottom: 10px; font-size: 20px; }
.metric-runs-page p { margin: 8px 0; line-height: 1.65; }
.metric-controls { display: flex; align-items: end; gap: 16px; flex-wrap: wrap; margin-top: 20px; }
.metric-controls label:first-child { display: grid; gap: 8px; min-width: min(100%, 300px); }
.metric-controls input[type=password] { border: 1px solid var(--line); border-radius: 8px; padding: 11px; width: 100%; }
.metric-check { display: flex; align-items: center; gap: 6px; padding-bottom: 11px; }
.metric-note, .metric-id { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.metric-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.metric-events { max-height: 180px; overflow: auto; color: var(--muted); font-size: 13px; }
.metric-findings { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 14px; margin-top: 20px; }
.metric-finding { border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
.metric-finding h3 { font-size: 16px; }
.metric-finding blockquote { margin: 10px 0 0; padding: 10px; border-left: 3px solid var(--teal); background: var(--teal-light); }
.metric-finding small { display: block; color: var(--muted); }
.metric-transcript p { padding: 8px 0; border-bottom: 1px solid var(--line); }
</style>

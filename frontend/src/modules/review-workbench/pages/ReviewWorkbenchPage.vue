<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowLeft, CheckCircle2, CircleAlert, History, Link2, ShieldCheck } from 'lucide-vue-next'
import { metricCatalog } from '../../../api/demoData'
import { dataMode, service } from '../../../api/service'
import StatusBadge from '../../../components/base/StatusBadge.vue'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { EvaluationRun, ReviewCase, ReviewDecision } from '../../../types/domain'
import { caseTone, metricTone, shortDate } from '../../../utils/display'

const route = useRoute()
const review = ref<ReviewCase | null>(null)
const run = ref<EvaluationRun | null>(null)
const loading = ref(true)
const error = ref('')
const activeMessage = ref('')
const decision = ref<ReviewDecision | ''>('')
const reason = ref('')
const confirmAudit = ref(false)
const busy = ref(false)
const feedback = ref('')
const decisions: ReviewDecision[] = ['确认', '驳回', '修正', '无法判断', '升级处理']
const findings = computed(() => run.value?.results.filter((item) => item.state === '需复核' || item.state === '证据不足') ?? [])
const riskFindings = computed(() => run.value?.results.filter((item) => item.metricId.startsWith('D6.')) ?? [])
const canSubmit = computed(() => !!decision.value && reason.value.trim().length >= 6 && confirmAudit.value && !busy.value)

async function locate(messageId: string) {
  activeMessage.value = messageId
  await nextTick()
  document.getElementById(`review-message-${messageId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function submit() {
  if (!canSubmit.value || !review.value || !decision.value) return
  busy.value = true
  feedback.value = ''
  try {
    review.value = await service.decideCase(review.value.id, decision.value, reason.value)
    feedback.value = dataMode === 'demo' ? '演示复核已记录；本次浏览器会话刷新后会恢复初始样例。' : '复核决定已提交。'
  } catch (cause) {
    feedback.value = cause instanceof Error ? cause.message : '提交失败。'
  } finally { busy.value = false }
}

onMounted(async () => {
  try {
    review.value = await service.reviewCase(String(route.params.id))
    run.value = await service.run(review.value.runId)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '复核资料加载失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page-stack">
    <RouterLink to="/risk-center" class="back-link"><ArrowLeft :size="16" />返回风险中心</RouterLink>
    <div v-if="loading" class="loading-state">正在加载复核资料…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div>
    <template v-else-if="review && run">
      <div class="page-heading page-heading--with-action"><div><span class="eyebrow">REVIEW CASE · {{ review.id }}</span><h1>人工复核工作台</h1><p>{{ review.title }} · 关联任务 {{ run.id }}</p></div><StatusBadge :label="review.state" :tone="caseTone(review.state)" /></div>
      <div class="notice notice--amber"><CircleAlert :size="19" /><div><strong>请以原始对话和完整语境作出判断</strong><span>以下为合成案例中的待核查线索。历史背景与本次证据分开显示；未复核的模型结论不构成自动处置依据。</span></div></div>
      <div class="review-grid">
        <div class="review-grid__left"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">CURRENT SESSION · {{ run.sessionId }}</span><h2>本次咨询时间线</h2></div><span class="muted-small">{{ run.round }} · {{ run.messages.length }} 条消息</span></div><EmptyState v-if="!run.messages.length" title="本次咨询原文不可用" description="请先核实数据来源，避免作出确定性判断。" /><div v-else class="timeline timeline--review"><div v-for="message in run.messages" :id="`review-message-${message.id}`" :key="message.id" class="timeline-item" :class="{ 'timeline-item--doctor': message.role === '医生', 'timeline-item--active': activeMessage === message.id }"><div class="timeline-item__meta"><b>{{ message.role }}</b><span>{{ message.id }} · {{ shortDate(message.at) }}</span></div><p>{{ message.content }}</p></div></div></section><section v-if="run.history.length" class="panel history-panel"><div class="panel-heading"><div><span class="eyebrow">HISTORY · CONTEXT ONLY</span><h2>相关历史背景</h2></div><History :size="19" /></div><div v-for="item in run.history" :key="item.sessionId" class="history-item"><strong>{{ item.date }} · {{ item.sessionId }}</strong><p>{{ item.content }}</p></div><div class="history-panel__note"><ShieldCheck :size="15" />不能将历史片段作为本次医生行为的直接证据</div></section></div>
        <div class="review-grid__right"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">REVIEW CONTEXT</span><h2>待核查线索</h2></div></div><div class="info-pairs"><div><span>优先级</span><StatusBadge :label="`${review.priority}优先级`" :tone="review.priority === '高' ? 'red' : 'amber'" /></div><div><span>证据状态</span><strong>{{ review.evidenceState }}</strong></div><div><span>规则版本</span><strong>{{ run.rubricVersion }}</strong></div></div><div class="hook-note"><strong>风险 Hook 候选</strong><p>{{ review.hookHint }}</p><small>候选线索不决定 D6 是否执行，也不直接给分。</small></div></section>
          <section class="panel"><div class="panel-heading"><div><span class="eyebrow">AGENT FINDINGS</span><h2>指标判断与证据</h2></div></div><div v-if="riskFindings.length" class="risk-findings"><div v-for="item in riskFindings" :key="item.metricId"><div><strong>{{ item.metricId }} {{ metricCatalog.find((metric) => metric.id === item.metricId)?.name }}</strong><StatusBadge :label="item.state" :tone="metricTone(item.state)" /></div><p>{{ item.reason }}</p></div></div><div v-for="item in findings.filter((entry) => !entry.metricId.startsWith('D6.'))" :key="item.metricId" class="review-finding"><div><strong>{{ item.metricId }} {{ metricCatalog.find((metric) => metric.id === item.metricId)?.name }}</strong><StatusBadge :label="item.state" :tone="metricTone(item.state)" /></div><p>{{ item.reason }}</p><button v-for="evidence in item.evidence" :key="evidence.messageId" class="evidence-link" @click="locate(evidence.messageId)"><Link2 :size="14" />定位原文 {{ evidence.messageId }}</button></div><div v-for="item in riskFindings" :key="`risk-evidence-${item.metricId}`" class="review-evidence"><button v-for="evidence in item.evidence" :key="evidence.messageId" class="evidence-link" @click="locate(evidence.messageId)"><Link2 :size="14" />{{ item.metricId }} 原文 {{ evidence.messageId }}</button></div></section>
          <section class="panel decision-panel"><div class="panel-heading"><div><span class="eyebrow">HUMAN DECISION</span><h2>提交复核决定</h2></div></div><div v-if="review.state === '已处理'" class="decision-done"><CheckCircle2 :size="22" /><div><strong>已记录人工决定：{{ review.decision }}</strong><p>{{ review.decisionReason }}</p></div></div><template v-else><label class="form-label">复核决定<select v-model="decision"><option value="">请选择处理结果</option><option v-for="item in decisions" :key="item">{{ item }}</option></select></label><label class="form-label">决定理由<textarea v-model="reason" rows="4" maxlength="500" placeholder="请结合原文和指标规则说明理由（至少 6 个字）" /></label><label class="check-line"><input v-model="confirmAudit" type="checkbox" /><span>我已核对本次咨询证据，并了解提交后将保留操作记录。</span></label><p v-if="feedback" :class="feedback.startsWith('演示') ? 'form-success' : 'form-error'" role="status">{{ feedback }}</p><button class="button button--primary button--wide" :disabled="!canSubmit" @click="submit">{{ busy ? '正在提交…' : '提交复核决定' }}</button></template></section>
        </div>
      </div>
    </template>
  </div>
</template>

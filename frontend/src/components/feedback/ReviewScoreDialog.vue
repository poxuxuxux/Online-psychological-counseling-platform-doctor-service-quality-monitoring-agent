<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Icon from '../base/Icon.vue'
import { dimensions } from '../../utils/catalog'

export type ReviewScoreMetric = { code: string; name: string; score: number | null }
export type ReviewScoreSubmission = {
  decision: 'keep' | 'adjust'
  scores: Record<string, number>
  totalScore: number
  note: string
}

const props = defineProps<{
  title: string
  metrics: ReviewScoreMetric[]
  overallScore: number | null
  offline?: boolean
}>()
const emit = defineEmits<{
  close: []
  submit: [value: ReviewScoreSubmission]
}>()

const decision = ref<'keep' | 'adjust'>('keep')
const changedScores = ref<Record<string, string>>({})
const totalScore = ref(props.overallScore === null ? '' : props.overallScore.toFixed(1))
const note = ref('')
const error = ref('')
const closeButton = ref<HTMLButtonElement | null>(null)
let previousBodyOverflow = ''
let previousDocumentOverflow = ''
const groupedMetrics = computed(() => dimensions.map((dimension) => ({
  ...dimension,
  metrics: props.metrics.filter((metric) => metric.code.startsWith(`${dimension.id}.`)),
})).filter((group) => group.metrics.length))

watch(decision, (value) => {
  if (value === 'keep' && props.overallScore !== null)
    totalScore.value = props.overallScore.toFixed(1)
})

onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  previousDocumentOverflow = document.documentElement.style.overflow
  document.body.style.overflow = 'hidden'
  document.documentElement.style.overflow = 'hidden'
  closeButton.value?.focus()
})

onUnmounted(() => {
  document.body.style.overflow = previousBodyOverflow
  document.documentElement.style.overflow = previousDocumentOverflow
})

function submit() {
  const score = Number(totalScore.value)
  if (totalScore.value === '' || !Number.isFinite(score) || score < 0 || score > 100) {
    error.value = '请填写 0 到 100 之间的复核总分。'
    return
  }
  if (note.value.trim().length < 10) {
    error.value = '复核意见至少需要 10 个字。'
    return
  }
  const scores: Record<string, number> = {}
  if (decision.value === 'adjust') {
    for (const metric of props.metrics) {
      const value = String(changedScores.value[metric.code] ?? '').trim()
      if (!value) continue
      const parsed = Number(value)
      if (!Number.isFinite(parsed) || parsed < 0 || parsed > 5) {
        error.value = `${metric.code} 的修改分值须在 0 到 5 之间。`
        return
      }
      scores[metric.code] = parsed
    }
  }
  error.value = ''
  emit('submit', { decision: decision.value, scores, totalScore: score, note: note.value.trim() })
}

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const dialog = (event.currentTarget as HTMLElement).querySelector<HTMLElement>('.review-score-dialog')
  const focusable = [...(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])]
  if (!focusable.length) return
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="review-score-overlay" role="presentation" tabindex="-1" @click.self="emit('close')" @keydown.esc.stop.prevent="emit('close')" @keydown="trapFocus">
      <section class="review-score-dialog" role="dialog" aria-modal="true" aria-labelledby="review-score-title">
        <header class="review-score-header">
          <div><h2 id="review-score-title">人工复核</h2><p>{{ title }} · 核对 18 项评价指标的 AI 原始分数，并记录复核结果。</p></div>
          <button ref="closeButton" class="review-dialog-close" type="button" aria-label="关闭人工复核" @click="emit('close')"><Icon name="close" :size="18" /></button>
        </header>
        <form class="review-score-form" @submit.prevent="submit">
          <div class="review-decision-options" role="radiogroup" aria-label="复核决定">
            <label :class="{ selected: decision === 'keep' }"><input v-model="decision" type="radio" value="keep" /><span><strong>维持原判</strong><small>保留 AI 原有指标分数</small></span></label>
            <label :class="{ selected: decision === 'adjust' }"><input v-model="decision" type="radio" value="adjust" /><span><strong>修改评分</strong><small>填写需要调整的指标分值</small></span></label>
          </div>

          <div class="review-score-list" aria-label="18 项指标分数">
            <section v-for="group in groupedMetrics" :key="group.id" class="review-score-group">
              <h3><span>{{ group.id }}</span>{{ group.name }}<small>{{ group.metrics.length }} 项</small></h3>
              <div class="review-score-rows">
                <div v-for="metric in group.metrics" :key="metric.code" class="review-score-row">
                  <div class="review-score-metric"><span>{{ metric.code }}</span><strong>{{ metric.name }}</strong></div>
                  <div class="review-score-original"><small>AI 原分</small><b>{{ metric.score === null ? '未评分' : metric.score.toFixed(1) }}</b></div>
                  <label class="review-score-input"><span class="visually-hidden">{{ metric.code }}填写修改分值</span><input v-model="changedScores[metric.code]" type="number" min="0" max="5" step="0.1" :disabled="decision !== 'adjust'" :placeholder="decision === 'adjust' ? '填写修改分值' : '维持原分'" /></label>
                </div>
              </div>
            </section>
          </div>

          <div class="review-score-bottom">
            <label class="review-total-score">复核总分（0–100）<input v-model="totalScore" type="number" min="0" max="100" step="0.1" inputmode="decimal" :disabled="decision === 'keep' && overallScore !== null" placeholder="填写总分" required /></label>
            <label class="review-dialog-note">复核意见<textarea v-model="note" rows="3" minlength="10" maxlength="500" placeholder="说明维持或调整的依据（至少 10 个字）" required></textarea><small>{{ note.length }}/500</small></label>
          </div>
          <p v-if="offline" class="review-dialog-storage"><Icon name="info" :size="14" />离线演示：复核结果仅保存在当前页面。</p>
          <p v-if="error" class="review-dialog-error" role="alert">{{ error }}</p>
          <footer class="review-dialog-actions"><button class="review-action secondary" type="button" @click="emit('close')">取消</button><button class="review-action primary" type="submit"><Icon name="check" :size="15" />提交复核结果</button></footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.review-score-overlay { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; padding: 24px; background: rgba(17, 38, 28, .48); backdrop-filter: blur(5px); }
.review-score-dialog { width: min(1040px, 100%); max-height: min(92dvh, 1060px); overflow-y: auto; overscroll-behavior: contain; border: 1px solid #dce9df; border-radius: 20px; background: #fff; color: #19372b; box-shadow: 0 28px 80px -32px rgba(12, 43, 27, .5); }
.review-score-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 24px 28px 18px; border-bottom: 1px solid #e7eee9; }
.review-score-header h2 { margin: 5px 0 0; font-size: 25px; line-height: 1.35; }
.review-score-header p { margin: 6px 0 0; color: #718176; font-size: 14px; line-height: 1.5; }
.review-dialog-close { display: grid; flex: 0 0 auto; place-items: center; width: 38px; height: 38px; border: 1px solid #e3ebe5; border-radius: 50%; background: #f7faf8; color: #5b7063; cursor: pointer; }
.review-score-form { display: block; }
.review-decision-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 18px 28px 14px; }
.review-decision-options label { display: flex; align-items: center; gap: 12px; min-height: 64px; padding: 12px 15px; border: 1px solid #dfe9e3; border-radius: 12px; background: #fbfdfb; cursor: pointer; }
.review-decision-options label.selected { border-color: #61a985; background: #f0f8f3; box-shadow: 0 0 0 2px rgba(35, 139, 94, .08); }
.review-decision-options input { width: 17px; height: 17px; accent-color: #16815a; }
.review-decision-options span { display: grid; gap: 3px; }
.review-decision-options strong { font-size: 15px; }
.review-decision-options small { color: #75867a; font-size: 12.5px; }
.review-score-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; gap: 12px; padding: 4px 28px 16px; }
.review-score-group { min-width: 0; padding: 11px; border: 1px solid #e4ece6; border-radius: 12px; background: #fcfdfc; }
.review-score-group h3 { display: flex; align-items: center; gap: 7px; margin: 0 0 7px; color: #385544; font-size: 14px; }
.review-score-group h3 > span { color: #158159; font-size: 12px; }
.review-score-group h3 small { margin-left: auto; color: #829087; font-size: 11px; font-weight: 500; }
.review-score-rows { display: grid; gap: 4px; }
.review-score-row { display: grid; grid-template-columns: minmax(0, 1fr) 66px minmax(118px, .75fr); align-items: center; gap: 8px; min-height: 42px; padding: 5px 7px; border-radius: 8px; background: #f5f9f6; }
.review-score-metric { display: grid; grid-template-columns: 35px minmax(0, 1fr); align-items: center; gap: 6px; min-width: 0; }
.review-score-metric > span { color: #7b8d81; font-size: 11px; font-variant-numeric: tabular-nums; }
.review-score-metric > strong { overflow: hidden; color: #405849; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.review-score-original { display: grid; justify-items: center; gap: 1px; }
.review-score-original small { color: #849087; font-size: 10px; }
.review-score-original b { color: #1b7d57; font-size: 14px; font-variant-numeric: tabular-nums; }
.review-score-input input, .review-total-score input { width: 100%; min-height: 34px; padding: 6px 8px; border: 1px solid #dce7df; border-radius: 7px; outline: none; background: white; color: #274435; font: inherit; font-size: 12px; }
.review-score-input input:focus, .review-total-score input:focus, .review-dialog-note textarea:focus { border-color: #62a987; box-shadow: 0 0 0 3px rgba(44, 142, 98, .1); }
.review-score-input input:disabled { background: #eef3ef; color: #87948b; cursor: not-allowed; }
.review-total-score input:disabled { background: #eef3ef; color: #63766a; cursor: not-allowed; }
.review-score-input input::placeholder { color: #8c9990; }
.review-score-bottom { display: grid; grid-template-columns: minmax(180px, .38fr) minmax(0, 1fr); gap: 16px; padding: 0 28px 14px; }
.review-total-score, .review-dialog-note { display: grid; align-content: start; gap: 7px; color: #41594a; font-size: 13px; font-weight: 650; }
.review-total-score input { min-height: 42px; font-size: 16px; }
.review-dialog-note { position: relative; }
.review-dialog-note textarea { min-height: 72px; padding: 9px 11px; border: 1px solid #dce7df; border-radius: 8px; outline: none; color: #344d3d; font: inherit; font-size: 13px; font-weight: 400; line-height: 1.6; resize: vertical; }
.review-dialog-note > small { justify-self: end; margin-top: -5px; color: #829087; font-size: 11px; font-weight: 400; }
.review-dialog-storage, .review-dialog-error { display: flex; align-items: center; gap: 6px; margin: 0 28px 10px; color: #708276; font-size: 12px; }
.review-dialog-error { color: #a43f48; }
.review-dialog-actions { display: flex; justify-content: flex-end; gap: 10px; padding: 13px 28px 20px; border-top: 1px solid #e8efea; background: #fff; }
.review-dialog-actions .review-action { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 112px; min-height: 42px; padding: 8px 14px; border: 1px solid #dfe9e2; border-radius: 9px; font-size: 14px; font-weight: 700; cursor: pointer; }
.review-dialog-actions .review-action.secondary { background: #fff; color: #405849; }
.review-dialog-actions .review-action.primary { border-color: #16815a; background: #16815a; color: #fff; }
.review-dialog-actions .review-action.primary:hover { border-color: #0d6747; background: #0d6747; }
.review-score-dialog button:focus-visible, .review-score-dialog input:focus-visible, .review-score-dialog textarea:focus-visible { outline: 3px solid rgba(39, 145, 98, .25); outline-offset: 2px; }
.review-score-dialog .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.review-score-dialog button, .review-score-dialog input, .review-score-dialog textarea { font-family: inherit; }
@media (max-width: 720px) {
  .review-score-overlay { align-items: end; padding: 0; }
  .review-score-dialog { width: 100%; max-height: 94dvh; border-radius: 18px 18px 0 0; }
  .review-score-header { padding: 18px 18px 14px; }
  .review-score-header h2 { font-size: 21px; }
  .review-decision-options { padding: 14px 18px 10px; }
  .review-decision-options label { min-height: 58px; padding: 9px; }
  .review-decision-options small { font-size: 11px; }
  .review-score-list { grid-template-columns: minmax(0, 1fr); padding: 4px 18px 12px; }
  .review-score-bottom { grid-template-columns: minmax(0, 1fr); gap: 11px; padding: 0 18px 12px; }
  .review-dialog-storage, .review-dialog-error { margin-inline: 18px; }
  .review-dialog-actions { padding: 12px 18px 18px; }
}
@media (prefers-reduced-motion: no-preference) {
  .review-score-dialog { animation: review-dialog-in 160ms ease-out; }
  @keyframes review-dialog-in { from { opacity: 0; transform: translateY(8px) scale(.99); } to { opacity: 1; transform: translateY(0) scale(1); } }
}
</style>

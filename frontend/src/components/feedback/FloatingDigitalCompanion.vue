<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Report } from '../../api/contracts/evaluation'
import { createQualityReports } from '../../data/reportsPreview'
import DigitalReportPresenter from './DigitalReportPresenter.vue'
import Icon from '../base/Icon.vue'
import stillImage from '../../assets/digital-human/xiaojian-still.png'
import waveImage from '../../assets/digital-human/xiaojian-wave.webp'

const props = defineProps<{ report: Report | null; preview: boolean }>()
const expanded = ref(false)
const minimized = ref(false)
const playing = ref(false)
const x = ref(0), y = ref(0)
const viewport = ref({ width: 1024, height: 768 })
const storageKey = 'xin-jian-companion-position-v1'
const petSize = computed(() => minimized.value ? { width: 64, height: 64 } : { width: 132, height: 208 })
const demoReport = createQualityReports().find(report => report.status === 'completed')!
const demoText = computed(() => props.preview
  ? [demoReport.title, demoReport.summary, '改进建议。' + demoReport.improvement].join('\n\n') : undefined)
const greeting = computed(() => playing.value ? '我正在为你讲解…'
  : props.preview ? '你好呀，我是小鉴。\n一起听听示例报告？'
    : props.report?.status === 'failed' ? '评价遇到问题了，\n我们一起看看原因。'
      : props.report ? '报告准备好了，\n要我讲给你听吗？' : '我在这里。\n有报告时，点我听讲解。')
const panelStyle = computed(() => {
  const width = Math.max(1, Math.min(380, viewport.value.width - 24))
  const above = y.value - 24
  const below = viewport.value.height - y.value - petSize.value.height - 24
  const useAbove = above >= below
  const height = Math.max(1, Math.min(500, useAbove ? above : below))
  return {
    width: width + 'px',
    left: Math.max(12, Math.min(x.value + petSize.value.width - width, viewport.value.width - width - 12)) + 'px',
    top: (useAbove ? Math.max(12, y.value - height - 12) : y.value + petSize.value.height + 12) + 'px',
    maxHeight: height + 'px',
  }
})
let drag: { pointer: number; startX: number; startY: number; x: number; y: number; moved: boolean } | null = null
let suppressClick = false

function clamp() {
  x.value = Math.max(8, Math.min(x.value, viewport.value.width - petSize.value.width - 8))
  y.value = Math.max(8, Math.min(y.value, viewport.value.height - petSize.value.height - 8))
}
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({ x: x.value, y: y.value, minimized: minimized.value })) }
  catch { /* Dragging remains available when browser storage is disabled. */ }
}
function resize() {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  clamp()
}
function close() {
  expanded.value = false
  playing.value = false
}
function toggle() {
  if (expanded.value) close()
  else expanded.value = true
}
async function minimize() {
  close()
  minimized.value = !minimized.value
  await nextTick()
  clamp()
  save()
}
function pointerDown(event: PointerEvent) {
  if (event.button !== 0 || drag) return
  drag = { pointer: event.pointerId, startX: event.clientX, startY: event.clientY, x: x.value, y: y.value, moved: false }
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!drag || drag.pointer !== event.pointerId) return
  const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY
  if (Math.hypot(dx, dy) > 5) drag.moved = true
  if (!drag.moved) return
  x.value = drag.x + dx
  y.value = drag.y + dy
  clamp()
}
function pointerUp(event: PointerEvent) {
  if (!drag || drag.pointer !== event.pointerId) return
  const moved = drag.moved
  drag = null
  suppressClick = moved
  if (moved) save()
}
function avatarClick() {
  if (suppressClick) {
    suppressClick = false
    return
  }
  toggle()
}
function escape(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}
watch(() => [props.report, props.preview], () => { playing.value = false })
onMounted(() => {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  minimized.value = window.innerWidth < 600
  x.value = window.innerWidth - petSize.value.width - 28
  y.value = window.innerHeight - petSize.value.height - 24
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || 'null')
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      x.value = saved.x
      y.value = saved.y
      minimized.value = saved.minimized === true
    }
  } catch { /* Start at the default corner if saved coordinates cannot be read. */ }
  clamp()
  window.addEventListener('resize', resize)
  window.addEventListener('keydown', escape)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  window.removeEventListener('keydown', escape)
})
</script>

<template>
  <div class="companion-pet" :class="{ minimized, 'panel-open': expanded }" :style="{ left: x + 'px', top: y + 'px' }">
    <button v-if="!expanded && !minimized" class="pet-greeting" type="button"
      :style="x < 210 ? { right: 'auto', left: '105px', bottom: y < 60 ? '20px' : '147px' } : { bottom: y < 60 ? '20px' : '147px' }" @click="toggle">
      <span class="greeting-dot"></span>{{ greeting }}
    </button>
    <button class="pet-size-toggle" type="button" :aria-label="minimized ? '展开小鉴形象' : '收成小头像'" @click="minimize">
      {{ minimized ? '↗' : '−' }}
    </button>
    <button class="pet-avatar" type="button" aria-label="小鉴，点击打开报告讲解，拖动调整位置" :aria-expanded="expanded"
      @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="drag = null"
      @click="avatarClick">
      <span class="pet-halo"></span>
      <picture>
        <source media="(prefers-reduced-motion: reduce)" :srcset="stillImage" />
        <img :src="playing ? waveImage : stillImage" alt="" draggable="false" />
      </picture>
      <span v-if="!minimized" class="pet-caption">小鉴 <i></i> 报告陪伴</span>
    </button>
  </div>
  <section v-if="expanded" class="companion-panel" :style="panelStyle" aria-label="小鉴报告讲解面板" @keydown.esc="close">
    <header class="companion-header">
      <span><i></i> 小鉴 · 你的报告讲解员</span>
      <button type="button" aria-label="关闭小鉴面板" @click="close"><Icon name="close" :size="16" /></button>
    </header>
    <DigitalReportPresenter :report="preview ? null : report" :demo-text="demoText" compact @playback-change="playing = $event" />
  </section>
</template>

<style scoped>
.companion-pet { position: fixed; z-index: 90; width: 132px; height: 208px; }
.pet-avatar { display: block; width: 100%; height: 100%; padding: 0; border: 0; background: none; position: relative; cursor: grab; touch-action: none; user-select: none; }
.pet-avatar:active { cursor: grabbing; }
.pet-avatar picture { position: absolute; inset: 0 0 18px; display: block; }
.pet-avatar img { width: 100%; height: 100%; object-fit: contain; pointer-events: none; filter: drop-shadow(0 10px 10px #163c3328); }
.pet-halo { position: absolute; width: 82px; height: 20px; bottom: 23px; left: 25px; border-radius: 50%; background: #315d4730; filter: blur(7px); }
.pet-caption { position: absolute; bottom: 0; left: 6px; right: 6px; display: flex; align-items: center; justify-content: center; gap: 6px; background: #fffffff2; border: 1px solid #d9e4d8; border-radius: 20px; padding: 6px 8px; font-size: 11px; color: #315b45; box-shadow: 0 4px 18px #17362b0c; }
.pet-caption i, .greeting-dot, .companion-header i { width: 6px; height: 6px; background: #67a383; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.pet-greeting { position: absolute; right: 105px; bottom: 147px; width: 188px; padding: 13px 16px; border: 1px solid #dce7da; border-radius: 16px 16px 3px 16px; background: #fffffff7; color: #3b5f4b; box-shadow: 0 7px 25px #263e3010; font: inherit; font-size: 12px; line-height: 1.8; text-align: left; white-space: pre-line; cursor: pointer; }
.greeting-dot { margin-right: 7px; }
.pet-size-toggle { position: absolute; z-index: 1; right: 0; top: 1px; border: 1px solid #d8e3d8; border-radius: 50%; background: #fffffff2; color: #54715b; width: 25px; height: 25px; font-size: 18px; cursor: pointer; }
.minimized { width: 64px; height: 64px; }
.minimized .pet-avatar { overflow: hidden; border-radius: 50%; border: 2px solid white; background: #e9eee2; box-shadow: 0 4px 20px #183a3025; }
.minimized .pet-avatar picture { width: 110px; height: 165px; left: -25px; top: -2px; bottom: auto; }
.minimized .pet-avatar img { object-fit: cover; }
.minimized .pet-halo { display: none; }
.minimized .pet-size-toggle { top: -9px; right: -7px; }
.companion-panel { position: fixed; z-index: 91; overflow: auto; border: 1px solid #d5e3d7; border-radius: 18px; background: #fbfcf8; box-shadow: 0 16px 60px #17392d26; }
.companion-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; background: #eef4e9; border-bottom: 1px solid #dce6d8; color: #41614b; font-size: 12px; }
.companion-header span { display: flex; align-items: center; gap: 8px; }
.companion-header button { display: grid; place-items: center; width: 26px; height: 26px; border: 0; border-radius: 50%; background: transparent; color: #496b54; cursor: pointer; }
button:focus-visible { outline: 3px solid #8eb59d; outline-offset: 3px; }
@media (max-width: 600px) { .pet-greeting { display: none; } }
</style>

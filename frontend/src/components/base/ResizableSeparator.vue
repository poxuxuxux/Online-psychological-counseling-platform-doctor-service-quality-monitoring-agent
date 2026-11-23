<script setup lang="ts">
import { onUnmounted } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: number
    min?: number
    max?: number
    resetValue?: number
    label: string
  }>(),
  { min: 38, max: 78, resetValue: 62 },
)
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

let startY = 0
let startValue = 0
let splitHeight = 0
let pointerId: number | null = null
let activeElement: HTMLElement | null = null

function clamp(value: number) {
  return Math.max(props.min, Math.min(props.max, value))
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  const element = event.currentTarget as HTMLElement
  const container = element.parentElement
  if (!container) return
  event.preventDefault()
  pointerId = event.pointerId
  activeElement = element
  startY = event.clientY
  startValue = props.modelValue
  splitHeight = container.getBoundingClientRect().height
  element.setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', stopDragging)
  window.addEventListener('pointercancel', stopDragging)
}

function onPointerMove(event: PointerEvent) {
  if (pointerId !== event.pointerId || splitHeight <= 0) return
  emit('update:modelValue', clamp(startValue + ((event.clientY - startY) / splitHeight) * 100))
}

function stopDragging(event?: PointerEvent) {
  if (event && pointerId !== event.pointerId) return
  if (activeElement && pointerId !== null && activeElement.hasPointerCapture(pointerId)) {
    activeElement.releasePointerCapture(pointerId)
  }
  pointerId = null
  activeElement = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', stopDragging)
  window.removeEventListener('pointercancel', stopDragging)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
    event.preventDefault()
    emit('update:modelValue', clamp(props.modelValue + (event.key === 'ArrowDown' ? 5 : -5)))
  } else if (event.key === 'Home') {
    event.preventDefault()
    emit('update:modelValue', props.resetValue)
  } else if (event.key === 'End') {
    event.preventDefault()
    emit('update:modelValue', props.max)
  }
}

onUnmounted(() => stopDragging())
</script>

<template>
  <div
    class="resizable-separator"
    role="separator"
    aria-orientation="horizontal"
    :aria-label="label"
    :aria-valuetext="`上方占 ${Math.round(modelValue)}%，下方占 ${100 - Math.round(modelValue)}%`"
    :aria-valuemin="min"
    :aria-valuemax="max"
    :aria-valuenow="Math.round(modelValue)"
    :title="`${label}；双击恢复默认比例`"
    tabindex="0"
    @pointerdown="onPointerDown"
    @keydown="onKeydown"
    @dblclick="$emit('update:modelValue', resetValue)"
  >
    <span aria-hidden="true"></span>
  </div>
</template>

<style scoped>
.resizable-separator {
  position: relative;
  z-index: 1;
  display: grid;
  min-height: 18px;
  place-items: center;
  margin: 0 12px;
  cursor: row-resize;
  touch-action: none;
  user-select: none;
}
.resizable-separator::before {
  position: absolute;
  inset: 0 -12px;
  content: '';
}
.resizable-separator span {
  width: 48px;
  height: 4px;
  border-radius: 99px;
  background: #b9d8c9;
  transition: width 160ms ease, background-color 160ms ease;
}
.resizable-separator:hover span,
.resizable-separator:focus-visible span {
  width: 68px;
  background: #20815d;
}
.resizable-separator:focus-visible {
  outline: 2px solid #20815d;
  outline-offset: 2px;
}
</style>

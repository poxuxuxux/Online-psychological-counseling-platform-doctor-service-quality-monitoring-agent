<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Overview } from '../../api/contracts/overview'
const props = withDefaults(
  defineProps<{
    trend: Overview['trend']
    scale?: 'percent' | 'five'
    monthly?: boolean
    initialFocus?: number
  }>(),
  { scale: 'percent', monthly: false, initialFocus: undefined },
)
const active = ref<number | null>(props.monthly ? (props.initialFocus ?? null) : null)
const x = (i: number) =>
  props.trend.length === 1 ? 370 : 48 + (i * 640) / (props.trend.length - 1)
const y = (score: number) =>
  props.scale === 'five' ? 283 - score * 2.45 : 234 - score * 1.96
const tickValues = computed(() =>
  props.scale === 'five' ? [20, 40, 60, 80, 100] : [0, 20, 40, 60, 80, 100],
)
const displayScore = (score: number) => (props.scale === 'five' ? score / 20 : score)
// Gaps remain gaps: connecting a missing day would imply an unobserved trend.
const segments = computed(() => {
  const result: number[][] = []
  let segment: number[] = []
  props.trend.forEach((p, i) => {
    if (p.average === null) {
      if (segment.length) result.push(segment)
      segment = []
    } else segment.push(i)
  })
  if (segment.length) result.push(segment)
  return result
})
// Catmull-Rom smoothing keeps the curve inside the observed points.
const smooth = (indexes: number[]) => {
  const points = indexes.map((i) => [x(i), y(props.trend[i]!.average!)] as [number, number])
  if (points.length === 1) {
    const [px, py] = points[0]!
    return `M${px} ${py}l0.01 0`
  }
  let d = `M${points[0]![0]} ${points[0]![1]}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]!
    const p1 = points[i]!
    const p2 = points[i + 1]!
    const p3 = points[i + 2] ?? p2
    const t = 0.2
    d += ` C${p1[0] + (p2[0] - p0[0]) * t} ${p1[1] + (p2[1] - p0[1]) * t} ${
      p2[0] - (p3[0] - p1[0]) * t
    } ${p2[1] - (p3[1] - p1[1]) * t} ${p2[0]} ${p2[1]}`
  }
  return d
}
const lines = computed(() => segments.value.map(smooth))
const areas = computed(() =>
  segments.value.map((indexes) => {
    const first = x(indexes[0]!)
    const last = x(indexes[indexes.length - 1]!)
    return `${smooth(indexes)} L${last} 234 L${first} 234 Z`
  }),
)
const ticks = computed(() =>
  props.monthly
    ? props.trend.map((_, i) => i).filter((i) => i % 2 === 0 || i === props.trend.length - 1)
    : [...new Set([0, Math.floor((props.trend.length - 1) / 2), props.trend.length - 1])],
)
const tickLabel = (i: number) =>
  props.monthly ? `${Math.floor((i + 1) / 2) + 1}月` : (props.trend[i]?.date.slice(5) ?? '')
const selected = computed(() => (active.value === null ? null : props.trend[active.value]))
const lastScored = computed(() => {
  for (let i = props.trend.length - 1; i >= 0; i--) if (props.trend[i]!.average !== null) return i
  return -1
})
const focusIndex = computed(() => active.value ?? lastScored.value)
const focusPoint = computed(() => {
  const item = props.trend[focusIndex.value]
  if (!item || item.average === null) return null
  const px = x(focusIndex.value)
  const py = y(item.average)
  // 靠近顶部时把气泡放到点下方，避免贴边被裁切。
  const above = props.monthly || py > 78
  return {
    px,
    py,
    item,
    above,
    bubbleX: Math.min(660, Math.max(50, px)),
    bubbleY: above ? py - 62 : py + 20,
  }
})
const fillId = `trend-fill-${Math.random().toString(36).slice(2, 8)}`
</script>
<template>
  <div class="trend-area">
    <svg
      class="trend-chart"
      viewBox="0 0 720 280"
      role="img"
      aria-label="每日平均总分折线图，满分100分，85分优质线与60分风险边界线，空白日期没有有效评分"
    >
      <defs>
        <linearGradient :id="fillId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3f9f78" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#3f9f78" stop-opacity="0" />
        </linearGradient>
      </defs>
      <g v-for="v in tickValues" :key="v">
        <line x1="48" x2="688" :y1="y(v)" :y2="y(v)" class="chart-grid" />
        <text x="34" :y="y(v) + 4" text-anchor="end" class="chart-tick">
          {{ scale === 'five' ? (v / 20).toFixed(1) : v }}
        </text>
      </g>
      <line
        v-for="i in ticks"
        :key="`grid-${i}`"
        :x1="x(i)"
        :x2="x(i)"
        y1="38"
        y2="234"
        class="chart-grid chart-grid-v"
      />
      <template v-if="scale === 'percent'">
        <line x1="48" x2="688" :y1="y(85)" :y2="y(85)" class="threshold quality" />
        <line x1="48" x2="688" :y1="y(60)" :y2="y(60)" class="threshold risk" />
      </template>
      <path v-for="(area, i) in areas" :key="`area-${i}`" :d="area" :fill="`url(#${fillId})`" />
      <path v-for="(line, i) in lines" :key="i" :d="line" class="trend-line" />
      <template v-if="focusPoint">
        <line
          :x1="focusPoint.px"
          :x2="focusPoint.px"
          :y1="focusPoint.py + 8"
          y2="234"
          class="trend-guide"
        />
        <circle
          :cx="focusPoint.px"
          :cy="focusPoint.py"
          r="9"
          class="chart-point-halo"
        />
        <g class="trend-bubble" :transform="`translate(${focusPoint.bubbleX}, ${focusPoint.bubbleY})`">
          <rect x="-43" y="0" width="86" height="46" rx="13" />
          <path v-if="focusPoint.above" d="M-7 45.5h14L0 56Z" class="trend-bubble-tip" />
          <path v-else d="M-7 0.5h14L0 -10Z" class="trend-bubble-tip" />
          <text x="-29" y="20" class="trend-bubble-date">
            {{ monthly ? `${Math.floor((focusIndex + 1) / 2) + 1}月` : focusPoint.item.date.slice(5) }}
          </text>
          <text x="-29" y="38" class="trend-bubble-score">
            {{ displayScore(focusPoint.item.average!).toFixed(1) }}
          </text>
        </g>
      </template>
      <template v-for="(p, i) in trend" :key="p.date">
        <circle
          v-if="p.average !== null"
          :cx="x(i)"
          :cy="y(p.average)"
          r="4"
          class="chart-point"
          tabindex="0"
          :aria-label="`${p.date}，${p.average.toFixed(1)} 分，${p.sample_count} 轮`"
          @focus="active = i"
          @blur="active = null"
          @mouseenter="active = i"
          @mouseleave="active = null"
        >
          <title>{{ p.date }}：{{ p.average.toFixed(1) }} 分，{{ p.sample_count }} 轮</title>
        </circle>
      </template>
      <text v-for="i in ticks" :key="i" :x="x(i)" y="260" text-anchor="middle" class="chart-label">
        {{ tickLabel(i) }}
      </text>
    </svg>
    <div class="chart-legend">
      <span><i class="legend-line" />平均总分</span
      ><span><i class="legend-line quality" />85 分优质线</span
      ><span><i class="legend-line risk" />60 分风险边界</span>
    </div>
    <p class="chart-caption" aria-live="polite">
      {{
        selected
          ? `${selected.date} · ${selected.average?.toFixed(1)} 分 · ${selected.sample_count} 轮`
          : '按评估保存日期统计；无有效评分的日期留空。'
      }}
    </p>
  </div>
</template>

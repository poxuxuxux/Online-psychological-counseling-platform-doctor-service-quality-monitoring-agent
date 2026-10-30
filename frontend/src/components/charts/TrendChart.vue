<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Overview } from '../../api/contracts/overview'
const props = defineProps<{ trend: Overview['trend'] }>()
const active = ref<number | null>(null)
const x = (i: number) =>
  props.trend.length === 1 ? 370 : 48 + (i * 640) / (props.trend.length - 1)
const y = (score: number) => 234 - score * 1.96
// Gaps remain gaps: connecting a missing day would imply an unobserved trend.
const segments = computed(() => {
  const result: string[] = []
  let segment: string[] = []
  props.trend.forEach((p, i) => {
    if (p.average === null) {
      if (segment.length) result.push(segment.join(' '))
      segment = []
    } else segment.push(`${x(i)},${y(p.average)}`)
  })
  if (segment.length) result.push(segment.join(' '))
  return result
})
const fills = computed(() =>
  segments.value.map((segment) => {
    const points = segment.split(' ')
    return `${points.join(' ')} ${points[points.length - 1]!.split(',')[0]},234 ${points[0]!.split(',')[0]},234`
  }),
)
const ticks = computed(() => [
  ...new Set([0, Math.floor((props.trend.length - 1) / 2), props.trend.length - 1]),
])
const selected = computed(() => (active.value === null ? null : props.trend[active.value]))
</script>
<template>
  <div class="trend-area">
    <svg
      class="trend-chart"
      viewBox="0 0 720 280"
      role="img"
      aria-label="每日平均总分折线图，满分100分，85分优质线与60分风险边界线，空白日期没有有效评分"
    >
      <g v-for="v in [0, 20, 40, 60, 80, 100]" :key="v">
        <line x1="48" x2="688" :y1="y(v)" :y2="y(v)" class="chart-grid" />
        <text x="34" :y="y(v) + 4" text-anchor="end" class="chart-tick">{{ v }}</text>
      </g>
      <line x1="48" x2="688" :y1="y(85)" :y2="y(85)" class="threshold quality" />
      <line x1="48" x2="688" :y1="y(60)" :y2="y(60)" class="threshold risk" />
      <polygon v-for="(fill, i) in fills" :key="`fill-${i}`" :points="fill" fill="#087f730c" />
      <polyline v-for="(segment, i) in segments" :key="i" :points="segment" class="trend-line" />
      <template v-for="(p, i) in trend" :key="p.date">
        <circle
          v-if="p.average !== null"
          :cx="x(i)"
          :cy="y(p.average)"
          r="4.5"
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
        {{ trend[i]?.date.slice(5) }}
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

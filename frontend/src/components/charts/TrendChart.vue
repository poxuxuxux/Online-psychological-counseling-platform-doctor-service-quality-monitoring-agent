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
    detailed?: boolean
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
const scoredPoints = computed(() => props.trend.filter((p) => p.average !== null))
const summary = computed(() => {
  const points = scoredPoints.value
  const count = points.reduce((sum, p) => sum + p.sample_count, 0)
  const first = points[0]?.average ?? 0
  const last = points.at(-1)?.average ?? 0
  return {
    average: count ? points.reduce((sum, p) => sum + p.average! * p.sample_count, 0) / count : 0,
    change: last - first,
    peak: points.length ? Math.max(...points.map((p) => p.average!)) : 0,
    count,
  }
})
const rolling = computed(() => props.trend.map((point, i) => {
  if (point.average === null) return null
  const window = props.trend.slice(Math.max(0, i - 6), i + 1).filter((p) => p.average !== null)
  const count = window.reduce((sum, p) => sum + p.sample_count, 0)
  return count ? window.reduce((sum, p) => sum + p.average! * p.sample_count, 0) / count : null
}))
const rollingPath = computed(() => {
  let previous = false
  return rolling.value.map((value, i) => {
    if (value === null) { previous = false; return '' }
    const command = previous ? 'L' : 'M'
    previous = true
    return `${command}${x(i)} ${y(value)}`
  }).join(' ')
})
const maxSamples = computed(() => Math.max(1, ...props.trend.map((p) => p.sample_count)))
const detailedTicks = computed(() => [...new Set(Array.from({ length: Math.min(6, props.trend.length) }, (_, i) => Math.round(i * (props.trend.length - 1) / Math.max(1, Math.min(6, props.trend.length) - 1))))])
</script>
<template>
  <div :class="['trend-area', { 'trend-detailed': detailed }]">
    <dl v-if="detailed && scoredPoints.length" class="trend-summary">
      <div><dt>周期均分</dt><dd>{{ summary.average.toFixed(1) }}<small> 分</small></dd></div>
      <div><dt>首末变化</dt><dd>{{ summary.change > 0 ? '+' : '' }}{{ summary.change.toFixed(1) }}<small> 分</small></dd></div>
      <div><dt>最高日均</dt><dd>{{ summary.peak.toFixed(1) }}<small> 分</small></dd></div>
      <div><dt>有效评价</dt><dd>{{ summary.count }}<small> 份</small></dd></div>
    </dl>
    <svg
      class="trend-chart"
      :viewBox="detailed ? '0 0 720 350' : '0 0 720 280'"
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
      <path v-if="detailed" :d="rollingPath" class="rolling-line" />
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
      <text v-for="i in (detailed ? detailedTicks : ticks)" :key="i" :x="x(i)" y="260" text-anchor="middle" class="chart-label">
        {{ tickLabel(i) }}
      </text>
      <g v-if="detailed" class="sample-bars" aria-label="每日有效评价数量">
        <text x="48" y="284" class="chart-tick">每日样本量（份）</text>
        <text x="688" y="284" text-anchor="end" class="chart-tick">最高 {{ maxSamples }} 份 / 天</text>
        <rect v-for="(p, i) in trend" :key="p.date" :x="x(i) - Math.min(10, 250 / Math.max(1, trend.length))" :y="330 - p.sample_count / maxSamples * 32" :width="Math.min(20, 500 / Math.max(1, trend.length))" :height="p.sample_count / maxSamples * 32" rx="1">
          <title>{{ p.date }}：{{ p.sample_count }} 份有效评价</title>
        </rect>
      </g>
    </svg>
    <div class="chart-legend">
      <span><i class="legend-line" />平均总分</span
      ><span v-if="detailed"><i class="legend-line rolling" />近 7 天均线</span><span><i class="legend-line quality" />85 分优质线</span
      ><span><i class="legend-line risk" />60 分风险边界</span>
    </div>
    <p class="chart-caption" aria-live="polite">
      {{
        selected
          ? `${selected.date} · ${selected.average?.toFixed(1)} 分 · ${selected.sample_count} 轮`
          : detailed ? '按日汇总有效评价；近 7 天均线按样本量加权，缺失日期留空。首末变化为最后与首个有效日均分之差。' : '按评估保存日期统计；无有效评分的日期留空。'
      }}
    </p>
  </div>
</template>

<style scoped>
.trend-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 14px; padding: 12px 0; border-bottom: 1px solid #e1ebe4; }
.trend-summary dt { color: #52685a; font-size: 13px; }
.trend-summary dd { margin: 6px 0 0; color: #244c37; font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
.trend-summary small { font-size: 12px; font-weight: 400; }
.rolling-line { fill: none; stroke: #8b6539; stroke-width: 2; stroke-dasharray: 6 4; pointer-events: none; }
.legend-line.rolling { border-color: #8b6539; border-top-style: dashed; background: transparent; }
.sample-bars rect { fill: #91bba3; }
.trend-detailed .chart-caption { color: #52685a; line-height: 1.7; }
.trend-detailed .chart-point:focus-visible { outline: 2px solid #245e40; outline-offset: 3px; }
@media (max-width: 560px) {
  .trend-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>

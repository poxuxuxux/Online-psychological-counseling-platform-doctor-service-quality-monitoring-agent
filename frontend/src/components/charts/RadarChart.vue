<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../base/Icon.vue'
import type { Overview } from '../../api/contracts/overview'
const props = withDefaults(
  defineProps<{ dimensions: Overview['dimensions']; scale?: 'percent' | 'five'; axisLabels?: boolean }>(),
  { scale: 'percent', axisLabels: false },
)
const active = ref<string | null>(null)
const displayScore = (score: number) => (props.scale === 'five' ? score / 20 : score)
const CENTER = 180
const RADIUS = 96
const axisAngle = (i: number) => -Math.PI / 2 + (i * Math.PI) / 3
const axisLabelPoint = (i: number) => {
  const angle = axisAngle(i)
  const cos = Math.cos(angle)
  const radius = Math.abs(cos) < 0.35 ? 132 : 106
  return {
    x: CENTER + cos * radius,
    y: CENTER + Math.sin(angle) * radius,
    anchor: cos > 0.35 ? 'start' : cos < -0.35 ? 'end' : 'middle',
  }
}
// 上下标签需要容纳图标、名称和分数；两侧标签从轴线外缘向外展开。
const CENTER_CHIP_RADIUS = 39
const SIDE_CHIP_RADIUS = 32
const point = (i: number, value: number, radius = RADIUS) => {
  const angle = axisAngle(i)
  return [CENTER + Math.cos(angle) * radius * (value / 100), CENTER + Math.sin(angle) * radius * (value / 100)]
}
const polygon = (value: number) =>
  props.dimensions.map((_, i) => point(i, value).join(',')).join(' ')
const complete = computed(() => props.dimensions.every((d) => d.average !== null))
const outline = computed(() =>
  props.dimensions.map((d, i) => point(i, d.average ?? 0).join(',')).join(' '),
)
const selected = computed(() => props.dimensions.find((d) => d.dimension_id === active.value))
const tones = ['jade', 'rose', 'amber', 'violet', 'rose', 'sky']
const icons = ['message', 'heart', 'zap', 'puzzle', 'alert', 'shield']
// 标签沿用数据轴的角度，避免标签环与雷达轴发生旋转偏差。
const chips = computed(() =>
  props.dimensions.map((d, i) => {
    const angle = axisAngle(i)
    const cos = Math.cos(angle)
    const side = Math.abs(cos) < 0.35 ? 'center' : cos > 0 ? 'right' : 'left'
    const radius = side === 'center' ? CENTER_CHIP_RADIUS : SIDE_CHIP_RADIUS
    return {
      ...d,
      icon: icons[i % icons.length]!,
      tone: tones[i % tones.length]!,
      side,
      axisIndex: i,
      style: {
        '--chip-left': `${50 + radius * cos}%`,
        '--chip-top': `${50 + radius * Math.sin(angle)}%`,
      },
    }
  }),
)
</script>
<template>
  <div class="radar-area">
    <div :class="['radar-shell', { 'axis-labeled': axisLabels }]">
      <svg
        class="radar-chart"
        viewBox="0 0 360 360"
        role="img"
        :aria-label="`六个维度平均分雷达图，满分${scale === 'five' ? '5' : '100'}分，详细数值见下方说明`"
      >
        <defs>
          <linearGradient id="radar-wash" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#5fbb92" stop-opacity="0.5" />
            <stop offset="100%" stop-color="#3f9f78" stop-opacity="0.22" />
          </linearGradient>
        </defs>
        <polygon
          v-for="v in [100, 80, 60, 40, 20]"
          :key="v"
          :points="polygon(v)"
          class="chart-grid radar-grid"
        />
        <g v-for="(d, i) in dimensions" :key="d.dimension_id">
          <line
            :x1="CENTER"
            :y1="CENTER"
            :x2="point(i, 100)[0]"
            :y2="point(i, 100)[1]"
            class="chart-grid radar-spoke"
          />
        </g>
        <text
          v-for="v in [20, 40, 60, 80, 100]"
          :key="v"
          x="186"
          :y="CENTER - v * (RADIUS / 100) + 4"
          class="chart-tick radar-tick"
        >
          {{ v }}
        </text>
        <g v-if="axisLabels" class="radar-axis-labels">
          <g v-for="(d, i) in dimensions" :key="`axis-label-${d.dimension_id}`">
            <text
              :x="axisLabelPoint(i).x"
              :y="axisLabelPoint(i).y"
              :text-anchor="axisLabelPoint(i).anchor"
              class="radar-axis-name"
            >{{ d.name }}</text>
            <text
              :x="axisLabelPoint(i).x"
              :y="axisLabelPoint(i).y + 17"
              :text-anchor="axisLabelPoint(i).anchor"
              class="radar-axis-score"
            >{{ d.average === null ? '—' : displayScore(d.average).toFixed(1) }}</text>
          </g>
        </g>
        <polygon v-if="complete" :points="outline" class="radar-fill" fill="url(#radar-wash)" />
        <g v-for="(d, i) in dimensions" :key="d.dimension_id">
          <circle
            v-if="d.average !== null"
            :cx="point(i, d.average)[0]"
            :cy="point(i, d.average)[1]"
            r="4"
            class="chart-point"
            tabindex="0"
            :aria-label="`${d.name}，${displayScore(d.average).toFixed(1)} 分，${d.sample_count} 轮`"
            @focus="active = d.dimension_id"
            @blur="active = null"
            @mouseenter="active = d.dimension_id"
            @mouseleave="active = null"
          >
          <title>{{ d.name }}：{{ displayScore(d.average).toFixed(1) }} 分，{{ d.sample_count }} 轮</title>
          </circle>
        </g>
      </svg>
      <span
        v-if="!axisLabels"
        v-for="c in chips"
        :key="c.dimension_id"
        :class="['radar-chip', c.tone, c.side, `axis-${c.axisIndex}`, { active: active === c.dimension_id }]"
        :style="c.style"
      >
        <i class="radar-chip-icon"><Icon :name="c.icon" :size="17" /></i>
        <span class="radar-chip-text">
          <span class="radar-chip-name">{{ c.name }}</span>
          <strong>{{ c.average === null ? '—' : displayScore(c.average).toFixed(1) }}</strong>
        </span>
      </span>
    </div>
    <p class="chart-caption" aria-live="polite">
      {{
        selected
          ? `${selected.name} · ${displayScore(selected.average!).toFixed(1)} 分 · ${selected.sample_count} 轮`
          : complete
            ? '面积展示维度均值；各维度样本数见下表。'
            : '部分维度暂无有效分数；缺失值留空，不补成 0 分。'
      }}
    </p>
  </div>
</template>

<style scoped>
.radar-shell.axis-labeled {
  display: block;
}
.radar-axis-name {
  fill: #61786b;
  font-size: 14px;
  font-weight: 550;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 3px;
  stroke-linejoin: round;
}
.radar-axis-score {
  fill: #203a2c;
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 3px;
  stroke-linejoin: round;
}
</style>

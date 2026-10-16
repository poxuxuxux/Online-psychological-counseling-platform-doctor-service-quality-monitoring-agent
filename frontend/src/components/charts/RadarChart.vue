<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Overview } from '../../api/contracts/overview'
const props = defineProps<{ dimensions: Overview['dimensions'] }>()
const active = ref<string | null>(null)
const point = (i: number, value: number, radius = 100) => {
  const angle = -Math.PI / 2 + (i * Math.PI) / 3
  return [
    180 + (Math.cos(angle) * radius * value) / 100,
    148 + (Math.sin(angle) * radius * value) / 100,
  ]
}
const polygon = (value: number) =>
  props.dimensions.map((_, i) => point(i, value).join(',')).join(' ')
const complete = computed(() => props.dimensions.every((d) => d.average !== null))
const outline = computed(() =>
  props.dimensions.map((d, i) => point(i, d.average ?? 0).join(',')).join(' '),
)
const selected = computed(() => props.dimensions.find((d) => d.dimension_id === active.value))
</script>
<template>
  <div class="radar-area">
    <svg
      class="radar-chart"
      viewBox="0 0 360 310"
      role="img"
      aria-label="六个维度平均分雷达图，满分100分，详细数值见下方表格"
    >
      <polygon
        v-for="v in [100, 80, 60, 40, 20]"
        :key="v"
        :points="polygon(v)"
        class="chart-grid radar-grid"
      />
      <g v-for="(d, i) in dimensions" :key="d.dimension_id">
        <line x1="180" y1="148" :x2="point(i, 100)[0]" :y2="point(i, 100)[1]" class="chart-grid" />
        <text
          :x="point(i, 100, 126)[0]"
          :y="point(i, 100, 126)[1] + 4"
          text-anchor="middle"
          class="chart-label"
        >
          {{ d.name }}
        </text>
      </g>
      <text v-for="v in [20, 40, 60, 80, 100]" :key="v" x="186" :y="148 - v + 4" class="chart-tick">
        {{ v }}
      </text>
      <polygon v-if="complete" :points="outline" class="radar-fill" fill="#087f7318" />
      <g v-for="(d, i) in dimensions" :key="d.dimension_id">
        <circle
          v-if="d.average !== null"
          :cx="point(i, d.average)[0]"
          :cy="point(i, d.average)[1]"
          r="5"
          class="chart-point"
          tabindex="0"
          :aria-label="`${d.name}，${d.average.toFixed(1)} 分，${d.sample_count} 轮`"
          @focus="active = d.dimension_id"
          @blur="active = null"
          @mouseenter="active = d.dimension_id"
          @mouseleave="active = null"
        >
          <title>{{ d.name }}：{{ d.average.toFixed(1) }} 分，{{ d.sample_count }} 轮</title>
        </circle>
      </g>
    </svg>
    <p class="chart-caption" aria-live="polite">
      {{
        selected
          ? `${selected.name} · ${selected.average?.toFixed(1)} 分 · ${selected.sample_count} 轮`
          : complete
            ? '面积展示维度均值；各维度样本数见下表。'
            : '部分维度暂无有效分数；缺失值留空，不补成 0 分。'
      }}
    </p>
  </div>
</template>

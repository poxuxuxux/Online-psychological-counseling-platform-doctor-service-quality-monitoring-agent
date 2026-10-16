<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value: number | null }>()
const circumference = 2 * Math.PI * 30
const amount = computed(() => (props.value === null ? 0 : Math.min(100, Math.max(0, props.value))))
</script>
<template>
  <svg
    class="score-ring"
    viewBox="0 0 76 76"
    role="img"
    :aria-label="value === null ? '平均总分尚不可用' : `平均总分 ${value.toFixed(1)} 分，满分100`"
  >
    <circle class="score-ring-track" cx="38" cy="38" r="30" />
    <circle
      v-if="value !== null"
      class="score-ring-value"
      cx="38"
      cy="38"
      r="30"
      :stroke-dasharray="circumference"
      :stroke-dashoffset="circumference * (1 - amount / 100)"
      transform="rotate(-90 38 38)"
    />
    <g v-if="value !== null">
      <text x="38" y="37" text-anchor="middle" class="score-ring-max">100</text>
      <text x="38" y="49" text-anchor="middle" class="score-ring-label">满分</text>
    </g>
    <path v-else d="M30 38h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
  </svg>
</template>

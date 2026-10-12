<script setup lang="ts">
const props = defineProps<{ label: string; tone?: 'blue' | 'green' | 'amber' | 'red' | 'slate' | 'purple' }>()
const tone = props.tone ?? 'slate'
</script>

<template>
  <span class="status-badge" :class="`status-badge--${tone}`"><span class="status-dot" />{{ label }}</span>
</template>

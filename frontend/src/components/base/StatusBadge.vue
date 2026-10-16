<script setup lang="ts">
withDefaults(defineProps<{ tone?: string }>(), { tone: 'neutral' })
</script>
<template>
  <span :class="['status-badge', `tone-${tone}`]"
    ><span class="status-dot" aria-hidden="true"></span><slot
  /></span>
</template>

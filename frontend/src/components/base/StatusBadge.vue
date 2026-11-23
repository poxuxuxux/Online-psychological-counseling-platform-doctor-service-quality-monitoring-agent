<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
withDefaults(defineProps<{ tone?: string }>(), { tone: 'neutral' })
</script>
<template>
  <span :class="['status-badge', `tone-${tone}`]"
    ><span class="status-dot" aria-hidden="true"></span><slot
  /></span>
</template>

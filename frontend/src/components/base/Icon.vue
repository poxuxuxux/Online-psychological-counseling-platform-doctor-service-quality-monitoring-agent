<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  radar: 'M12 2 21 7v10l-9 5-9-5V7z M12 2v20 M3 7l18 10 M21 7 3 17 M12 6l6 3v6l-6 3-6-3V9z',
  trend: 'M3 3v18h18 M6 15l5-6 4 3 6-8',
  pulse: 'M3 12h4l3-8 4 16 3-8h4',
  workspace: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  report: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h6',
  shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7z M8 12l3 3 5-6',
  list: 'M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01',
  settings: 'M3 5h18 M3 12h18 M3 19h18 M7 3v4 M17 10v4 M9 17v4',
  chevron: 'm9 5 7 7-7 7',
  arrow: 'M5 12h14 M12 5l7 7-7 7',
  play: 'm8 5 11 7-11 7z',
  check: 'm5 12 4 4L19 6',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 2 M18 18a8 8 0 0 1-13-2',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  download: 'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5',
  close: 'm6 6 12 12 M6 18 18 6',
  menu: 'M3 6h18 M3 12h18 M3 18h18',
  clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  link: 'm10 13 4-4 M8 16l-2 2a4 4 0 0 1-6-6l4-4 M16 8l2-2a4 4 0 0 1 6 6l-4 4',
  info: 'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.info" />
  </svg>
</template>

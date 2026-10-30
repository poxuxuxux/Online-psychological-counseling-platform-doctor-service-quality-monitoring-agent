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
  upload: 'M12 16V3m0 0-4 4m4-4 4 4M4 16v4h16v-4',
  check: 'm5 12 4 4L19 6',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 2 M18 18a8 8 0 0 1-13-2',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  download: 'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5',
  close: 'm6 6 12 12 M6 18 18 6',
  menu: 'M3 6h18 M3 12h18 M3 18h18',
  clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  link: 'm10 13 4-4 M8 16l-2 2a4 4 0 0 1-6-6l4-4 M16 8l2-2a4 4 0 0 1 6 6l-4 4',
  info: 'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  bell: 'M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9 M13.7 21a2 2 0 0 1-3.4 0',
  calendar: 'M4 5h16v16H4z M4 10h16 M8 3v4 M16 3v4',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4',
  moon: 'M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z',
  message: 'M21 11.5a8.4 8.4 0 0 1-9 8.4 9.9 9.9 0 0 1-3.6-.7L3 21l1.8-4.4A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z',
  star: 'm12 3 2.9 5.9 6.1.9-4.4 4.3 1 6.4-5.6-3-5.6 3 1-6.4L3 9.8l6.1-.9z',
  medal: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12 M8.2 13.6 7 22l5-2.6L17 22l-1.2-8.4',
  alert: 'M12 3 2 21h20z M12 9v5 M12 18h.01',
  heart: 'M12 21s-9-5.2-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 5.8-9 11-9 11z',
  zap: 'M13 2 4 14h6l-1 8 9-12h-6z',
  puzzle: 'M9 3h6v2a2 2 0 1 0 4 0h2v6h-2a2 2 0 1 0 0 4h2v6h-6v-2a2 2 0 1 0-4 0H9v-6H7a2 2 0 1 0 0-4h2z',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
  command: 'M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z',
  sparkle: 'm12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
  'arrow-up-right': 'M7 17 17 7 M8 7h9v9',
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

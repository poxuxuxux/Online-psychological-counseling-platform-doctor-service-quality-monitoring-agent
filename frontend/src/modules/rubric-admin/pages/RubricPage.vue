<script setup lang="ts">
import { BookOpenText, CheckCheck, FileClock } from 'lucide-vue-next'
import { metricCatalog } from '../../../api/demoData'

const dimensions = [...new Set(metricCatalog.map((metric) => metric.dimension))]
</script>

<template>
  <div class="page-stack"><div class="page-heading"><span class="eyebrow">RUBRIC CATALOG</span><h1>质检指标</h1><p>基于项目确认的第二版指标表，展示六个维度、18项指标及评价职责。</p></div><div class="rubric-intro"><div class="rubric-intro__icon"><BookOpenText :size="25" /></div><div><span class="eyebrow">CURRENT CATALOG</span><h2>竞赛指标 v0.1</h2><p>指标名称与 Agent 归属用于前端联调；评分锚点、权重和发布流程仍需团队共同确定。</p></div><div class="rubric-intro__meta"><span><CheckCheck :size="16" />18项指标</span><span><FileClock :size="16" />规则版本待发布</span></div></div><div class="rubric-grid"><section v-for="dimension in dimensions" :key="dimension" class="panel rubric-card"><div class="rubric-card__head"><span class="rubric-card__code">{{ dimension.split(' ')[0] }}</span><div><h2>{{ dimension.split(' ').slice(1).join(' ') }}</h2><small>{{ metricCatalog.filter((item) => item.dimension === dimension).length }} 项二级指标</small></div></div><div v-for="item in metricCatalog.filter((entry) => entry.dimension === dimension)" :key="item.id" class="rubric-metric"><span>{{ item.id }}</span><div><strong>{{ item.name }}</strong><small>{{ item.owner }}</small></div></div></section></div><div class="notice notice--blue"><strong>指标适用规则</strong><span>D6.1 和 D6.2 默认进入评价任务，再由各自负责的 Agent 判断是否适用；风险 Hook 的命中情况不改变指标归属。</span></div></div>
</template>

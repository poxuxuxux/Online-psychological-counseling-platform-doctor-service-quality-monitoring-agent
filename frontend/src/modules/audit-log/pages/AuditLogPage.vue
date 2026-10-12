<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { FileClock, Info } from 'lucide-vue-next'
import { service } from '../../../api/service'
import EmptyState from '../../../components/base/EmptyState.vue'
import type { AuditEvent } from '../../../types/domain'
import { shortDate } from '../../../utils/display'

const events = ref<AuditEvent[]>([])
const loading = ref(true)
const error = ref('')
onMounted(async () => {
  try { events.value = await service.audit() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '审计记录加载失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page-stack"><div class="page-heading"><span class="eyebrow">AUDIT TRAIL</span><h1>审计日志</h1><p>查看任务、报告与人工复核操作的记录。</p></div><div class="notice notice--blue"><Info :size="19" /><div><strong>关于演示记录</strong><span>当前仅展示前端内存中的合成事件。真实业务的完整、不可静默覆盖审计必须由后端存储与校验。</span></div></div><section class="panel panel--flush"><div class="panel-heading"><div><span class="eyebrow">ACTIVITY LOG</span><h2>最近操作</h2></div><FileClock :size="19" /></div><div v-if="loading" class="loading-state">正在加载操作记录…</div><div v-else-if="error" class="error-panel" role="alert">{{ error }}</div><EmptyState v-else-if="!events.length" title="暂无操作记录" /><div v-else class="audit-list"><div v-for="item in events" :key="item.id" class="audit-row"><span class="audit-row__icon"><FileClock :size="18" /></span><div><strong>{{ item.action }}</strong><p>{{ item.detail }}</p><small>{{ item.target }}</small></div><time>{{ shortDate(item.at) }}</time></div></div></section></div>
</template>

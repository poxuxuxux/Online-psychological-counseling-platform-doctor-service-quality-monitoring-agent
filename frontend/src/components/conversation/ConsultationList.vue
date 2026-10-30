<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ConsultationItem } from '../../api/contracts/consultations'
import Icon from '../base/Icon.vue'
import { label, time } from '../../utils/catalog'
const props = defineProps<{
  items: ConsultationItem[]
  total: number
  offset: number
  query: string
  selectedId?: string
  loading: boolean
  selecting: boolean
  disabled: boolean
  error: string
  source: 'preview' | 'database' | 'uploaded' | 'access_required' | 'unavailable'
}>()
const emit = defineEmits<{ select: [id: string]; evaluate: [id: string]; refresh: [offset: number, query: string] }>()
const search = ref(props.query)
watch(
  () => props.query,
  (value) => (search.value = value),
)
</script>
<template>
  <section class="workspace-panel session-panel service-session-panel" aria-labelledby="consultations-title">
    <div class="panel-title-row">
      <div><h2 id="consultations-title">咨询会话列表</h2><p>{{ total }} 条{{ source === 'database' ? '后端' : source === 'uploaded' ? '已上传' : '可用' }}会话</p></div>
      <span class="panel-count">{{ loading ? '…' : total }}</span>
    </div>
    <form class="service-session-filters consultation-list-tools" @submit.prevent="emit('refresh', 0, search)">
      <label class="workspace-search search-field"><Icon name="search" :size="16" /><input v-model="search" aria-label="搜索咨询 ID" placeholder="搜索会话 ID" maxlength="120" /></label>
      <button class="service-refresh-button" type="submit" :disabled="loading || disabled" aria-label="查询会话"><Icon name="search" :size="16" /></button>
      <button class="service-refresh-button" type="button" :disabled="loading || disabled" aria-label="刷新列表" @click="emit('refresh', offset, query)"><Icon name="refresh" :size="16" /></button>
    </form>
    <div v-if="error" class="service-list-error" role="alert">
      <p>{{ error }}</p>
      <button type="button" class="text-button" :disabled="loading || disabled" @click="emit('refresh', offset, query)">重新读取列表</button>
    </div>
    <div v-else class="service-session-list" :aria-busy="loading" aria-label="咨询会话">
      <article v-for="item in items" :key="item.session_id" :class="['service-session-item', 'consultation-row', { selected: item.session_id === selectedId }]">
        <button class="service-session-select" type="button" :disabled="disabled || loading" :aria-pressed="item.session_id === selectedId" :aria-label="`查看咨询 ${item.session_id} 的详细内容`" @click="emit('select', item.session_id)">
          <span class="session-item-top"><strong class="consultation-id">{{ item.session_id }}</strong><span :class="['session-status', item.evaluation_status || 'pending']">{{ item.evaluation_status ? label(item.evaluation_status) : '未评价' }}</span></span>
          <span class="session-item-meta"><span>{{ label(item.consultation_round) }}</span><time>{{ time(item.updated_at) }}</time></span>
          <span class="session-item-bottom"><span>{{ item.message_count }} 条消息</span><Icon name="chevron" :size="14" /></span>
        </button>
        <button class="service-session-evaluate consultation-evaluate" type="button" :disabled="disabled || loading || selecting" :aria-label="`评估咨询 ${item.session_id}`" @click="emit('evaluate', item.session_id)"><Icon name="play" :size="14" />评估</button>
      </article>
      <div v-if="!items.length && !loading" class="session-empty">
        <Icon name="search" :size="26" /><strong>{{ query ? '没有找到匹配会话' : '暂无可查看的咨询记录' }}</strong>
        <p>{{ query ? '请调整关键词后重新查询。' : source === 'access_required' ? '上传 JSON 文件，或切换到离线数据。' : '可通过上方按钮上传咨询数据。' }}</p>
      </div>
      <div v-if="loading" class="service-session-loading" role="status">正在读取会话…</div>
    </div>
    <footer class="session-pagination">
      <button type="button" aria-label="上一页" :disabled="offset === 0 || loading || disabled" @click="emit('refresh', Math.max(0, offset - 5), query)"><Icon class="flip-icon" name="chevron" :size="15" /></button>
      <span>{{ Math.floor(offset / 5) + 1 }} / {{ Math.max(1, Math.ceil(total / 5)) }}</span>
      <button type="button" aria-label="下一页" :disabled="offset + 5 >= total || loading || disabled" @click="emit('refresh', offset + 5, query)"><Icon name="chevron" :size="15" /></button>
    </footer>
  </section>
</template>

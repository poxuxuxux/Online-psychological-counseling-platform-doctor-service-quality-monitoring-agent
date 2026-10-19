<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ConsultationItem } from '../../api/contracts/consultations'
import Icon from '../base/Icon.vue'
import StatusBadge from '../base/StatusBadge.vue'
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
  source: 'preview' | 'database' | 'demo' | 'unavailable'
}>()
const emit = defineEmits<{ select: [id: string]; refresh: [offset: number, query: string] }>()
const search = ref(props.query)
watch(
  () => props.query,
  (value) => (search.value = value),
)
</script>
<template>
  <section class="surface consultation-browser" aria-labelledby="consultations-title">
    <div class="consultation-list-heading">
      <div>
        <h2 id="consultations-title">咨询对话</h2>
        <p>选择咨询 ID，在下方查看咨询记录与服务质量评价。</p>
      </div>
      <StatusBadge :tone="source === 'database' ? 'success' : 'neutral'">{{
        source === 'database'
          ? '数据库记录'
          : source === 'preview'
            ? '3 条合成样例'
            : source === 'demo'
              ? '后端演示记录'
              : '列表暂不可用'
      }}</StatusBadge>
    </div>
    <form class="consultation-list-tools" @submit.prevent="emit('refresh', 0, search)">
      <label class="search-field"
        ><Icon name="search" :size="17" /><input
          v-model="search"
          aria-label="搜索咨询 ID"
          placeholder="输入咨询 ID"
          maxlength="120"
      /></label>
      <button class="button secondary" :disabled="loading || disabled">查询</button>
      <button
        type="button"
        class="text-button"
        :disabled="loading || disabled"
        @click="emit('refresh', offset, query)"
      >
        <Icon name="refresh" :size="16" />刷新列表
      </button>
      <span class="consultation-count">{{
        loading ? '正在读取…' : error ? '读取失败' : `共 ${total} 条`
      }}</span>
    </form>
    <div v-if="error" class="alert danger" role="alert">
      <p>{{ error }}</p>
      <button
        class="text-button"
        :disabled="loading || disabled"
        @click="emit('refresh', offset, query)"
      >
        重新读取列表
      </button>
    </div>
    <div v-else class="consultation-table-wrap" :aria-busy="loading">
      <table class="consultation-table">
        <thead>
          <tr>
            <th scope="col">咨询 ID</th>
            <th scope="col">会话类型</th>
            <th scope="col">消息数</th>
            <th scope="col">更新时间</th>
            <th scope="col">评价状态</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.session_id"
            :class="{ active: item.session_id === selectedId }"
          >
            <td>
              <button
                class="consultation-id"
                :disabled="disabled || loading"
                :aria-pressed="item.session_id === selectedId"
                @click="emit('select', item.session_id)"
              >
                <Icon name="report" :size="17" />{{ item.session_id }}
              </button>
            </td>
            <td>{{ label(item.consultation_round) }}</td>
            <td>{{ item.message_count }} 条</td>
            <td>{{ time(item.updated_at) }}</td>
            <td>
              <StatusBadge
                :tone="
                  item.evaluation_status === 'failed'
                    ? 'danger'
                    : item.evaluation_status
                      ? 'neutral'
                      : 'warning'
                "
                >{{
                  item.evaluation_status ? label(item.evaluation_status) : '未评价'
                }}</StatusBadge
              >
            </td>
            <td>
              <button
                class="text-button"
                :disabled="disabled || loading"
                @click="emit('select', item.session_id)"
              >
                {{ item.session_id === selectedId ? '已选中' : '查看'
                }}<Icon name="chevron" :size="14" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!items.length && !loading" class="empty-note padded">
        {{ query ? '没有匹配的咨询 ID，请修改查询条件。' : '暂无可查看的咨询记录。' }}
      </p>
    </div>
    <div class="consultation-list-footer">
      <small>{{
        selecting
          ? '正在加载所选咨询，请稍候…'
          : source === 'demo'
            ? '数据库暂无可用记录或列表接口尚未部署，当前仅展示内置演示。'
            : source === 'preview'
              ? '离线合成数据，用于演示 ID 切换；不代表真实咨询。'
              : '每页最多展示 5 条，点击 ID 查看已有报告。'
      }}</small>
      <div>
        <button
          class="text-button"
          :disabled="offset === 0 || loading || disabled"
          @click="emit('refresh', Math.max(0, offset - 5), query)"
        >
          上一页</button
        ><span>{{ Math.floor(offset / 5) + 1 }} / {{ Math.max(1, Math.ceil(total / 5)) }}</span
        ><button
          class="text-button"
          :disabled="offset + 5 >= total || loading || disabled"
          @click="emit('refresh', offset + 5, query)"
        >
          下一页
        </button>
      </div>
    </div>
  </section>
</template>

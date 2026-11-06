<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Session } from '../../api/contracts/evaluation'
import Icon from '../base/Icon.vue'
import { label, time } from '../../utils/catalog'
const props = withDefaults(defineProps<{
  session: Session | null
  highlightedIds: string[]
  showViewToggle?: boolean
  initialMessageCount?: number
  evidenceMessageIds?: string[]
}>(), {
  showViewToggle: false,
  initialMessageCount: 0,
  evidenceMessageIds: () => [],
})
const emit = defineEmits<{ locateEvidence: [messageId: string] }>()
const search = ref('')
const viewMode = ref<'original' | 'structured'>('original')
const showAllMessages = ref(false)
const messages = computed(() =>
  [...(props.session?.messages || [])].sort((a, b) => a.sequence - b.sequence),
)
const visibleMessages = computed(() =>
  props.initialMessageCount > 0 && !showAllMessages.value
    ? messages.value.slice(0, props.initialMessageCount)
    : messages.value,
)
const roles: Record<string, string> = {
  doctor: '咨询医生',
  patient: '匿名咨询者',
  system: '系统消息',
  unknown: '角色未确认',
}
function matches(content: string) {
  return !search.value || content.includes(search.value)
}
</script>
<template>
  <section :class="['conversation-panel surface', { 'service-conversation-panel': showViewToggle }]" aria-labelledby="conversation-title">
    <div :class="showViewToggle ? 'panel-title-row conversation-heading' : 'panel-header'">
      <div>
        <h2 id="conversation-title">本次咨询记录</h2>
        <p>
          {{
            session
              ? `${label(session.consultation_round)} · ${session.messages.length} 条消息`
              : '尚未加载会话'
          }}
        </p>
      </div>
      <div v-if="showViewToggle" class="view-tabs" role="group" aria-label="记录视图">
        <button type="button" :class="{ active: viewMode === 'original' }" :aria-pressed="viewMode === 'original'" @click="viewMode = 'original'">原文</button>
        <button type="button" :class="{ active: viewMode === 'structured' }" :aria-pressed="viewMode === 'structured'" @click="viewMode = 'structured'">结构化</button>
      </div>
      <span v-else class="mini-label">合成数据</span>
    </div>
    <label v-if="!showViewToggle" class="search-field"
      ><Icon name="search" :size="17" /><input
        v-model="search"
        aria-label="搜索会话内容"
        placeholder="查找本次会话内容" /><button
        v-if="search"
        class="icon-button"
        aria-label="清空搜索"
        @click="search = ''"
      >
        <Icon name="close" :size="16" /></button
    ></label>
    <div v-if="!showViewToggle || viewMode === 'original'" class="conversation-list">
      <div v-if="!session" class="empty-state compact">
        <Icon name="list" :size="32" />
        <h3>先加载一轮咨询</h3>
        <p>选择合成示例后，在这里查看原始消息。</p>
      </div>
      <p v-else-if="search && !messages.some((m) => matches(m.content))" class="empty-note">
        没有匹配的消息。清空搜索可查看完整上下文。
      </p>
      <article
        v-for="message in visibleMessages"
        v-show="matches(message.content) || highlightedIds.includes(message.message_id)"
        :key="message.message_id"
        :id="`message-${message.message_id}`"
        tabindex="-1"
        :class="[
          'conversation-message',
          message.role,
          { highlighted: highlightedIds.includes(message.message_id) },
        ]"
      >
        <template v-if="showViewToggle">
          <span class="message-avatar" aria-hidden="true">{{ message.role === 'doctor' ? '医' : message.role === 'patient' ? '访' : '系' }}</span>
          <div class="message-content">
            <div class="message-meta"><strong>{{ roles[message.role] }}</strong><time>{{ time(message.timestamp) }}</time></div>
            <p class="message-bubble">{{ message.content }}</p>
            <div class="message-foot">
              <span>{{ message.message_id }}</span>
              <span v-if="highlightedIds.includes(message.message_id)" class="evidence-marker">当前引用证据</span>
              <span v-else-if="message.modality !== 'text'">{{ message.modality === 'audio' ? '语音转写' : '视频转写' }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="message-meta">
            <span class="speaker-mark">{{ message.role === 'doctor' ? '医' : message.role === 'patient' ? '咨' : '系' }}</span>
            <strong>{{ roles[message.role] }}</strong><time>{{ time(message.timestamp) }}</time>
          </div>
          <p class="message-bubble">{{ message.content }}</p>
          <div class="message-foot">
            <span>{{ message.message_id }}</span>
            <button v-if="evidenceMessageIds.includes(message.message_id)" class="evidence-tag" type="button" @click="viewMode = 'original'; showAllMessages = true; emit('locateEvidence', message.message_id)"><Icon name="link" :size="12" />查看证据</button>
            <span v-else-if="highlightedIds.includes(message.message_id)" class="evidence-marker">当前引用证据</span>
            <span v-else-if="message.modality !== 'text'">{{ message.modality === 'audio' ? '语音转写' : '视频转写' }}</span>
          </div>
        </template>
      </article>
    </div>
    <div v-else class="structured-view">
      <table>
        <thead><tr><th>序号</th><th>角色</th><th>时间</th><th>消息内容</th></tr></thead>
        <tbody>
          <tr v-for="(message, index) in messages" :key="message.message_id" :id="`message-${message.message_id}`" tabindex="-1">
            <td>{{ index + 1 }}</td><td>{{ roles[message.role] }}</td><td>{{ time(message.timestamp) }}</td>
            <td :class="{ 'structured-evidence': highlightedIds.includes(message.message_id) }">{{ message.content }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <footer v-if="showViewToggle && session" class="conversation-footer">
      <button v-if="initialMessageCount > 0 && messages.length > initialMessageCount" type="button" @click="showAllMessages = !showAllMessages"><Icon name="chevron" :size="13" :class="{ 'rotate-icon': showAllMessages }" />消息 {{ visibleMessages.length }} / {{ messages.length }}</button>
      <span v-else>消息 {{ messages.length }} / {{ messages.length }}</span>
      <span>{{ initialMessageCount > 0 ? '查看证据定位' : '记录已加载' }}</span>
    </footer>
    <div v-else-if="session" class="panel-footer">仅展示本次轮次；历史背景不能作为本次行为的评分证据。</div>
  </section>
</template>

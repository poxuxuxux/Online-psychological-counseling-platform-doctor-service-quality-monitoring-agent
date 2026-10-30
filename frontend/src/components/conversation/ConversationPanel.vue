<!-- 环节：前端组件层；用途：实现可复用的会话、图表、反馈或基础界面组件。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Session } from '../../api/contracts/evaluation'
import Icon from '../base/Icon.vue'
import { label, time } from '../../utils/catalog'
const props = defineProps<{ session: Session | null; highlightedIds: string[] }>()
const search = ref('')
const messages = computed(() =>
  [...(props.session?.messages || [])].sort((a, b) => a.sequence - b.sequence),
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
  <section class="conversation-panel surface" aria-labelledby="conversation-title">
    <div class="panel-header">
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
      <span class="mini-label">{{ session?.source_id === 'synthetic-demo' || session?.source_id === 'offline-preview' ? '合成数据' : '本次会话' }}</span>
    </div>
    <label class="search-field"
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
    <div class="conversation-list">
      <div v-if="!session" class="empty-state compact">
        <Icon name="list" :size="32" />
        <h3>先加载一轮咨询</h3>
        <p>选择合成示例后，在这里查看原始消息。</p>
      </div>
      <p v-else-if="search && !messages.some((m) => matches(m.content))" class="empty-note">
        没有匹配的消息。清空搜索可查看完整上下文。
      </p>
      <article
        v-for="message in messages"
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
        <div class="message-meta">
          <span class="speaker-mark">{{
            message.role === 'doctor' ? '医' : message.role === 'patient' ? '咨' : '系'
          }}</span
          ><strong>{{ roles[message.role] }}</strong
          ><time>{{ time(message.timestamp) }}</time>
        </div>
        <p class="message-bubble">{{ message.content }}</p>
        <div class="message-foot">
          <span>{{ message.message_id }}</span
          ><span v-if="highlightedIds.includes(message.message_id)" class="evidence-marker"
            >当前引用证据</span
          ><span v-else-if="message.modality !== 'text'">{{
            message.modality === 'audio' ? '语音转写' : '视频转写'
          }}</span>
        </div>
      </article>
    </div>
    <div v-if="session" class="panel-footer">
      仅展示本次轮次；历史背景不能作为本次行为的评分证据。
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import Icon from '../base/Icon.vue'
import {
  createWorkspaceSessions,
  workspaceStatusText,
  type WorkspaceGroup,
  type WorkspaceMessage,
  type WorkspaceMetric,
  type WorkspaceSession,
  type WorkspaceStatus,
} from '../../data/workspacePreview'
import { isDateInRange, useDateRange } from '../../composables/dateRange'

const emit = defineEmits<{ history: []; notify: [message: string] }>()
const sessions = ref<WorkspaceSession[]>(createWorkspaceSessions())
const dateRange = useDateRange()
const selectedId = ref(sessions.value[0]!.id)
const query = ref('')
const statusFilter = ref<'all' | WorkspaceStatus>('all')
const currentPage = ref(1)
const pageSize = 6
const viewMode = ref<'original' | 'structured'>('original')
const showAllMessages = ref(false)
const highlightedIds = ref<string[]>([])
const activeMetric = ref<WorkspaceMetric | null>(null)
const collapsedGroups = ref<string[]>([])
const metricFilter = ref<'all' | 'attention'>('all')
const running = ref(false)
const progress = ref(100)
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadMessage = ref('')
let evaluationTimer: ReturnType<typeof setInterval> | undefined

const periodSessions = computed(() => sessions.value.filter((item) => isDateInRange(item.updatedAt, dateRange.value)))
const selected = computed(() => periodSessions.value.find((item) => item.id === selectedId.value) || periodSessions.value[0] || sessions.value[0]!)
const filteredSessions = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return periodSessions.value.filter((item) =>
    (statusFilter.value === 'all' || item.status === statusFilter.value) &&
    isDateInRange(item.updatedAt, dateRange.value) &&
    (!keyword || `${item.id} ${item.doctor} ${item.patient}`.toLowerCase().includes(keyword)),
  )
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredSessions.value.length / pageSize)))
const visibleSessions = computed(() => filteredSessions.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const visibleMessages = computed(() => showAllMessages.value ? selected.value.messages : selected.value.messages.slice(0, 6))
const visibleGroups = computed(() => selected.value.groups.map((group) => ({
  ...group,
  metrics: group.metrics.filter((metric) => metricFilter.value === 'all' || metric.score < 4),
})).filter((group) => group.metrics.length))
const currentStage = computed(() => {
  if (!running.value) return selected.value.status === 'pending' ? 1 : 4
  if (progress.value < 28) return 1
  if (progress.value < 52) return 2
  if (progress.value < 92) return 3
  return 4
})
const runLabel = computed(() => {
  if (running.value) return `评估中 ${progress.value}%`
  return selected.value.status === 'completed' ? '重新评估' : '开始评估任务'
})

watch(() => [dateRange.value.start, dateRange.value.end], () => {
  currentPage.value = 1
  const first = periodSessions.value[0]
  if (first) selectSession(first.id)
  else selectedId.value = ''
})

function groupAverage(group: WorkspaceGroup) {
  return (group.metrics.reduce((sum, metric) => sum + metric.score, 0) / group.metrics.length).toFixed(1)
}
function selectSession(id: string) {
  if (running.value || id === selectedId.value) return
  selectedId.value = id
  activeMetric.value = null
  highlightedIds.value = []
  showAllMessages.value = false
  viewMode.value = 'original'
  metricFilter.value = 'all'
  progress.value = selected.value.status === 'pending' ? 0 : 100
}
function toggleGroup(id: string) {
  collapsedGroups.value = collapsedGroups.value.includes(id)
    ? collapsedGroups.value.filter((item) => item !== id)
    : [...collapsedGroups.value, id]
}
function chooseMetric(metric: WorkspaceMetric) {
  activeMetric.value = activeMetric.value?.code === metric.code ? null : metric
}
async function locateEvidence(id: string) {
  viewMode.value = 'original'
  showAllMessages.value = true
  highlightedIds.value = [id]
  await nextTick()
  const target = document.getElementById(`workspace-${selected.value.id}-${id}`)
  target?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' })
  target?.focus({ preventScroll: true })
}
function startEvaluation() {
  if (running.value) return
  running.value = true
  progress.value = 4
  activeMetric.value = null
  clearInterval(evaluationTimer)
  evaluationTimer = setInterval(() => {
    progress.value = Math.min(100, progress.value + 8)
    if (progress.value >= 100) {
      clearInterval(evaluationTimer)
      running.value = false
      selected.value.status = 'completed'
      emit('notify', `${selected.value.id} 的离线演示评估已完成，未调用模型或后端服务。`)
    }
  }, 160)
}
function resetFilters() {
  query.value = ''
  statusFilter.value = 'all'
  currentPage.value = 1
}
function exportReport() {
  const content = JSON.stringify({ dataType: 'offline-synthetic-demo', exportedAt: new Date().toISOString(), session: selected.value }, null, 2)
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `心衡-${selected.value.id}-离线评价.json`
  anchor.click()
  URL.revokeObjectURL(url)
  emit('notify', '离线评价已导出为 JSON 文件。')
}
function importedGroups(messages: WorkspaceMessage[]) {
  return sessions.value[0]!.groups.map((group, groupIndex) => ({
    ...group,
    metrics: group.metrics.map((metric) => ({
      ...metric,
      score: 4,
      evidenceId: messages[Math.min(groupIndex * 2 + 1, messages.length - 1)]!.id,
    })),
  }))
}
async function importSession(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    if (file.size > 2_000_000) throw new Error('文件超过 2 MB，请按会话拆分后上传。')
    const data = JSON.parse(await file.text()) as Partial<WorkspaceSession> & { session_id?: string }
    if (!data.session_id && !data.id) throw new Error('缺少 session_id 或 id 字段。')
    if (!Array.isArray(data.messages) || !data.messages.length) throw new Error('messages 需要包含至少一条消息。')
    const id = String(data.session_id || data.id)
    if (sessions.value.some((item) => item.id === id)) throw new Error('该会话 ID 已存在，请检查后重试。')
    const messages: WorkspaceMessage[] = data.messages.map((message, index) => {
      if (!message || typeof message.content !== 'string' || !message.content.trim()) throw new Error(`第 ${index + 1} 条消息缺少有效内容。`)
      return {
        id: message.id || `imported-m${index + 1}`,
        role: message.role === 'doctor' ? 'doctor' : 'patient',
        time: message.time || '未提供时间',
        content: message.content,
      }
    })
    const session: WorkspaceSession = {
      id,
      doctor: typeof data.doctor === 'string' ? data.doctor : '未命名医生',
      patient: typeof data.patient === 'string' ? data.patient : '本页导入来访者',
      updatedAt: messages[0]!.time,
      status: 'pending',
      score: 4,
      summary: '这是本页导入的离线演示数据。完成模拟评估后，可查看预设指标交互；结果不代表真实模型评价。',
      messages,
      groups: importedGroups(messages),
    }
    sessions.value.unshift(session)
    selectedId.value = id
    statusFilter.value = 'all'
    query.value = ''
    currentPage.value = 1
    activeMetric.value = null
    progress.value = 0
    uploadMessage.value = `已在本页载入 ${id}，未上传至服务器。`
  } catch (error) {
    uploadMessage.value = `导入失败：${(error as Error).message}`
  }
}

watch([query, statusFilter], () => { currentPage.value = 1 })
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })
onUnmounted(() => clearInterval(evaluationTimer))
</script>

<template>
  <div class="evaluation-workspace">
    <header class="workspace-heading">
      <div>
        <div class="heading-title-line">
          <h1>评估工作台</h1>
          <span class="offline-badge"><i aria-hidden="true"></i>离线演示</span>
        </div>
        <p>选择咨询会话，查看原文并启动多智能体服务质量评价。</p>
      </div>
      <div class="workspace-actions">
        <button class="workspace-button secondary" type="button" @click="emit('history')">
          <Icon name="clock" :size="17" />历史任务
        </button>
        <button class="workspace-button secondary" type="button" :disabled="running" @click="uploadInput?.click()">
          <Icon name="upload" :size="17" />上传咨询数据
        </button>
        <input id="workspace-session-import" ref="uploadInput" class="visually-hidden" type="file" accept=".json,application/json" :disabled="running" @change="importSession" />
        <button class="workspace-button primary" type="button" :disabled="running || !periodSessions.length" @click="startEvaluation">
          <Icon :name="running ? 'clock' : 'play'" :size="17" />{{ runLabel }}
        </button>
      </div>
    </header>

    <section v-if="periodSessions.length" class="process-panel" aria-label="评估任务进度">
      <ol class="process-steps">
        <li v-for="(step, index) in [
          ['上传数据', '支持 JSON 格式'],
          ['数据解析', '自动校验与结构化'],
          ['AI 评价中', '多智能体协同评估'],
          ['评价完成', '生成结果与报告'],
        ]" :key="step[0]" :class="['process-step', { complete: currentStage > index + 1, active: currentStage === index + 1 }]">
          <span class="step-marker"><Icon v-if="currentStage > index + 1" name="check" :size="16" /><b v-else>{{ index + 1 }}</b></span>
          <span class="step-copy"><strong>{{ step[0] }}</strong><small>{{ step[1] }}</small></span>
          <Icon v-if="index < 3" class="step-arrow" name="chevron" :size="15" />
        </li>
      </ol>
      <div class="process-progress">
        <div><span>{{ running ? '正在执行离线演示评估' : selected.status === 'pending' ? '等待开始评估' : '本次评价流程' }}</span><strong>{{ running ? progress : selected.status === 'pending' ? 0 : 100 }}%</strong></div>
        <span class="progress-track" role="progressbar" aria-label="评估进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="running ? progress : selected.status === 'pending' ? 0 : 100"><i :style="{ width: `${running ? progress : selected.status === 'pending' ? 0 : 100}%` }"></i></span>
        <small>{{ running ? `正在处理 ${selected.id}` : `${selected.messages.length} 条消息 · 18 项评价指标` }}</small>
      </div>
    </section>
    <p v-if="uploadMessage" class="upload-feedback" role="status">{{ uploadMessage }}</p>

    <div v-if="periodSessions.length" class="evaluation-layout">
      <section class="workspace-panel session-panel" aria-labelledby="session-list-title">
        <div class="panel-title-row">
          <div><h2 id="session-list-title">咨询会话列表</h2><p>{{ filteredSessions.length }} 条本地会话</p></div>
          <span class="panel-count">{{ periodSessions.length }}</span>
        </div>
        <div class="session-filters">
          <label class="workspace-search">
            <Icon name="search" :size="16" />
            <input v-model="query" type="search" placeholder="搜索会话 ID / 医生" aria-label="搜索会话" />
          </label>
          <label class="visually-hidden" for="session-status-filter">按状态筛选</label>
          <select id="session-status-filter" v-model="statusFilter" aria-label="按状态筛选">
            <option value="all">全部状态</option>
            <option value="completed">已完成</option>
            <option value="evaluating">评估中</option>
            <option value="pending">待评估</option>
          </select>
        </div>
        <div class="session-list" aria-label="咨询会话">
          <button v-for="item in visibleSessions" :key="item.id" :class="['session-item', { selected: item.id === selectedId }]" type="button" :aria-pressed="item.id === selectedId" @click="selectSession(item.id)">
            <span class="session-item-top"><strong>{{ item.id }}</strong><span :class="['session-status', item.status]">{{ workspaceStatusText[item.status] }}</span></span>
            <span class="session-item-meta"><span>{{ item.doctor }}</span><time>{{ item.updatedAt }}</time></span>
            <span class="session-item-bottom"><span>{{ item.patient }}</span><span>{{ item.messages.length }} 条消息</span><Icon name="chevron" :size="14" /></span>
          </button>
          <div v-if="!visibleSessions.length" class="session-empty">
            <Icon name="search" :size="26" /><strong>没有找到匹配会话</strong><p>请尝试其他关键词或状态。</p><button type="button" @click="resetFilters">清除筛选</button>
          </div>
        </div>
        <footer class="session-pagination">
          <button type="button" aria-label="上一页" :disabled="currentPage === 1" @click="currentPage--"><Icon class="flip-icon" name="chevron" :size="15" /></button>
          <button v-for="pageNumber in totalPages" :key="pageNumber" type="button" :class="{ active: currentPage === pageNumber }" :aria-label="`第 ${pageNumber} 页`" :aria-current="currentPage === pageNumber ? 'page' : undefined" @click="currentPage = pageNumber">{{ pageNumber }}</button>
          <button type="button" aria-label="下一页" :disabled="currentPage === totalPages" @click="currentPage++"><Icon name="chevron" :size="15" /></button>
        </footer>
      </section>

      <section class="workspace-panel conversation-panel" aria-labelledby="conversation-title">
        <div class="panel-title-row conversation-heading">
          <div><h2 id="conversation-title">本次咨询记录</h2><p>{{ selected.id }} · {{ selected.doctor }}</p></div>
          <div class="view-tabs" role="group" aria-label="记录视图">
            <button type="button" :class="{ active: viewMode === 'original' }" :aria-pressed="viewMode === 'original'" @click="viewMode = 'original'">原文</button>
            <button type="button" :class="{ active: viewMode === 'structured' }" :aria-pressed="viewMode === 'structured'" @click="viewMode = 'structured'">结构化</button>
          </div>
        </div>
        <div v-if="viewMode === 'original'" class="conversation-list" aria-live="polite">
          <article v-for="message in visibleMessages" :id="`workspace-${selected.id}-${message.id}`" :key="message.id" :class="['conversation-message', message.role, { highlighted: highlightedIds.includes(message.id) }]" tabindex="-1">
            <span class="message-avatar" aria-hidden="true">{{ message.role === 'doctor' ? '医' : '访' }}</span>
            <div class="message-content">
              <div class="message-meta"><strong>{{ message.role === 'doctor' ? selected.doctor : '来访者' }}</strong><time>{{ message.time }}</time></div>
              <p class="message-bubble">{{ message.content }}</p>
              <button v-if="message.evidence" class="evidence-tag" type="button" @click="locateEvidence(message.id)"><Icon name="link" :size="12" />证据 {{ message.evidence }}</button>
            </div>
          </article>
        </div>
        <div v-else class="structured-view">
          <table>
            <thead><tr><th>序号</th><th>角色</th><th>时间</th><th>消息内容</th></tr></thead>
            <tbody><tr v-for="(message, index) in selected.messages" :key="message.id"><td>{{ index + 1 }}</td><td>{{ message.role === 'doctor' ? '医生' : '来访者' }}</td><td>{{ message.time }}</td><td>{{ message.content }}</td></tr></tbody>
          </table>
        </div>
        <footer class="conversation-footer">
          <span>消息 {{ visibleMessages.length }} / {{ selected.messages.length }}</span>
          <button v-if="selected.messages.length > 6" type="button" @click="showAllMessages = !showAllMessages">{{ showAllMessages ? '收起消息' : '展开全部' }}<Icon name="chevron" :size="13" :class="{ 'rotate-icon': showAllMessages }" /></button>
          <span v-else><Icon name="check" :size="13" />记录已加载</span>
        </footer>
      </section>

      <section class="workspace-panel ai-panel" aria-labelledby="ai-results-title">
        <div class="panel-title-row">
          <div><h2 id="ai-results-title">AI 评价结果</h2><p>18 项服务质量指标</p></div>
          <span :class="['result-status', selected.status]"><Icon :name="selected.status === 'completed' ? 'check' : 'clock'" :size="13" />{{ workspaceStatusText[selected.status] }}</span>
        </div>
        <template v-if="selected.status !== 'pending'">
          <div class="score-summary">
            <div class="overall-score"><span class="score-icon"><Icon name="star" :size="25" /></span><span><small>综合得分</small><strong>{{ (selected.score * 20).toFixed(1) }}<em>/ 100</em></strong></span></div>
            <div class="score-conclusion"><strong>评价结论</strong><p>{{ selected.summary }}</p></div>
          </div>
          <div class="metric-toolbar">
            <strong>18 项评价指标 <span title="点击指标可查看评价依据并定位原文"><Icon name="info" :size="14" /></span></strong>
            <select v-model="metricFilter" aria-label="筛选评价指标"><option value="all">全部指标</option><option value="attention">重点关注（低于 4 分）</option></select>
          </div>
          <div class="metric-groups">
            <section v-for="group in visibleGroups" :key="group.id" :class="['metric-group', `group-${group.id.toLowerCase()}`]">
              <button class="metric-group-heading" type="button" :aria-expanded="!collapsedGroups.includes(group.id)" @click="toggleGroup(group.id)">
                <span class="group-icon"><Icon :name="group.icon" :size="16" /></span>
                <strong>{{ group.name }}<small>（{{ group.metrics.length }} 项）</small></strong>
                <b>{{ groupAverage(group) }}</b><Icon class="group-chevron" name="chevron" :size="14" />
              </button>
              <div v-show="!collapsedGroups.includes(group.id)" class="metric-grid">
                <button v-for="metric in group.metrics" :key="metric.code" :class="['metric-item', { active: activeMetric?.code === metric.code }]" type="button" :aria-pressed="activeMetric?.code === metric.code" @click="chooseMetric(metric)">
                  <span class="metric-code">{{ metric.code.replace('D', '') }}</span><span class="metric-name">{{ metric.name }}</span><strong :class="{ low: metric.score < 4 }">{{ metric.score.toFixed(1) }}</strong>
                </button>
              </div>
            </section>
            <div v-if="!visibleGroups.length" class="metric-empty">当前筛选下没有指标。<button type="button" @click="metricFilter = 'all'">查看全部</button></div>
          </div>
          <div v-if="activeMetric" class="metric-detail">
            <div><span>{{ activeMetric.code }}</span><strong>{{ activeMetric.name }}</strong><b>{{ activeMetric.score.toFixed(1) }}</b></div>
            <p>{{ activeMetric.rationale }}</p>
            <button type="button" @click="locateEvidence(activeMetric.evidenceId)"><Icon name="link" :size="13" />查看原文证据</button>
          </div>
          <footer class="result-footer"><span>预设合成结果，仅供界面演示</span><button type="button" @click="exportReport"><Icon name="download" :size="14" />导出</button></footer>
        </template>
        <div v-else class="result-empty">
          <span><Icon name="sparkle" :size="30" /></span><h3>等待开始评价</h3><p>当前会话已加载 {{ selected.messages.length }} 条消息。开始离线演示评估后，这里将展示 18 项指标及原文证据。</p><button class="workspace-button primary" type="button" :disabled="running" @click="startEvaluation"><Icon name="play" :size="15" />{{ running ? `评估中 ${progress}%` : '开始评估' }}</button>
        </div>
      </section>
    </div>
    <div v-else class="surface workspace-range-empty"><Icon name="calendar" :size="28" /><strong>所选时间范围内没有咨询会话</strong><p>调整顶栏日期范围后，列表和评价内容会同步更新。</p></div>
    <p class="workspace-data-note"><Icon name="info" :size="14" />本页全部内容为合成离线数据，未连接后端、未运行模型，不用于真实医疗或服务质量结论。</p>
  </div>
</template>

<style scoped src="../../styles/workspace.css"></style>

<!-- 环节：前端页面层；用途：按医生聚合历史评价，展示趋势、画像与确定性预警。 -->
<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { monitoringApi } from '../api/endpoints/monitoring'
import type { DoctorProfile, MonitoringList } from '../api/contracts/monitoring'
import { monitoringPreviewList, monitoringPreviewProfile } from '../data/monitoringPreview'
import Icon from '../components/base/Icon.vue'
import StatusBadge from '../components/base/StatusBadge.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import TrendChart from '../components/charts/TrendChart.vue'

const props = defineProps<{ mode: 'service' | 'preview'; refreshKey: string }>()

const DAYS = 180
const list = ref<MonitoringList | null>(null)
const profile = ref<DoctorProfile | null>(null)
const selected = ref('')
const loading = ref(false)
const profileLoading = ref(false)
const error = ref('')
let epoch = 0

const riskNames: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
  unknown: '风险未知',
}
const riskTones: Record<string, string> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
  unknown: 'warning',
}
const ruleNames: Record<string, string> = {
  latest_high_risk: '最近评价高风险',
  consecutive_risk_streak: '连续风险观察',
  score_decline: '总分连续下滑',
  persistent_dimension_gap: '维度持续短板',
  serious_service_risk_flag: '严重服务风险标记',
  review_backlog: '待复核积压',
}

async function load() {
  const token = ++epoch
  loading.value = true
  error.value = ''
  list.value = null
  profile.value = null
  try {
    const result = props.mode === 'preview' ? monitoringPreviewList() : await monitoringApi.doctors(DAYS)
    if (token !== epoch) return
    list.value = result
    selectDoctor(result.doctors[0]?.doctor_id || '')
  } catch (e) {
    if (token === epoch) error.value = (e as Error).message
  } finally {
    if (token === epoch) loading.value = false
  }
}

async function selectDoctor(doctorId: string) {
  if (!doctorId) return
  selected.value = doctorId
  profile.value = null
  profileLoading.value = true
  try {
    const result =
      props.mode === 'preview'
        ? monitoringPreviewProfile(doctorId)
        : await monitoringApi.profile(doctorId, DAYS)
    profile.value = result
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    profileLoading.value = false
  }
}

watch(() => [props.mode, props.refreshKey], load, { immediate: true })
onUnmounted(() => {
  epoch++
})

const doctors = computed(() => list.value?.doctors ?? [])
const hasTrend = computed(() => profile.value?.trend.some((p) => p.average !== null) ?? false)
const hasRadar = computed(() => profile.value?.dimensions.some((d) => d.average !== null) ?? false)
const excludedNote = computed(() =>
  list.value && list.value.excluded_missing_doctor_id > 0
    ? `另有 ${list.value.excluded_missing_doctor_id} 份报告因缺少医生标识未纳入画像。`
    : '',
)
const score100 = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${Math.round(value * 20)}`
const riskBadge = (level: string | null | undefined) =>
  level ? riskNames[level] : '—'
</script>

<template>
  <div class="profile-layout">
    <aside class="surface doctor-panel">
      <header class="doctor-panel-head">
        <h2>医生画像</h2>
        <span class="doctor-panel-meta">
          {{ list?.doctor_count ?? '—' }} 位医生 · 预警
          {{ list ? list.alert_counts.high + list.alert_counts.medium : '—' }} 条
        </span>
      </header>
      <p v-if="excludedNote" class="excluded-note">{{ excludedNote }}</p>
      <div v-if="loading" class="panel-state">正在读取医生画像…</div>
      <div v-else-if="error" class="panel-state">{{ error }}</div>
      <div v-else-if="!doctors.length" class="panel-state">
        近 {{ DAYS }} 天还没有可画像的医生。导入真实会话并完成评价后，画像与预警会自动生成。
      </div>
      <ul v-else class="doctor-list" role="list">
        <li v-for="doctor in doctors" :key="doctor.doctor_id">
          <button
            :class="['doctor-row', { active: doctor.doctor_id === selected }]"
            @click="selectDoctor(doctor.doctor_id)"
          >
            <span class="doctor-id">{{ doctor.doctor_id }}</span>
            <span class="doctor-latest">{{ score100(doctor.latest_score) }} 分</span>
            <StatusBadge
              :tone="
                doctor.alerts.some((a) => a.level === 'high')
                  ? 'danger'
                  : doctor.alerts.length
                    ? 'warning'
                    : 'neutral'
              "
            >
              {{ doctor.alerts.length ? `${doctor.alerts.length} 条预警` : '正常' }}
            </StatusBadge>
          </button>
        </li>
      </ul>
    </aside>

    <section v-if="profile" class="profile-main">
      <div class="surface profile-header">
        <div class="profile-identity">
          <h2>{{ profile.doctor_id }}</h2>
          <p>
            近 {{ profile.days }} 天 · {{ profile.counts.in_window }} 份报告 · 可计分
            {{ profile.counts.scored }} 份 · 待复核 {{ profile.counts.pending_review }} 份
          </p>
        </div>
        <dl class="profile-stats">
          <div>
            <dt>最近评分</dt>
            <dd>{{ profile.latest_score === null ? '—' : `${profile.latest_score} 分` }}</dd>
          </div>
          <div>
            <dt>平均总分</dt>
            <dd>{{ profile.average_total === null ? '—' : `${profile.average_total} 分` }}</dd>
          </div>
          <div>
            <dt>风险等级</dt>
            <dd>
              <StatusBadge :tone="profile.latest_risk ? riskTones[profile.latest_risk] : 'neutral'">
                {{ riskBadge(profile.latest_risk) }}
              </StatusBadge>
            </dd>
          </div>
          <div>
            <dt>确定性预警</dt>
            <dd>{{ profile.alerts.length }} 条</dd>
          </div>
        </dl>
      </div>

      <div v-if="profile.alerts.length" :class="['alert-panel', 'surface']" aria-label="确定性预警">
        <h3><Icon name="shield" :size="18" />确定性预警（{{ profile.policy_version }}）</h3>
        <ul role="list">
          <li v-for="alert in profile.alerts" :key="alert.rule_id" :class="['alert-card', alert.level]">
            <strong>{{ ruleNames[alert.rule_id] || alert.rule_id }}</strong>
            <p>{{ alert.message }}</p>
            <small v-if="alert.related_sessions.length">
              相关会话：{{ alert.related_sessions.join('、') }}
            </small>
          </li>
        </ul>
      </div>

      <div class="profile-charts">
        <div class="surface chart-card">
          <h3>总分趋势（近 {{ profile.days }} 天，满分 100）</h3>
          <TrendChart v-if="hasTrend" :trend="profile.trend" />
          <div v-else class="panel-state">
            近 {{ profile.days }} 天没有可信评分；初评分和待复核报告不进入趋势线。
          </div>
        </div>
        <div class="surface chart-card">
          <h3>六维画像</h3>
          <RadarChart v-if="hasRadar" :dimensions="profile.dimensions" />
          <div v-else class="panel-state">暂无维度评分。</div>
        </div>
      </div>

      <div class="surface sessions-card">
        <h3>评价记录</h3>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>会话</th>
                <th>总分（满分 100）</th>
                <th>风险</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="session in profile.sessions" :key="session.session_id || session.date">
                <td>{{ session.date }}</td>
                <td class="session-id">{{ session.session_id || '—' }}</td>
                <td>{{ score100(session.overall_score) }}</td>
                <td>{{ riskBadge(session.risk_level) }}</td>
                <td>
                  <StatusBadge :tone="session.review_required ? 'warning' : 'neutral'">
                    {{ session.review_required ? '待人工复核' : '已计分' }}
                  </StatusBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
    <section v-else-if="profileLoading" class="panel-state profile-placeholder">
      正在读取 {{ selected || '' }} 的画像…
    </section>
  </div>
</template>

<style scoped>
.profile-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.doctor-panel {
  position: sticky;
  top: 12px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.doctor-panel-head h2 {
  margin: 0;
  font-size: 17px;
}
.doctor-panel-meta {
  display: block;
  margin: 4px 0 12px;
  font-size: 12.5px;
  color: var(--muted);
}
.excluded-note {
  margin: 0 0 10px;
  padding: 8px 10px;
  font-size: 12.5px;
  color: var(--warning);
  background: var(--warning-bg);
  border-radius: 6px;
}
.panel-state {
  padding: 26px 10px;
  font-size: 13.5px;
  color: var(--muted);
  text-align: center;
}
.profile-placeholder {
  grid-column: 2;
  background: var(--paper);
  border: 1px dashed var(--line);
  border-radius: 10px;
}
.doctor-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
  max-height: 60vh;
  overflow-y: auto;
}
.doctor-row {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  font: inherit;
  color: var(--ink);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
}
.doctor-row:hover {
  background: var(--teal-light);
}
.doctor-row.active {
  border-color: var(--teal);
  background: var(--teal-light);
}
.doctor-id {
  flex: 1;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.doctor-latest {
  font-size: 13px;
  color: var(--muted);
}
.profile-main {
  display: grid;
  gap: 18px;
  min-width: 0;
}
.profile-header {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.profile-identity h2 {
  margin: 0 0 4px;
  font-size: 18px;
}
.profile-identity p {
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
}
.profile-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  margin: 0;
}
.profile-stats dt {
  font-size: 12px;
  color: var(--muted);
}
.profile-stats dd {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 700;
}
.alert-panel {
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-left: 4px solid var(--danger);
  border-radius: 10px;
}
.alert-panel h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 14.5px;
  color: var(--danger);
}
.alert-panel ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}
.alert-card {
  padding: 10px 12px;
  border-radius: 8px;
}
.alert-card.high {
  background: var(--danger-bg);
  border: 1px solid #f0d4d7;
}
.alert-card.medium {
  background: var(--warning-bg);
  border: 1px solid #efe3c8;
}
.alert-card strong {
  font-size: 13.5px;
}
.alert-card p {
  margin: 4px 0 2px;
  font-size: 13px;
  line-height: 1.55;
}
.alert-card small {
  font-size: 12px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.profile-charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 18px;
}
.chart-card {
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.chart-card h3,
.sessions-card h3 {
  margin: 0 0 12px;
  font-size: 14.5px;
}
.sessions-card {
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.table-scroll {
  overflow-x: auto;
}
.sessions-card table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.sessions-card th,
.sessions-card td {
  padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--line);
}
.sessions-card th {
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
}
.session-id {
  max-width: 220px;
  overflow-wrap: anywhere;
  color: var(--muted);
}
@media (max-width: 960px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
  .doctor-panel {
    position: static;
  }
  .doctor-list {
    max-height: 40vh;
  }
}
</style>

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
import { rangeDayCount, useDateRange } from '../composables/dateRange'

const props = defineProps<{ mode: 'service' | 'preview'; refreshKey: string }>()

const dateRange = useDateRange()
const rangeDays = computed(() => rangeDayCount(dateRange.value))
const list = ref<MonitoringList | null>(null)
const profile = ref<DoctorProfile | null>(null)
const selected = ref('')
const loading = ref(false)
const profileLoading = ref(false)
const error = ref('')
const profileError = ref('')
const doctorQuery = ref('')
const doctorListCollapsed = ref(false)
let epoch = 0
let profileEpoch = 0

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
  profileEpoch++
  loading.value = true
  error.value = ''
  profileError.value = ''
  doctorQuery.value = ''
  list.value = null
  profile.value = null
  try {
    const result = props.mode === 'preview'
      ? monitoringPreviewList(dateRange.value.start, dateRange.value.end)
      : await monitoringApi.doctors(dateRange.value.start, dateRange.value.end)
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
  const token = ++profileEpoch
  selected.value = doctorId
  profile.value = null
  profileError.value = ''
  profileLoading.value = true
  try {
    const result =
      props.mode === 'preview'
        ? monitoringPreviewProfile(doctorId, dateRange.value.start, dateRange.value.end)
        : await monitoringApi.profile(doctorId, dateRange.value.start, dateRange.value.end)
    if (token === profileEpoch) profile.value = result
  } catch (e) {
    if (token === profileEpoch) profileError.value = (e as Error).message
  } finally {
    if (token === profileEpoch) profileLoading.value = false
  }
}

watch(() => [props.mode, props.refreshKey, dateRange.value.start, dateRange.value.end], load, { immediate: true })
onUnmounted(() => {
  epoch++
  profileEpoch++
})

const doctors = computed(() => list.value?.doctors ?? [])
const filteredDoctors = computed(() => {
  const keyword = doctorQuery.value.trim().toLowerCase()
  return doctors.value.filter((doctor) => doctor.doctor_id.toLowerCase().includes(keyword))
})
const hasTrend = computed(() => profile.value?.trend.some((p) => p.average !== null) ?? false)
const hasRadar = computed(() => profile.value?.dimensions.some((d) => d.average !== null) ?? false)
const profileDimensions = computed(() => {
  const names: Record<string, string> = {
    D1: '服务可靠性',
    D2: '服务响应性',
    D3: '专业信息沟通',
    D4: '情感共情性',
    D5: '咨询协作性',
    D6: '心理风险应对',
  }
  return (profile.value?.dimensions ?? []).map((dimension) => ({
    ...dimension,
    name:
      dimension.name && dimension.name !== dimension.dimension_id
        ? dimension.name
        : names[dimension.dimension_id] || dimension.dimension_id,
  }))
})
const alertGroups = computed(() =>
  (['high', 'medium'] as const)
    .map((level) => ({
      level,
      title: level === 'high' ? '高风险重点关注' : '中风险持续观察',
      alerts: profile.value?.alerts.filter((alert) => alert.level === level) ?? [],
    }))
    .filter((group) => group.alerts.length),
)
const alertCounts = computed(() => ({
  high: profile.value?.alerts.filter((alert) => alert.level === 'high').length ?? 0,
  medium: profile.value?.alerts.filter((alert) => alert.level === 'medium').length ?? 0,
}))
const scoreCoverage = computed(() => {
  if (!profile.value?.counts.in_window) return '0%'
  return `${Math.round((profile.value.counts.scored / profile.value.counts.in_window) * 100)}%`
})
const excludedNote = computed(() =>
  list.value && list.value.excluded_missing_doctor_id > 0
    ? `另有 ${list.value.excluded_missing_doctor_id} 份报告因缺少医生标识未纳入画像。`
    : '',
)
const score100 = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${Math.round(value)}`
const scoreText = (value: number | null | undefined) =>
  value === null || value === undefined
    ? '—'
    : Number.isInteger(value)
      ? `${value}`
      : value.toFixed(1)
const riskBadge = (level: string | null | undefined) =>
  level ? riskNames[level] : '—'
const doctorTone = (doctor: MonitoringList['doctors'][number]) =>
  doctor.latest_risk === 'high' || doctor.alerts.some((alert) => alert.level === 'high')
    ? 'danger'
    : doctor.latest_risk === 'medium' || doctor.alerts.some((alert) => alert.level === 'medium')
      ? 'warning'
      : doctor.latest_risk === 'unknown'
        ? 'warning'
        : doctor.latest_risk === 'low'
          ? 'success'
          : 'neutral'
</script>

<template>
  <div :class="['profile-layout', { 'doctor-list-collapsed': doctorListCollapsed }]">
    <aside :class="['surface', 'doctor-panel', { collapsed: doctorListCollapsed }]">
      <button
        v-if="doctorListCollapsed"
        class="doctor-panel-toggle doctor-panel-toggle-collapsed"
        type="button"
        aria-label="展开医生列表"
        title="展开医生列表"
        :aria-expanded="false"
        @click="doctorListCollapsed = false"
      >
        <Icon name="arrow" :size="18" />
      </button>
      <div v-else class="doctor-panel-content">
        <header class="doctor-panel-head">
          <div>
            <h2>医生列表</h2>
            <p class="doctor-panel-meta">{{ rangeDays }} 天 · {{ list?.doctor_count ?? '—' }} 位医生</p>
          </div>
          <div class="doctor-panel-actions">
            <span class="doctor-alert-count"><Icon name="alert" :size="15" />{{ list ? list.alert_counts.high + list.alert_counts.medium : '—' }} 条预警</span>
            <button
              class="doctor-panel-toggle"
              type="button"
              aria-label="收起医生列表"
              title="收起医生列表"
              :aria-expanded="true"
              @click="doctorListCollapsed = true"
            >
              <Icon name="arrow" :size="16" />
            </button>
          </div>
        </header>
        <p v-if="excludedNote" class="excluded-note">{{ excludedNote }}</p>
        <label v-if="!loading && doctors.length" class="doctor-search">
          <Icon name="search" :size="17" />
          <input v-model="doctorQuery" type="search" aria-label="搜索医生" placeholder="搜索医生 ID…" />
        </label>
        <div v-if="loading" class="panel-state">正在读取医生画像…</div>
        <div v-else-if="error" class="panel-state" role="alert">{{ error }}</div>
        <div v-else-if="!doctors.length" class="panel-state">
          所选日期范围内没有可画像的医生。调整顶栏日期范围，或导入真实会话并完成评价。
        </div>
        <ul v-else class="doctor-list" role="list">
          <li v-for="doctor in filteredDoctors" :key="doctor.doctor_id">
            <button
              :class="['doctor-row', { active: doctor.doctor_id === selected }]"
              :aria-pressed="doctor.doctor_id === selected"
              @click="selectDoctor(doctor.doctor_id)"
            >
              <span class="doctor-avatar"><Icon name="user" :size="19" /></span>
              <span class="doctor-copy">
                <strong>{{ doctor.doctor_id }}</strong>
                <small>评价 {{ doctor.session_count }} 次 · 均分 {{ score100(doctor.average_total) }}</small>
              </span>
              <span class="doctor-row-end">
                <StatusBadge :tone="doctorTone(doctor)">{{ riskBadge(doctor.latest_risk) }}</StatusBadge>
                <small>最新 {{ score100(doctor.latest_score) }}</small>
              </span>
            </button>
          </li>
          <li v-if="filteredDoctors.length === 0" class="doctor-empty">没有匹配的医生，请调整搜索词。</li>
        </ul>
      </div>
    </aside>

    <section v-if="profile" class="profile-main">
      <header class="surface profile-header">
        <div class="profile-identity">
          <span class="profile-avatar"><Icon name="user" :size="30" /></span>
          <div>
            <span class="profile-kicker">医生画像对象</span>
            <h2>doctor id: {{ profile.doctor_id }}</h2>
            <p>近 {{ profile.days }} 天 · {{ profile.period_start }} 至 {{ profile.period_end }}</p>
          </div>
        </div>
        <dl class="profile-stats" aria-label="医生评价摘要">
          <div class="profile-stat jade">
            <dt><Icon name="message" :size="17" />累计评价</dt>
            <dd>{{ profile.counts.in_window }}<small>次</small></dd>
            <p>近 {{ profile.days }} 天</p>
          </div>
          <div class="profile-stat amber">
            <dt><Icon name="star" :size="17" />最近评分</dt>
            <dd>{{ scoreText(profile.latest_score) }}<small>/ 100</small></dd>
            <p>{{ profile.latest_date || '暂无评分' }}</p>
          </div>
          <div class="profile-stat jade">
            <dt><Icon name="medal" :size="17" />平均总分</dt>
            <dd>{{ scoreText(profile.average_total) }}<small>/ 100</small></dd>
            <p>{{ profile.counts.scored }} 份有效评分</p>
          </div>
          <div class="profile-stat rose">
            <dt><Icon name="alert" :size="17" />风险预警</dt>
            <dd>{{ profile.alerts.length }}<small>条</small></dd>
            <p>高 {{ alertCounts.high }} · 中 {{ alertCounts.medium }}</p>
          </div>
          <div class="profile-stat mint">
            <dt><Icon name="check" :size="17" />有效评价</dt>
            <dd>{{ profile.counts.scored }}<small>份</small></dd>
            <p>占窗口内 {{ scoreCoverage }}</p>
          </div>
        </dl>
      </header>

      <div class="profile-analysis">
        <div class="profile-analysis-main">
          <section :class="['surface', 'alert-panel', { 'has-high-alert': alertCounts.high > 0, 'no-alert': profile.alerts.length === 0 }]" aria-labelledby="profile-alert-title">
            <header class="section-heading">
              <div>
                <h3 id="profile-alert-title"><Icon name="shield" :size="19" />风险预警与结论</h3>
                <p>确定性规则 · {{ profile.policy_version }}<span v-if="profile.latest_date"> · 最近一次评价 {{ profile.latest_date }}</span></p>
              </div>
              <StatusBadge :tone="profile.alerts.length ? (alertCounts.high ? 'danger' : 'warning') : 'success'">
                {{ profile.alerts.length ? `${profile.alerts.length} 条待关注` : '暂无触发' }}
              </StatusBadge>
            </header>
            <div v-if="alertGroups.length" class="alert-groups">
              <section v-for="group in alertGroups" :key="group.level" :class="['alert-group', group.level]">
                <h4>{{ group.title }}<span>{{ group.alerts.length }}</span></h4>
                <ul role="list">
                  <li v-for="alert in group.alerts" :key="alert.rule_id" class="alert-item">
                    <strong>{{ ruleNames[alert.rule_id] || alert.rule_id }}</strong>
                    <p>{{ alert.message }}</p>
                    <small v-if="alert.related_sessions.length">相关会话：{{ alert.related_sessions.join('、') }}</small>
                  </li>
                </ul>
              </section>
            </div>
            <div v-else class="alert-clear">
              <span><Icon name="check" :size="19" /></span>
              <div><strong>当前周期未触发确定性预警</strong><p>这表示现有监测规则未发现需提示的服务质量信号。</p></div>
            </div>
            <p class="alert-footnote">预警依据服务质量监测规则生成，不代表患者临床风险等级；正式判断请结合会话原文和适用规则。</p>
          </section>

          <section class="surface chart-card profile-trend-card" aria-labelledby="profile-trend-title">
            <header class="section-heading chart-heading">
              <div>
                <h3 id="profile-trend-title">总分趋势</h3>
                <p>近 {{ profile.days }} 天 · 满分 100 分</p>
              </div>
              <span class="chart-period"><Icon name="calendar" :size="15" />{{ profile.period_start }} — {{ profile.period_end }}</span>
            </header>
            <TrendChart v-if="hasTrend" :trend="profile.trend" />
            <div v-else class="panel-state chart-empty">
              近 {{ profile.days }} 天没有可信评分；初评分和待复核报告不进入趋势线。
            </div>
          </section>
        </div>

        <section class="surface chart-card profile-radar-card" aria-labelledby="profile-radar-title">
          <header class="section-heading chart-heading">
            <div>
              <h3 id="profile-radar-title">六维服务画像</h3>
              <p>各维度平均分 · 满分 5 分</p>
            </div>
            <span class="radar-legend"><i />本期</span>
          </header>
          <RadarChart v-if="hasRadar" :dimensions="profileDimensions" scale="five" :axis-labels="true" />
          <div v-else class="panel-state chart-empty">暂无维度评分。</div>
          <div v-if="hasRadar" class="dimension-summary" aria-label="维度评分详情">
            <div v-for="dimension in profileDimensions" :key="dimension.dimension_id" class="dimension-summary-row">
              <span>{{ dimension.name }}</span>
              <i><b :style="{ width: `${dimension.average ?? 0}%` }" /></i>
              <strong>{{ dimension.average === null ? '—' : (dimension.average / 20).toFixed(1) }}</strong>
            </div>
          </div>
        </section>
      </div>

      <section class="surface sessions-card" aria-labelledby="profile-sessions-title">
        <header class="section-heading sessions-heading">
          <div>
            <h3 id="profile-sessions-title">最近评价记录</h3>
            <p>{{ profile.sessions.length }} 条记录 · 近 {{ profile.days }} 天</p>
          </div>
          <span class="records-count">{{ profile.sessions.length }} 条</span>
        </header>
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
                <td>{{ session.overall_score === null ? '—' : (session.overall_score * 20).toFixed(1) }}</td>
                <td>
                  <StatusBadge :tone="session.risk_level ? riskTones[session.risk_level] : 'neutral'">
                    {{ riskBadge(session.risk_level) }}
                  </StatusBadge>
                </td>
                <td>
                  <StatusBadge :tone="session.review_required ? 'warning' : 'neutral'">
                    {{ session.review_required ? '待人工复核' : '已计分' }}
                  </StatusBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!profile.sessions.length" class="records-empty">当前周期暂无评价记录。</p>
      </section>
    </section>
    <section v-else class="panel-state profile-placeholder" role="status">
      <template v-if="profileLoading">正在读取 {{ selected || '' }} 的画像…</template>
      <template v-else-if="profileError">
        <span>{{ profileError }}</span>
        <button class="retry-profile" type="button" @click="selectDoctor(selected)">重新加载画像</button>
      </template>
      <template v-else>从左侧选择一位医生查看服务质量画像。</template>
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
  font-size: 18.5px;
}
.doctor-panel-meta {
  display: block;
  margin: 4px 0 12px;
  font-size: 14px;
  color: var(--muted);
}
.excluded-note {
  margin: 0 0 10px;
  padding: 8px 10px;
  font-size: 14px;
  color: var(--warning);
  background: var(--warning-bg);
  border-radius: 6px;
}
.panel-state {
  padding: 26px 10px;
  font-size: 15px;
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
  font-size: 14.5px;
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
  font-size: 19.5px;
}
.profile-identity p {
  margin: 0;
  font-size: 14px;
  color: var(--muted);
}
.profile-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  margin: 0;
}
.profile-stats dt {
  font-size: 13.5px;
  color: var(--muted);
}
.profile-stats dd {
  margin: 2px 0 0;
  font-size: 17.5px;
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
  font-size: 16px;
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
  font-size: 15px;
}
.alert-card p {
  margin: 4px 0 2px;
  font-size: 14.5px;
  line-height: 1.55;
}
.alert-card small {
  font-size: 13.5px;
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
  font-size: 16px;
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
  font-size: 14.5px;
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

/* The shared content area is the responsive reference because the sidebar reduces its width. */
:global(main.profile-page-shell) {
  container-name: profile-page;
  container-type: inline-size;
}
.profile-layout {
  grid-template-columns: minmax(230px, 0.28fr) minmax(0, 0.72fr);
  gap: clamp(16px, 1.35vw, 22px);
  min-width: 0;
  color: var(--ink);
  transition: grid-template-columns 220ms ease;
}
.doctor-panel,
.profile-header,
.alert-panel,
.chart-card,
.sessions-card,
.profile-placeholder {
  border: 1px solid rgba(219, 232, 223, 0.95);
  border-radius: 17px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 16px 38px -34px rgba(26, 75, 49, 0.45);
}
.doctor-panel {
  top: 14px;
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 112px);
  min-height: 360px;
  padding: 18px;
}
.doctor-panel-content {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.doctor-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.doctor-panel-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}
.doctor-panel-toggle {
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #dceae0;
  border-radius: 10px;
  background: #f5faf6;
  color: #47775b;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease, transform 220ms ease;
}
.doctor-panel-toggle:hover {
  background: #e8f5eb;
  color: #176d4c;
}
.doctor-panel-toggle svg { transform: rotate(180deg); }
.doctor-panel-toggle-collapsed svg { transform: none; }
.doctor-panel-head h2 { margin: 0; font-size: 20px; }
.doctor-panel-meta {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 14px;
}
.doctor-alert-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 37px;
  height: 32px;
  justify-content: center;
  padding: 0 9px;
  border-radius: 999px;
  background: #fff0e3;
  color: #a96822;
  font-size: 14px;
  font-weight: 700;
}
.doctor-search {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 44px;
  padding: 0 12px;
  margin: 14px 0 12px;
  border: 1px solid #e0eae2;
  border-radius: 11px;
  background: #f9fbf9;
  color: #7b9082;
}
.doctor-search:focus-within { border-color: #80b999; background: #fff; }
.doctor-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 14px;
}
.doctor-search input::placeholder { color: #8b9a90; }
.excluded-note {
  margin: 0 0 10px;
  padding: 10px 11px;
  border: 1px solid #f0e0bf;
  border-radius: 10px;
  color: #8c6726;
  font-size: 13.5px;
  line-height: 1.55;
}
.doctor-list {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  margin: 0 -4px -4px;
  padding: 0 4px 4px;
  gap: 7px;
  scrollbar-width: thin;
  scrollbar-color: #c9dbce transparent;
}
.doctor-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 72px;
  padding: 10px;
  border-color: #edf2ee;
  border-radius: 12px;
  transition: background 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
.doctor-row:hover { background: #f5faf6; }
.doctor-row.active {
  border-color: #b9dcc6;
  background: linear-gradient(105deg, #e9f6ed, #f8fbf8);
  box-shadow: inset 3px 0 #219266;
}
.doctor-avatar,
.profile-avatar {
  display: grid;
  place-items: center;
  flex: none;
  border-radius: 50%;
  background: linear-gradient(145deg, #edf5ff, #d7e7fb);
  color: #376aa3;
}
.doctor-avatar { width: 40px; height: 40px; }
.doctor-copy { display: grid; align-content: center; gap: 5px; min-width: 0; }
.doctor-copy strong {
  overflow: hidden;
  color: #20352a;
  font-size: 15.5px;
  text-overflow: ellipsis;
}
.doctor-copy small,
.doctor-row-end small {
  color: var(--muted);
  font-size: 13.5px;
  white-space: nowrap;
}
.doctor-row-end {
  display: grid;
  justify-items: end;
  align-content: center;
  gap: 5px;
}
.doctor-row-end .status-badge { font-size: 13px; }
.doctor-empty { padding: 18px 8px; color: var(--muted); font-size: 14px; text-align: center; }
.panel-state { padding: 32px 16px; font-size: 15px; line-height: 1.7; }
.profile-main { gap: 16px; }
.profile-header {
  display: grid;
  grid-template-columns: minmax(190px, 0.78fr) minmax(0, 2.22fr);
  align-items: center;
  gap: 18px;
  padding: 18px;
  background: linear-gradient(110deg, rgba(255,255,255,0.97), rgba(245,251,246,0.97));
}
.profile-identity { display: flex; align-items: center; gap: 14px; min-width: 0; }
.profile-avatar {
  width: 62px;
  height: 62px;
  background: linear-gradient(145deg, #e8f4ec, #d1e8d8);
  color: #257d56;
}
.profile-kicker { display: block; margin-bottom: 5px; color: #718579; font-size: 13.5px; }
.profile-identity h2 {
  margin: 0 0 5px;
  color: #19372b;
  font-family: 'Segoe UI', sans-serif;
  font-size: 21px;
  overflow-wrap: anywhere;
}
.profile-identity p { margin: 0; color: var(--muted); font-size: 13.5px; }
.profile-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 9px;
  min-width: 0;
  margin: 0;
}
.profile-stat {
  min-width: 0;
  min-height: 98px;
  padding: 11px 12px;
  border: 1px solid transparent;
  border-radius: 12px;
}
.profile-stat.jade { background: #f0f8f2; border-color: #e2f0e5; }
.profile-stat.amber { background: #fff8eb; border-color: #f6ecd5; }
.profile-stat.rose { background: #fff3f2; border-color: #f5e4e2; }
.profile-stat.mint { background: #eef8f5; border-color: #e0f0eb; }
.profile-stat dt { display: flex; align-items: center; gap: 6px; color: #607469; font-size: 13.5px; white-space: nowrap; }
.profile-stat.jade dt svg,
.profile-stat.mint dt svg { color: #249267; }
.profile-stat.amber dt svg { color: #d19a35; }
.profile-stat.rose dt svg { color: #ce6870; }
.profile-stat dd {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin: 5px 0 0;
  color: #182e24;
  font-family: 'Segoe UI', sans-serif;
  font-size: 25px;
  font-weight: 750;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.profile-stat dd small { color: #6d8175; font-family: inherit; font-size: 13px; font-weight: 550; }
.profile-stat p { overflow: hidden; margin: 4px 0 0; color: #728579; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.profile-analysis {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  min-width: 0;
}
.profile-analysis-main { display: grid; gap: 16px; min-width: 0; }
.alert-panel,
.chart-card,
.sessions-card { min-width: 0; padding: 18px; }
.alert-panel { border-left: 4px solid #dca34e; }
.alert-panel.has-high-alert { border-left-color: #d56e72; }
.alert-panel.no-alert { border-left-color: #43a778; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; min-width: 0; }
.section-heading h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #21382b;
  font-size: 18px;
  line-height: 1.35;
}
.section-heading > div > p { margin: 5px 0 0; color: var(--muted); font-size: 13.5px; line-height: 1.5; }
.alert-panel .section-heading h3 svg { color: #b58037; }
.alert-panel.has-high-alert .section-heading h3 svg { color: #be555d; }
.alert-panel.no-alert .section-heading h3 svg { color: #24895e; }
.alert-panel .section-heading > .status-badge { flex: none; margin-top: 1px; }
.alert-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 15px; }
.alert-group { min-width: 0; padding: 12px; border: 1px solid transparent; border-radius: 12px; }
.alert-group.high { background: #fff3f2; border-color: #f4e0df; }
.alert-group.medium { background: #fff8eb; border-color: #f3e9d3; }
.alert-group h4 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; color: #ae5057; font-size: 15px; }
.alert-group.medium h4 { color: #9f7226; }
.alert-group h4 span { display: grid; place-items: center; min-width: 22px; height: 22px; padding: 0 5px; border-radius: 99px; background: #fff; font-size: 13px; }
.alert-group ul { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }
.alert-item { padding-top: 8px; border-top: 1px solid rgba(137, 105, 75, 0.12); }
.alert-item:first-child { padding-top: 0; border-top: 0; }
.alert-item strong { color: #564940; font-size: 14px; line-height: 1.5; }
.alert-item p { margin: 3px 0; color: #65766a; font-size: 13.5px; line-height: 1.6; overflow-wrap: anywhere; }
.alert-item small { color: #7d8980; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.alert-clear { display: flex; align-items: center; gap: 12px; margin-top: 15px; padding: 17px; border: 1px solid #dcefe3; border-radius: 12px; background: #f1f9f3; }
.alert-clear > span { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: #dcf1e4; color: #228b5e; }
.alert-clear strong { color: #286448; font-size: 15px; }
.alert-clear p { margin: 4px 0 0; color: #718579; font-size: 13.5px; line-height: 1.55; }
.alert-footnote { margin: 12px 0 0; color: #79887f; font-size: 13.5px; line-height: 1.6; }
.profile-trend-card,
.profile-radar-card { display: flex; flex-direction: column; }
.chart-heading { align-items: center; margin-bottom: 10px; }
.chart-heading h3 { margin: 0; }
.chart-period { display: inline-flex; align-items: center; gap: 6px; flex: none; color: #72857a; font-size: 13.5px; white-space: nowrap; }
.chart-period svg { color: #54856a; }
.profile-trend-card :deep(.trend-area) { min-height: 275px; padding: 8px 2px 0; overflow-x: auto; }
.profile-trend-card :deep(.trend-chart) { min-width: 540px; min-height: 245px; }
.profile-trend-card :deep(.chart-legend) { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 7px; font-size: 13.5px; }
.profile-trend-card :deep(.chart-caption) { margin: 7px 0 0; font-size: 13.5px; }
.chart-empty { display: grid; flex: 1; place-items: center; min-height: 210px; }
.profile-radar-card { width: 100%; min-height: 510px; align-self: start; }
.profile-radar-card :deep(.radar-area) { flex: none; min-height: 0; grid-template-rows: auto auto; padding: 5px 0 0; }
.profile-radar-card :deep(.radar-shell) { width: min(100%, 440px); height: auto; max-width: 440px; max-height: none; aspect-ratio: 1; }
.profile-radar-card :deep(.radar-chart) { width: 100%; height: 100%; }
.profile-radar-card :deep(.radar-chip-icon) { width: 32px; height: 32px; }
.profile-radar-card :deep(.radar-chip-name) { color: #61786b; font-size: 14px; }
.profile-radar-card :deep(.radar-chip strong) { font-size: 17.5px; }
.profile-radar-card :deep(.chart-caption) { margin: 3px 0 10px; color: #74877b; font-size: 13.5px; }
@container radar-area (max-width: 480px) {
  .profile-radar-card :deep(.radar-shell) { width: 100%; max-width: none; aspect-ratio: auto; }
  .profile-radar-card :deep(.radar-chart) { width: min(100%, 300px); height: auto; }
}
.radar-legend { display: inline-flex; align-items: center; gap: 7px; color: #65796d; font-size: 13.5px; white-space: nowrap; }
.radar-legend i { width: 8px; height: 8px; border-radius: 50%; background: #239566; }
.dimension-summary { display: grid; gap: 3px; margin-top: 8px; padding-top: 9px; border-top: 1px solid #edf2ee; }
.dimension-summary-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(48px, 0.65fr) 34px; align-items: center; gap: 9px; min-height: 27px; color: #62756a; font-size: 13.5px; }
.dimension-summary-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dimension-summary-row > i { display: block; height: 5px; overflow: hidden; border-radius: 99px; background: #e8f0ea; }
.dimension-summary-row > i b { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #72c5a0, #218d63); }
.dimension-summary-row > strong { color: #274735; font-family: 'Segoe UI', sans-serif; font-size: 13.5px; text-align: right; font-variant-numeric: tabular-nums; }
.sessions-card { padding-bottom: 12px; }
.sessions-heading { align-items: center; margin-bottom: 12px; }
.sessions-heading h3 { margin: 0; }
.records-count { flex: none; padding: 5px 10px; border-radius: 99px; background: #eff7f1; color: #4f7860; font-size: 13.5px; }
.table-scroll { overflow-x: auto; border: 1px solid #e9efea; border-radius: 11px; }
.sessions-card table { min-width: 640px; width: 100%; border-collapse: collapse; font-size: 14px; }
.sessions-card th,
.sessions-card td { padding: 11px 13px; text-align: left; border-bottom: 1px solid #edf2ee; white-space: nowrap; }
.sessions-card th { background: #f5f8f5; color: #62766a; font-size: 13.5px; font-weight: 650; }
.sessions-card tbody tr:last-child td { border-bottom: 0; }
.sessions-card tbody tr:hover { background: #f8fbf8; }
.sessions-card td { color: #4e6455; }
.session-id { max-width: 250px; overflow: hidden; color: #66796d; text-overflow: ellipsis; }
.records-empty { padding: 20px; color: var(--muted); font-size: 14px; text-align: center; }
.profile-placeholder { grid-column: 2; min-height: 260px; display: grid; place-content: center; gap: 14px; }
.retry-profile { justify-self: center; padding: 8px 14px; border: 1px solid #b9d8c2; border-radius: 9px; background: #f0f8f2; color: #246945; font: inherit; font-size: 14px; cursor: pointer; }
.retry-profile:hover { background: #e2f2e6; }

@container profile-page (min-width: 1200px) {
  .profile-analysis { grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.95fr); }
  .profile-radar-card { min-height: 0; }
  .profile-radar-card :deep(.radar-area) { min-height: 370px; }
}
@container profile-page (min-width: 900px) and (max-width: 1199px) {
  .profile-header { grid-template-columns: minmax(0, 1fr); }
  .profile-stats { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .profile-analysis { grid-template-columns: minmax(0, 1fr); }
  .profile-radar-card { min-height: 620px; }
  .profile-radar-card :deep(.radar-area) { min-height: 400px; }
  .profile-placeholder { grid-column: 2; }
}
@container profile-page (max-width: 899px) {
  .profile-layout { grid-template-columns: minmax(0, 1fr); }
  .doctor-panel { position: static; max-height: none; min-height: 0; }
  .doctor-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 285px), 1fr)); max-height: min(390px, 46dvh); }
  .profile-placeholder { grid-column: auto; }
  .profile-header { grid-template-columns: minmax(0, 1fr); }
  .profile-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .profile-analysis { grid-template-columns: minmax(0, 1fr); }
  .profile-radar-card { min-height: 600px; }
}
@container profile-page (max-width: 560px) {
  .doctor-panel { padding: 14px; }
  .doctor-row { grid-template-columns: 38px minmax(0, 1fr); }
  .doctor-avatar { width: 36px; height: 36px; }
  .doctor-row-end { grid-column: 2; grid-template-columns: auto 1fr; justify-items: start; align-items: center; }
  .doctor-row-end small { justify-self: end; }
  .profile-header,
  .alert-panel,
  .chart-card,
  .sessions-card { padding: 14px; }
  .profile-avatar { width: 50px; height: 50px; }
  .profile-identity h2 { font-size: 18px; }
  .profile-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .profile-stat { min-height: 92px; }
  .alert-groups { grid-template-columns: minmax(0, 1fr); }
  .section-heading { align-items: flex-start; }
  .chart-period { white-space: normal; text-align: right; }
  .profile-radar-card { min-height: 0; }
  .profile-radar-card :deep(.radar-area) { min-height: 310px; }
  .profile-radar-card :deep(.radar-chip) { gap: 5px; }
  .profile-radar-card :deep(.radar-chip-icon) { width: 27px; height: 27px; }
  .profile-radar-card :deep(.radar-chip-name) { font-size: 13px; }
  .profile-radar-card :deep(.radar-chip strong) { font-size: 15px; }
  .profile-trend-card :deep(.trend-area) { min-height: 260px; }
  .profile-trend-card :deep(.trend-chart) { min-width: 500px; }
}
.profile-layout.doctor-list-collapsed {
  grid-template-columns: 56px minmax(0, 1fr);
}
.doctor-panel.collapsed {
  display: grid;
  place-items: start center;
  width: 56px;
  height: 56px;
  min-height: 56px;
  padding: 9px;
  overflow: hidden;
}
.doctor-panel-toggle-collapsed {
  width: 36px;
  height: 36px;
  border-radius: 11px;
}
@container profile-page (max-width: 899px) {
  .profile-layout.doctor-list-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
  .doctor-panel.collapsed {
    width: 100%;
    height: 54px;
    min-height: 54px;
    place-items: center start;
  }
  .doctor-panel-toggle-collapsed {
    width: 100%;
    place-items: center start;
    padding-inline: 12px;
  }
}
</style>

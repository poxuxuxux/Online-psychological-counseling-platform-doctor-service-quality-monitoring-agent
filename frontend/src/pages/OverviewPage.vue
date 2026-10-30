<!-- 环节：前端页面层；用途：实现独立业务页面及其数据呈现。 -->
<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { request } from '../api/client/http'
import { OverviewSchema, type Overview } from '../api/contracts/overview'
import { overviewPreviewRange } from '../data/overviewPreview'
import { rangeDayCount, useDateRange } from '../composables/dateRange'
import Icon from '../components/base/Icon.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import TrendChart from '../components/charts/TrendChart.vue'
import overviewHero from '../assets/consultation-room.png'
const emit = defineEmits<{ navigate: [page: 'workspace' | 'rubrics' | 'review'] }>()
const props = defineProps<{ mode: 'service' | 'preview'; refreshKey: string }>()
const dateRange = useDateRange()
const days = computed(() => rangeDayCount(dateRange.value))
const loading = ref(false),
  error = ref(''),
  data = ref<Overview | null>(null)
let epoch = 0
async function load() {
  const token = ++epoch
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const result =
      props.mode === 'preview'
        ? overviewPreviewRange(dateRange.value.start, dateRange.value.end)
        : await request(
            `/api/v1/evaluations/overview?start_date=${encodeURIComponent(dateRange.value.start)}&end_date=${encodeURIComponent(dateRange.value.end)}`,
            OverviewSchema,
          )
    if (token === epoch) data.value = result
  } catch (e) {
    if (token === epoch) error.value = (e as Error).message
  } finally {
    if (token === epoch) loading.value = false
  }
}
watch(() => [props.mode, props.refreshKey, dateRange.value.start, dateRange.value.end], load, { immediate: true })
onUnmounted(() => {
  epoch++
})
const ranges = [
  { days: 7, label: '日' },
  { days: 90, label: '周' },
  { days: 30, label: '月' },
]
function setRangeDays(count: number) {
  const end = new Date(`${dateRange.value.end}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() - count + 1)
  dateRange.value = { start: end.toISOString().slice(0, 10), end: dateRange.value.end }
}
const periodLabel = computed(() => `${dateRange.value.start} 至 ${dateRange.value.end}`)
const stats = computed(() => [
  {
    label: '参评对话数',
    value: data.value?.counts.evaluated,
    unit: '',
    hint: '按咨询轮次去重，取最新一次评估',
    foot: '累计数据',
    icon: 'message',
    tone: 'neutral',
  },
  {
    label: '优质对话数',
    value: data.value?.counts.high_quality,
    unit: '',
    hint: '可信总分 ≥ 85 分',
    foot: '累计数据',
    icon: 'star',
    tone: 'success',
  },
  {
    label: '风险对话数',
    value: data.value?.counts.risk,
    unit: '',
    hint: '可信总分 < 60 分；表示服务质量评分偏低，不表示患者出现心理危机',
    foot: '累计数据',
    icon: 'alert',
    tone: 'danger',
  },
  {
    label: '平均总分',
    value: data.value?.average_total,
    unit: '/ 100',
    hint: '仅纳入有效评分的对话，百分制',
    foot: `有效计分 ${data.value?.counts.scored ?? '—'} 轮`,
    icon: 'medal',
    tone: 'teal',
  },
])
const format = (n: number | null | undefined) =>
  n === null || n === undefined
    ? '—'
    : Number.isInteger(n)
      ? n.toLocaleString('zh-CN')
      : n.toFixed(1)
const hasScores = computed(() => !!data.value?.counts.scored)
const distribution = computed(() => {
  const c = data.value?.counts
  const total = c?.scored ?? 0
  return [
    { label: '优质对话', count: c?.high_quality ?? 0, kind: 'good', rule: '≥ 85 分' },
    {
      label: '中间档对话',
      count: Math.max(0, total - (c?.high_quality ?? 0) - (c?.risk ?? 0)),
      kind: 'middle',
      rule: '60 ≤ 分数 < 85',
    },
    { label: '风险对话', count: c?.risk ?? 0, kind: 'low', rule: '< 60 分' },
  ].map((item, i, all) => ({
    ...item,
    share: total ? item.count / total : 0,
    offset: total ? all.slice(0, i).reduce((sum, d) => sum + d.count, 0) / total : 0,
  }))
})
const trendRows = computed(() => data.value?.trend.filter((p) => p.average !== null) ?? [])
const chartTrend = computed(() =>
  data.value?.trend ?? [],
)
</script>
<template>
  <div class="overview-layout">
    <h1 class="sr-only">数据总览</h1>
    <section class="overview-hero">
      <img
        :src="overviewHero"
        alt=""
        class="hero-photo"
        width="2000"
        height="734"
        fetchpriority="high"
        decoding="async"
      />
      <span class="hero-fade" aria-hidden="true" />
      <div class="hero-copy">
        <p class="hero-hello">欢迎回来，管理员</p>
        <p class="hero-sub">用数据和 AI，关注每一次心理服务的质量。</p>
        <button class="hero-cta" @click="emit('navigate', 'workspace')">
          开始评估任务<Icon name="arrow" :size="18" />
        </button>
      </div>
    </section>
    <div v-if="error" class="alert danger overview-alert" role="alert">
      <strong>统计暂时无法加载</strong>
      <p>{{ error }}</p>
      <p>统计接口需要与本次前端一起部署；不会使用离线数字代替服务端数据。</p>
      <button class="text-button" @click="load">重试</button>
    </div>
    <div v-else-if="data && !data.available" class="notice overview-notice">
      数据库尚未配置，无法取得统计数据。下面的“—”表示未知，不表示 0 轮。
    </div>
    <div v-if="data?.source === 'offline-preview'" class="notice overview-notice preview-notice">
      图表布局样例：以下汇总数据为独立预设的合成样例，并非工作台报告的统计，也不代表真实评估结果。
    </div>
    <div v-else-if="data?.counts.synthetic" class="notice overview-notice">
      当前统计包含 {{ data.counts.synthetic }} 轮合成演示会话，正式数据接入后请按来源区分统计。
    </div>
    <section class="overview-stats" aria-label="服务质量统计" :aria-busy="loading">
      <article v-for="s in stats" :key="s.label" :class="['overview-stat', s.tone]">
        <span class="kpi-icon"><Icon :name="s.icon" :size="32" /></span>
        <div class="kpi-body">
          <div class="kpi-label">
            <span>{{ s.label }}</span
            ><span class="kpi-info" :title="s.hint" :aria-label="s.hint">i</span>
          </div>
          <strong>{{ loading ? '…' : format(s.value) }}<small v-if="s.unit">{{ s.unit }}</small></strong>
          <p>{{ s.foot }}</p>
        </div>
        <svg class="kpi-wave" viewBox="0 0 240 60" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 44c34-20 62-26 96-12s62 22 96 4 34-16 48-10v34H0Z" opacity=".55" />
          <path d="M0 54c30-12 56-16 86-6s58 14 92 2 46-10 62-4v14H0Z" opacity=".32" />
        </svg>
      </article>
    </section>
    <p class="overview-method">
      <span :class="['method-state', hasScores ? 'ready' : 'waiting']">{{
        hasScores ? '有效评分已纳入' : '暂无有效评分'
      }}</span
      ><span>待核验 / 复核 {{ format(data?.counts.pending) }} 轮</span
      ><span v-if="data?.counts.other_version"
        >其他评分版本 {{ data.counts.other_version }} 轮（不混入均值）</span
      ><span>评分版本：{{ data?.rubric_version ?? '尚无有效版本' }}</span>
    </p>
    <div class="overview-charts">
      <section class="surface trend-panel">
        <div class="panel-header">
          <h2>总分变化趋势<span class="panel-info" title="按评估保存日期统计每日可信总分均值">i</span></h2>
          <div class="panel-tools">
            <div class="segmented" role="group" aria-label="评价时间范围">
              <button
                v-for="r in ranges"
                :key="r.days"
                :class="{ active: days === r.days }"
                :aria-pressed="days === r.days"
                @click="setRangeDays(r.days)"
              >
                {{ r.label }}
              </button>
            </div>
            <button
              class="icon-button panel-refresh"
              :disabled="loading"
              :aria-label="loading ? '正在刷新统计' : '刷新统计'"
              @click="load"
            >
              <Icon name="refresh" :size="17" />
            </button>
          </div>
        </div>
        <TrendChart
          v-if="data?.available && hasScores"
          :trend="chartTrend"
          scale="percent"
          :monthly="props.mode === 'preview' && days === 30"
          :initial-focus="5"
        />
        <div v-else class="empty-state chart-empty">
          <Icon name="pulse" :size="34" />
          <h3>{{ loading ? '正在读取总分' : '暂无可绘制的总分' }}</h3>
          <p>初评分和待复核报告不会进入总分趋势。</p>
        </div>
        <details v-if="trendRows.length || data?.counts.scored" class="panel-details">
          <summary>查看每日数值与计分分布</summary>
          <div v-if="trendRows.length" class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>评估日期</th>
                  <th>平均总分</th>
                  <th>有效对话数</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in trendRows" :key="p.date">
                  <td>{{ p.date }}</td>
                  <td>{{ format(p.average) }} / 100</td>
                  <td>{{ p.sample_count }} 轮</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="data?.counts.scored" class="quality-distribution">
            <div class="distribution-heading">
              <h3>计分对话分布</h3>
              <span>仅统计有效评分</span>
            </div>
            <div class="distribution-layout">
              <div class="distribution-donut">
                <svg
                  viewBox="0 0 120 120"
                  role="img"
                  :aria-label="distribution.map((d) => `${d.label} ${d.count} 轮`).join('，')"
                >
                  <circle cx="60" cy="60" r="46" fill="none" stroke="#e8eeeb" stroke-width="12" />
                  <circle
                    v-for="d in distribution"
                    :key="d.kind"
                    :class="['donut-segment', d.kind]"
                    cx="60"
                    cy="60"
                    r="46"
                    fill="none"
                    stroke-width="12"
                    :stroke-dasharray="`${d.share * 289.0265} 289.0265`"
                    :stroke-dashoffset="-d.offset * 289.0265"
                    transform="rotate(-90 60 60)"
                  />
                </svg>
                <div>
                  <strong>{{ data.counts.scored }}</strong
                  ><span>有效对话</span>
                </div>
              </div>
              <dl class="distribution-details">
                <div v-for="d in distribution" :key="d.kind">
                  <dt>
                    <i :class="d.kind" /><span
                      >{{ d.label }}<small>{{ d.rule }}</small></span
                    >
                  </dt>
                  <dd>
                    {{ d.count }}<small>轮</small><span>{{ (d.share * 100).toFixed(1) }}%</span>
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </details>
      </section>
      <section class="surface radar-panel">
        <div class="panel-header">
          <h2>六维质量画像<span class="panel-info" title="六个评价维度的平均分，满分 100 分">i</span></h2>
          <div class="radar-legends" aria-label="图例">
            <span class="radar-legend"><i aria-hidden="true" />本期</span>
            <span class="radar-legend previous"><i aria-hidden="true" />上期</span>
          </div>
        </div>
        <RadarChart
          v-if="data?.available && hasScores"
          :dimensions="data.dimensions"
          :scale="props.mode === 'preview' ? 'five' : 'percent'"
        />
        <div v-else class="empty-state chart-empty">
          <Icon name="pulse" :size="34" />
          <h3>{{ loading ? '正在读取维度评分' : '暂无可绘制的维度评分' }}</h3>
          <p>完成评分并满足汇总条件后，在此展示雷达图。</p>
        </div>
        <details class="panel-details dimension-details">
          <summary>查看各维度数值与样本数</summary>
          <div class="table-scroll">
            <table class="data-table dimension-averages">
              <thead>
                <tr>
                  <th>指标维度</th>
                  <th>平均分</th>
                  <th>有效对话数</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in data?.dimensions ?? []" :key="d.dimension_id">
                  <td>
                    <span class="metric-code">{{ d.dimension_id }}</span> {{ d.name }}
                  </td>
                  <td>
                    <div class="dimension-score">
                      <strong>{{ format(d.average) }}</strong
                      ><span class="dimension-meter" aria-hidden="true"
                        ><i v-if="d.average !== null" :style="{ width: `${d.average}%` }"
                      /></span>
                    </div>
                  </td>
                  <td>{{ data?.available ? d.sample_count : '—' }} 轮</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </div>
    <div class="overview-baseline">
      <details class="surface overview-definition">
        <summary>统计口径与判定规则</summary>
        <ul>
          <li>
            同一咨询轮次只取最新一次评估，重复运行不增加对话数；时间范围按最新评估的保存日期筛选。
          </li>
          <li>
            总分 ≥ 85 为优质；总分 &lt; 60 为风险；60 ≤ 总分 &lt; 85
            为中间档。风险表示服务质量评分偏低，不表示患者出现心理危机。
          </li>
          <li>
            总分使用后端确定性汇总结果。现有报告的 0–5 分换算为 0–100 分（乘以
            20），不重新计算指标权重。
          </li>
          <li>
            均值、分类和趋势只纳入已完成核验、覆盖率达标且无未决问题的报告。评分版本不同的报告分开计算，目前展示最新有效版本。
          </li>
          <li>
            每个维度对有有效维度分的对话取平均；不适用和证据不足不补为
            0。折线为日均值，无有效评分的日期留空。
          </li>
          <li>
            当前统计窗口：{{ periodLabel }}。图表只用于展示布局样例或汇总结果，不代替原始报告。
          </li>
        </ul>
      </details>
      <p class="overview-footnote">
        数据来自服务端确定性汇总；风险表示服务质量评分偏低，不表示患者出现心理危机。
      </p>
    </div>
  </div>
</template>

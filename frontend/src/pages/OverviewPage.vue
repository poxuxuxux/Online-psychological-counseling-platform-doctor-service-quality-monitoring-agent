<!-- 环节：前端页面层；用途：实现独立业务页面及其数据呈现。 -->
<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { request } from '../api/client/http'
import { OverviewSchema, type Overview } from '../api/contracts/overview'
import { overviewPreview } from '../data/overviewPreview'
import Icon from '../components/base/Icon.vue'
import StatusBadge from '../components/base/StatusBadge.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import TrendChart from '../components/charts/TrendChart.vue'
import consultationRoom from '../assets/consultation-room.png'
const emit = defineEmits<{ navigate: [page: 'workspace' | 'rubrics' | 'review'] }>()
const props = defineProps<{ mode: 'service' | 'preview'; refreshKey: string }>()
const days = ref(30),
  loading = ref(false),
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
        ? overviewPreview(days.value)
        : await request(`/api/v1/evaluations/overview?days=${days.value}`, OverviewSchema)
    if (token === epoch) data.value = result
  } catch (e) {
    if (token === epoch) error.value = (e as Error).message
  } finally {
    if (token === epoch) loading.value = false
  }
}
watch(() => [props.mode, props.refreshKey, days.value], load, { immediate: true })
onUnmounted(() => {
  epoch++
})
const stats = computed(() => [
  {
    label: '参评对话数',
    value: data.value?.counts.evaluated,
    unit: '轮',
    hint: '按咨询轮次去重，取最新一次评估',
    icon: 'report',
    tone: 'neutral',
  },
  {
    label: '优质对话数',
    value: data.value?.counts.high_quality,
    unit: '轮',
    hint: '可信总分 ≥ 85 分',
    icon: 'check',
    tone: 'success',
  },
  {
    label: '风险对话数',
    value: data.value?.counts.risk,
    unit: '轮',
    hint: '可信总分 < 60 分',
    icon: 'shield',
    tone: 'danger',
  },
  {
    label: '平均总分',
    value: data.value?.average_total,
    unit: '分',
    hint: `有效计分 ${data.value?.counts.scored ?? '—'} 轮 · 满分 100`,
    icon: 'pulse',
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
</script>
<template>
  <div class="overview-layout">
    <div class="overview-primary">
      <section class="consultation-hero" aria-labelledby="hero-title">
        <img
          :src="consultationRoom"
          alt=""
          class="consultation-photo"
          width="2172"
          height="724"
          fetchpriority="high"
          decoding="async"
        />
        <div class="hero-copy">
          <span class="hero-eyebrow"><i aria-hidden="true" />让评价有据可循</span>
          <h2 id="hero-title">每一次倾听，<br />都值得认真评价。</h2>
          <p>从真实对话出发，发现服务亮点与改进空间。</p>
          <div class="hero-actions">
            <button class="button primary hero-start" @click="emit('navigate', 'workspace')">
              进入评估工作台<Icon name="arrow" :size="17" />
            </button>
            <button class="hero-secondary" @click="emit('navigate', 'rubrics')">
              查看评价指标<Icon name="chevron" :size="15" />
            </button>
          </div>
          <ul class="hero-features" aria-label="评价机制">
            <li><Icon name="check" :size="15" />六维服务评价</li>
            <li><Icon name="check" :size="15" />原文证据引用</li>
            <li><Icon name="check" :size="15" />修正过程留痕</li>
          </ul>
        </div>
      </section>
      <div class="overview-toolbar">
        <div>
          <strong><Icon name="clock" :size="17" />评估时间范围</strong>
          <p>
            {{
              data
                ? `${data.period_start} — ${data.period_end} · 北京时间`
                : '按评估日期统计，所有分数均按百分制展示。'
            }}
          </p>
        </div>
        <div class="overview-controls">
          <label for="overview-period">统计范围</label
          ><select id="overview-period" v-model.number="days">
            <option :value="7">最近 7 天</option>
            <option :value="30">最近 30 天</option>
            <option :value="90">最近 90 天</option>
          </select>
          <button class="button secondary" :disabled="loading" @click="load">
            <Icon name="refresh" :size="16" />{{ loading ? '加载中…' : '刷新统计' }}
          </button>
        </div>
      </div>
      <div v-if="error" class="alert danger" role="alert">
        <strong>统计暂时无法加载</strong>
        <p>{{ error }}</p>
        <p>统计接口需要与本次前端一起部署；不会使用离线数字代替服务端数据。</p>
        <button class="text-button" @click="load">重试</button>
      </div>
      <div v-else-if="data && !data.available" class="notice">
        数据库尚未配置，无法取得统计数据。下面的“—”表示未知，不表示 0 轮。
      </div>
      <div v-if="data?.source === 'offline-preview'" class="notice">
        图表布局样例：以下汇总数据为独立预设的合成样例，并非工作台报告的统计，也不代表真实评估结果。
      </div>
      <div v-else-if="data?.counts.synthetic" class="notice">
        当前统计包含 {{ data.counts.synthetic }} 轮合成演示会话，正式数据接入后请按来源区分统计。
      </div>
      <section class="overview-stats" aria-label="服务质量统计" :aria-busy="loading">
        <article v-for="s in stats" :key="s.label" :class="['surface', 'overview-stat', s.tone]">
          <div class="stat-top">
            <span>{{ s.label }}</span
            ><span class="stat-icon"><Icon :name="s.icon" :size="25" /></span>
          </div>
          <strong
            >{{ loading ? '…' : format(s.value) }}<small>{{ s.unit }}</small></strong
          >
          <p>{{ s.hint }}</p>
        </article>
      </section>
      <div class="overview-method">
        <StatusBadge :tone="hasScores ? 'success' : 'warning'">{{
          hasScores ? '有效评分已纳入' : '暂无有效评分'
        }}</StatusBadge
        ><span>待核验 / 复核 {{ format(data?.counts.pending) }} 轮</span
        ><span v-if="data?.counts.other_version"
          >其他评分版本 {{ data.counts.other_version }} 轮（不混入均值）</span
        ><span>评分版本：{{ data?.rubric_version ?? '尚无有效版本' }}</span>
      </div>
      <div class="overview-charts">
        <section class="surface radar-panel">
          <div class="panel-header">
            <div>
              <h2>维度平均分</h2>
              <p>六维质量画像 · 满分 100 分</p>
            </div>
            <span class="chart-type"><Icon name="radar" :size="17" />六维画像</span>
          </div>
          <RadarChart v-if="data?.available && hasScores" :dimensions="data.dimensions" />
          <div v-else class="empty-state chart-empty">
            <Icon name="pulse" :size="36" />
            <h3>{{ loading ? '正在读取维度评分' : '暂无可绘制的维度评分' }}</h3>
            <p>完成评分并满足汇总条件后，在此展示雷达图。</p>
          </div>
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
        </section>
        <section class="surface trend-panel">
          <div class="panel-header">
            <div>
              <h2>总分变化趋势</h2>
              <p>每天的可信总分均值 · {{ format(data?.counts.scored) }} 轮有效对话</p>
            </div>
            <span class="chart-type"><Icon name="trend" :size="17" />日均总分</span>
          </div>
          <TrendChart v-if="data?.available && hasScores" :trend="data.trend" />
          <div v-else class="empty-state chart-empty">
            <Icon name="pulse" :size="36" />
            <h3>{{ loading ? '正在读取总分' : '暂无可绘制的总分' }}</h3>
            <p>初评分和待复核报告不会进入总分趋势。</p>
          </div>
          <details v-if="trendRows.length" class="trend-table">
            <summary>查看每日数值与样本数</summary>
            <div class="table-scroll">
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
          </details>

          <div class="quality-distribution" v-if="data?.counts.scored">
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
        </section>
      </div>
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
        </ul>
      </details>
    </div>
    <aside class="overview-rail" aria-label="评价工作指南">
      <section class="surface journey-card">
        <div class="rail-heading">
          <h2>让结论经得起追问</h2>
          <Icon name="shield" :size="21" />
        </div>
        <p class="rail-intro">评价与核验相互反馈，每一次修正都留下依据。</p>
        <ol class="quality-journey">
          <li>
            <span><Icon name="list" :size="18" /></span>
            <div>
              <strong>专业评价</strong>
              <p>按主责指标分析咨询行为</p>
            </div>
          </li>
          <li>
            <span><Icon name="search" :size="18" /></span>
            <div>
              <strong>回到原文</strong>
              <p>核对事实、语境与评分依据</p>
            </div>
          </li>
          <li>
            <span><Icon name="link" :size="18" /></span>
            <div>
              <strong>讨论与仲裁</strong>
              <p>围绕未决问题交换依据</p>
            </div>
          </li>
          <li>
            <span><Icon name="refresh" :size="18" /></span>
            <div>
              <strong>反馈修正</strong>
              <p>记录旧值、新值与修改理由</p>
            </div>
          </li>
        </ol>
        <p class="rail-footnote">以上为工作机制说明，运行结果请以报告为准。</p>
      </section>
      <section class="evidence-invitation">
        <span class="invitation-icon"><Icon name="search" :size="25" /></span>
        <h2>好的评价，<br />从看见原文开始。</h2>
        <p>查看证据引用和核验结果，了解每条结论从何而来。</p>
        <button class="button primary" @click="emit('navigate', 'workspace')">
          查看原文与评价<Icon name="arrow" :size="16" />
        </button>
      </section>
      <section class="surface rules-card">
        <div class="rail-heading">
          <h2>评分规则速览</h2>
          <span>百分制</span>
        </div>
        <div class="rule-summary">
          <div>
            <strong>85<small>分起</small></strong
            ><span>优质对话</span>
          </div>
          <div>
            <strong>&lt;60<small>分</small></strong
            ><span>风险对话</span>
          </div>
        </div>
        <p>风险指服务质量评分偏低；证据不足与不适用均不直接判为低分。</p>
        <div class="rail-links">
          <button @click="emit('navigate', 'rubrics')">
            <span><Icon name="radar" :size="18" />六维 · 18 项评价指标</span
            ><Icon name="chevron" :size="16" /></button
          ><button @click="emit('navigate', 'review')">
            <span><Icon name="shield" :size="18" />进入人工复核</span
            ><Icon name="chevron" :size="16" />
          </button>
        </div>
      </section>
    </aside>
  </div>
</template>

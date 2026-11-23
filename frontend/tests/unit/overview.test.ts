// 环节：前端测试层；用途：验证前端组件逻辑、API 客户端和展示工具。
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import OverviewPage from '../../src/pages/OverviewPage.vue'
import RadarChart from '../../src/components/charts/RadarChart.vue'
import TrendChart from '../../src/components/charts/TrendChart.vue'
import ScoreRing from '../../src/components/base/ScoreRing.vue'
import { overviewPreview, overviewPreviewRange } from '../../src/data/overviewPreview'
import { OverviewSchema } from '../../src/api/contracts/overview'
let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})
describe('statistics overview', () => {
  it('shows both charts and correct synthetic classification without API calls', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    wrapper = mount(OverviewPage, { props: { mode: 'preview', refreshKey: '' } })
    await flushPromises()
    const data = overviewPreview()
    expect(wrapper.findAll('.overview-stat')).toHaveLength(4)
    expect(wrapper.get('.overview-stat.success').text()).toContain(
      data.counts.high_quality!.toLocaleString('zh-CN'),
    )
    expect(wrapper.get('.overview-stat.danger').text()).toContain(String(data.counts.risk))
    expect(wrapper.find('.radar-chart').exists()).toBe(true)
    expect(wrapper.find('.trend-chart').exists()).toBe(true)
    expect(wrapper.findAll('.dimension-averages tbody tr')).toHaveLength(6)
    expect(wrapper.get('.distribution-donut strong').text()).toBe(String(data.counts.scored))
    expect(wrapper.text()).toContain('并非工作台报告的统计')
    expect(wrapper.text()).toContain('不表示患者出现心理危机')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('changes the range and exports no fabricated reports', async () => {
    wrapper = mount(OverviewPage, { props: { mode: 'preview', refreshKey: '' } })
    await flushPromises()
    await wrapper.find('.segmented button').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(TrendChart).props('trend')).toHaveLength(7)
    expect(wrapper.text()).toContain('2024-06-24 至 2024-06-30')
  })
  it('filters synthetic totals and trend points to exact dates', () => {
    const full = overviewPreviewRange('2024-06-01', '2024-06-30')
    const week = overviewPreviewRange('2024-06-24', '2024-06-30')
    const empty = overviewPreviewRange('2024-07-01', '2024-07-07')
    expect(full.days).toBe(30)
    expect(full.average_total).toBe(84)
    expect(week.period_start).toBe('2024-06-24')
    expect(week.trend).toHaveLength(7)
    expect(week.counts.evaluated).toBeLessThan(full.counts.evaluated!)
    expect(empty.counts.evaluated).toBe(0)
    expect(empty.trend.every((point) => point.average === null)).toBe(true)
  })
  it('keeps disconnected database counts unknown instead of zero', async () => {
    const data = overviewPreview()
    data.available = false
    Object.keys(data.counts).forEach((k) => (data.counts[k as keyof typeof data.counts] = null))
    data.average_total = null
    data.dimensions.forEach((d) => {
      d.average = null
      d.sample_count = 0
    })
    data.trend.forEach((d) => {
      d.average = null
      d.sample_count = 0
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(data))),
    )
    wrapper = mount(OverviewPage, { props: { mode: 'service', refreshKey: '' } })
    await flushPromises()
    expect(wrapper.get('.overview-stat').text()).toContain('—')
    expect(wrapper.text()).toContain('数据库尚未配置')
    expect(wrapper.find('.radar-chart').exists()).toBe(false)
  })
  it('keeps unverified conversations in evaluated count but outside charts', async () => {
    const data = overviewPreview()
    data.source = 'postgresql'
    data.counts = {
      evaluated: 8,
      scored: 0,
      high_quality: 0,
      risk: 0,
      pending: 8,
      other_version: 0,
      synthetic: 8,
    }
    data.average_total = null
    data.rubric_version = null
    data.dimensions.forEach((d) => {
      d.average = null
      d.sample_count = 0
    })
    data.trend.forEach((d) => {
      d.average = null
      d.sample_count = 0
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(data))),
    )
    wrapper = mount(OverviewPage, { props: { mode: 'service', refreshKey: '' } })
    await flushPromises()
    expect(wrapper.get('.overview-stat').text()).toContain('8')
    expect(wrapper.text()).toContain('待核验 / 复核 8 轮')
    expect(wrapper.find('.trend-chart').exists()).toBe(false)
  })
  it('shows missing deployed endpoint error and never substitutes offline numbers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 404 })),
    )
    wrapper = mount(OverviewPage, { props: { mode: 'service', refreshKey: '' } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('尚未在当前服务部署')
    expect(wrapper.get('.overview-stat').text()).toContain('—')
    expect(wrapper.find('.radar-chart').exists()).toBe(false)
  })
  it('ignores old response when switching to preview', async () => {
    let finish: (response: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      ),
    )
    wrapper = mount(OverviewPage, { props: { mode: 'service', refreshKey: '' } })
    await wrapper.setProps({ mode: 'preview' })
    await flushPromises()
    const old = overviewPreview()
    old.source = 'postgresql'
    finish(new Response(JSON.stringify(old)))
    await flushPromises()
    expect(wrapper.text()).toContain('图表布局样例')
  })
  it('draws no closed radar polygon when a dimension is missing', () => {
    const data = overviewPreview()
    data.dimensions[5]!.average = null
    wrapper = mount(RadarChart, { props: { dimensions: data.dimensions } })
    expect(wrapper.find('.radar-fill').exists()).toBe(false)
    expect(wrapper.findAll('.chart-point')).toHaveLength(5)
  })
  it('preserves trend gaps and true zero scores', () => {
    wrapper = mount(TrendChart, {
      props: {
        trend: [
          { date: '2026-10-10', average: 0, sample_count: 1 },
          { date: '2026-10-11', average: null, sample_count: 0 },
          { date: '2026-10-12', average: 85, sample_count: 1 },
        ],
      },
    })
    expect(wrapper.findAll('.trend-line')).toHaveLength(2)
    expect(wrapper.findAll('.chart-point')).toHaveLength(2)
    expect(wrapper.get('.chart-point').attributes('cy')).toBe('234')
  })
  it('rejects incompatible score scales and inconsistent counts', () => {
    const data = overviewPreview()
    expect(OverviewSchema.safeParse({ ...data, score_scale: 5 }).success).toBe(false)
    expect(
      OverviewSchema.safeParse({ ...data, counts: { ...data.counts, evaluated: 1 } }).success,
    ).toBe(false)
    expect(OverviewSchema.safeParse({ ...data, trend: [] }).success).toBe(false)
  })
  it('distinguishes an unknown mean from a genuine zero in the score ring', async () => {
    wrapper = mount(ScoreRing, { props: { value: null } })
    expect(wrapper.find('.score-ring-value').exists()).toBe(false)
    expect(wrapper.get('svg').attributes('aria-label')).toContain('尚不可用')
    await wrapper.setProps({ value: 0 })
    expect(wrapper.find('.score-ring-value').exists()).toBe(true)
    expect(wrapper.get('svg').attributes('aria-label')).toContain('0.0 分')
  })
  it('exposes radar point scores and samples on keyboard focus', async () => {
    const data = overviewPreview()
    wrapper = mount(RadarChart, { props: { dimensions: data.dimensions } })
    const point = wrapper.get('.chart-point')
    expect(point.attributes('tabindex')).toBe('0')
    await point.trigger('focus')
    expect(wrapper.get('.chart-caption').text()).toContain(data.dimensions[0]!.name)
    expect(wrapper.get('.chart-caption').text()).toContain(
      data.dimensions[0]!.average!.toFixed(1),
    )
  })
  it('exposes trend dates and sample counts on keyboard focus', async () => {
    wrapper = mount(TrendChart, {
      props: { trend: [{ date: '2026-10-12', average: 85, sample_count: 3 }] },
    })
    await wrapper.get('.chart-point').trigger('focus')
    expect(wrapper.get('.chart-caption').text()).toContain('2026-10-12')
    expect(wrapper.get('.chart-caption').text()).toContain('3 轮')
  })
})

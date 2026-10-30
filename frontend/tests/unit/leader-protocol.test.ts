// 环节：前端契约回归；用途：用真实后端模型替身报告验证裁决标签、总分与协商记录。
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ReportSchema, SessionSchema } from '../../src/api/contracts/evaluation'
import { overallScore, reportRows } from '../../src/utils/trust'
import App from '../../src/App.vue'
import fixture from '../fixtures/leader-report.json'
import postFixture from '../fixtures/post-initial-report.json'
import { setPrivateAccessToken } from '../../src/api/client/http'

afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })

describe('Leader protocol actual API compatibility', () => {
  it('keeps independent initials separate from unique final metrics', () => {
    const report = ReportSchema.parse(fixture)
    expect(report.collaboration?.round_count).toBe(3)
    expect(report.collaboration?.initial_evaluations).toHaveLength(3)
    expect(reportRows(report)).toHaveLength(2)
    expect(overallScore(report)).toBe(4)
    expect(reportRows(report).every((row) => row.verdict.text === 'Leader 有据裁决')).toBe(true)
    expect(report.collaboration?.reports.at(-1)?.findings[0]?.responses).toHaveLength(3)
    expect(report.collaboration?.feedback.some((f) => f.decision === 'disagree')).toBe(true)
  })
  it('accepts actual v2 stage vectors, full initials and uncapped mean', () => {
    const report = ReportSchema.parse(postFixture)
    expect(report.collaboration?.weight_deviation).toBeNull()
    expect(report.collaboration?.weighting_stages).toHaveLength(3)
    expect(report.collaboration?.initial_evaluations.flatMap((a) => a.findings)).toHaveLength(54)
    expect(reportRows(report)).toHaveLength(4)
    expect(report.collaboration?.weights['D1.1']).toBeCloseTo(.7)
    expect(overallScore(report)).toBe(4)
  })

  it.each([['v1', fixture], ['v2', postFixture]] as const)('renders %s protocol stages and evaluation history', async (version, source) => {
    setPrivateAccessToken('test-private-access-token')
    const session = SessionSchema.parse({ session_id: source.session_id, source_id: 'test-only',
      messages: [{ message_id: 'm1', role: 'doctor', content: '听起来你很难受，我们一起看看。', sequence: 0 }] })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/api/v1/consultations?')) return new Response(JSON.stringify({
        total: 1, database_configured: true, items: [{ session_id: source.session_id,
          consultation_round: 'initial', message_count: 1, updated_at: '', evaluation_status: 'completed' }] }))
      if (url.startsWith('/api/v1/consultations/')) return new Response(JSON.stringify({ session, report: source }))
      if (url === '/health') return new Response(JSON.stringify({ status: 'ok' }))
      if (url === '/ready') return new Response(JSON.stringify({ status: 'ready', database: { configured: true, connected: true } }))
      if (url.startsWith('/api/v1/evaluations/recent')) return new Response(JSON.stringify({ database_configured: true, items: [] }))
      if (url.endsWith('/reviews')) return new Response(JSON.stringify({ items: [] }))
      return new Response('{}', { status: 404 })
    }))
    const wrapper = mount(App)
    try {
      await flushPromises()
      await wrapper.get('.nav-item[href="#workspace"]').trigger('click')
      await flushPromises()
      if (version === 'v1') {
        expect(wrapper.text()).toContain('3/3 轮')
        expect(wrapper.text()).toContain('初评前权重')
        expect(wrapper.text()).toContain('Leader 有据裁决')
        expect(wrapper.text()).toContain('Leader 未采纳反馈')
      } else {
        expect(wrapper.text()).toContain('三阶段平均权重')
        expect(wrapper.text()).toContain('阶段1 · 情境分析')
        expect(wrapper.text()).toContain('阶段2 · 评分与证据分布')
        expect(wrapper.text()).toContain('阶段3 · 核心需求相关性')
        expect(wrapper.text()).toContain('70.00%')
        expect(wrapper.text()).toContain('三方共识评分')
        expect(wrapper.text()).not.toContain('初评前权重')
      }
      expect(wrapper.text()).toContain('独立初评')
      expect(wrapper.text()).toContain('不等于三方一致')
    } finally { wrapper.unmount() }
  })
})

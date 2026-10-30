// 环节：前端测试层；用途：验证前端组件逻辑、API 客户端和展示工具。
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import App from '../../src/App.vue'
import { previewSession, previewReport } from '../../src/data/preview'
import { setPrivateAccessToken } from '../../src/api/client/http'

let wrapper: VueWrapper | undefined
let requests: string[] = []
let failEvaluation = false
let failSessionId = ''
let catalogUnavailable = false
let resolveEvaluation: (() => void) | undefined
let holdEvaluation = false
let withInvestigation = false
let modelConfigured: boolean | undefined
let failedReportSessionId = ''
let highRiskSessionId = ''
beforeEach(() => {
  requests = []
  failEvaluation = false
  failSessionId = ''
  catalogUnavailable = false
  holdEvaluation = false
  withInvestigation = false
  modelConfigured = undefined
  failedReportSessionId = ''
  highRiskSessionId = ''
  setPrivateAccessToken('test-private-access-token')
  location.hash = 'workspace'
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, options?: RequestInit) => {
      requests.push(`${options?.method || 'GET'} ${path}`)
      if (path === '/health') return new Response(JSON.stringify({ status: 'ok' }))
      if (path === '/ready')
        return new Response(
          JSON.stringify({ status: 'ready', database: { configured: false, connected: false },
            ...(modelConfigured === undefined ? {} : { model: { configured: modelConfigured } }) }),
        )
      if (path.startsWith('/api/v1/evaluations/recent'))
        return new Response(JSON.stringify({ database_configured: false, items: [] }))
      if (path.startsWith('/api/v1/consultations?')) {
        if (catalogUnavailable) return new Response('{}', { status: 404 })
        const url = new URL(path, 'http://testserver')
        const all = [0, 1, 2].map((index) => previewSession(index))
        const matched = all.filter((item) => item.session_id.includes(url.searchParams.get('query') || ''))
        const offset = Number(url.searchParams.get('offset') || 0)
        const limit = Number(url.searchParams.get('limit') || 5)
        return new Response(JSON.stringify({ database_configured: true, total: matched.length,
          items: matched.slice(offset, offset + limit).map((item) => ({
            session_id: item.session_id, consultation_round: item.consultation_round,
            message_count: item.messages.length, updated_at: '', evaluation_status: null,
          })) }))
      }
      if (path.startsWith('/api/v1/consultations/')) {
        const id = decodeURIComponent(path.split('/').pop() || '')
        const session = [0, 1, 2].map((index) => previewSession(index)).find((item) => item.session_id === id)
        return new Response(JSON.stringify({ session, report: null }))
      }
      if (path === '/api/v1/demo/sessions')
        return catalogUnavailable
          ? new Response('{}', { status: 404 })
          : new Response(JSON.stringify([0, 1, 2].map((index) => previewSession(index))))
      if (path.startsWith('/api/v1/demo/sessions/')) {
        const id = decodeURIComponent(path.split('/').pop() || '')
        const session = [0, 1, 2].map((index) => previewSession(index)).find((item) => item.session_id === id)
        return new Response(JSON.stringify({ session, report: null }))
      }
      if (path === '/api/v1/demo/session') return new Response(JSON.stringify(previewSession()))
      if (path.endsWith('/reviews') && options?.method === 'POST') {
        const input = JSON.parse(String(options.body))
        return new Response(JSON.stringify({ ...input, review_id: 'review-test', created_at: new Date().toISOString() }))
      }
      if (path.endsWith('/reviews')) return new Response(JSON.stringify({ items: [] }))
      if (path === '/api/v1/sessions' && options?.method === 'POST')
        return new Response(JSON.stringify({ session_id: JSON.parse(String(options.body)).session_id }))
      if (path === '/api/v1/evaluations' || path === '/api/v1/guest/evaluations') {
        const session = JSON.parse(String(options?.body))
        if (holdEvaluation)
          await new Promise<void>((resolve) => {
            resolveEvaluation = resolve
          })
        if (failEvaluation || session.session_id === failSessionId)
          return new Response('{}', { status: 500 })
        const generated = previewReport(session)
        generated.risk = {
          level: session.session_id === highRiskSessionId ? 'high' : 'low',
          scope: 'doctor_service_quality',
          reasons: [],
        }
        if (session.session_id === failedReportSessionId) {
          generated.status = 'failed'
          generated.team = { model_call_count: 0, stop_reason: 'model_not_configured' }
          generated.review_reasons = ['metric_submission_rejected', 'leader_planning_incomplete', 'insufficient_scored_coverage']
          generated.execution_issues = [{ agent_id: 'evaluator:effectiveness', stage: 'initial_evaluation',
            metric_id: 'D1.1', error: 'Score needs a Skill anchor and source-grounded claims',
            fields: [], attempt: 3, transport: null }]
        }
        if (withInvestigation) generated.investigation = {
          stop_reason: 'agent_finished', uncovered_metric_ids: [], attempts: { 'D2.1': 1 },
          model_call_count: 7, model_call_limit: 48,
          preflight_history: { required: true, status: 'completed', issues: [] },
          metric_statuses: { 'D2.1': 'evaluated' },
          observations: [{ step: 1, action: 'calculate_time', question: '回复间隔是多少？',
                           status: 'completed', tool_name: 'time_calculator' }],
        }
        return new Response(JSON.stringify(generated))
      }
      return new Response('{}', { status: 404 })
    }),
  )
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})
async function start() {
  wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  await wrapper.get('.mode-switch-button').trigger('click')
  await flushPromises()
  return wrapper
}
async function evaluate() {
  await wrapper!.get('.upload-actions .primary').trigger('click')
  await flushPromises()
}
async function navigate(page: string) {
  await wrapper!.get(`.nav-item[href="#${page}"]`).trigger('click')
  await flushPromises()
}
async function setDateRange(app: VueWrapper, start: string, end: string) {
  await app.get('.top-date').trigger('click')
  const dates = app.findAll('.date-range-popover input[type="date"]')
  await dates[0]!.setValue(start)
  await dates[1]!.setValue(end)
  await app.get('.date-range-apply').trigger('click')
  await flushPromises()
}
async function setTodayRange(app: VueWrapper) {
  const today = new Date().toISOString().slice(0, 10)
  await setDateRange(app, today, today)
}
async function setDialogValue(selector: string, value: string, eventName = 'input') {
  const field = document.body.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)
  if (!field) throw new Error(`Unable to find dialog field ${selector}`)
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), 'value')?.set
  setter?.call(field, value)
  field.dispatchEvent(new Event(eventName, { bubbles: true }))
  await flushPromises()
}
async function submitDialog() {
  const form = document.body.querySelector<HTMLFormElement>('.review-score-form')
  if (!form) throw new Error('Unable to find the review dialog form')
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
}
describe('workbench actual component interaction', () => {
  it('opens the offline workspace by default without backend requests', async () => {
    wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('.evaluation-workspace').text()).toContain('离线演示')
    expect(wrapper.findAll('.metric-item')).toHaveLength(18)
    expect(requests).toHaveLength(0)
  })
  it('opens offline quality reports without backend requests', async () => {
    location.hash = 'reports'
    wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('.quality-reports-page').text()).toContain('ZJ-20240628-001')
    expect(wrapper.findAll('.risk-card')).toHaveLength(4)
    expect(wrapper.findAll('.history-table tbody tr')).toHaveLength(4)
    expect(requests).toHaveLength(0)
  })
  it('filters report history without restoring the removed full-report action', async () => {
    location.hash = 'reports'
    const app = mount(App, { attachTo: document.body })
    wrapper = app
    await flushPromises()
    await setDateRange(app, '2024-05-10', '2024-05-10')
    await app.get('.history-search input').setValue('5月第二周')
    expect(app.findAll('.history-table tbody tr')).toHaveLength(1)
    expect(app.findAll('.view-report')).toHaveLength(0)
    expect(app.findAll('.report-detail-panel')).toHaveLength(0)
    expect(requests).toHaveLength(0)
  })
  it('opens the offline review queue without backend requests', async () => {
    location.hash = 'review'
    wrapper = mount(App, { attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('.review-page').text()).toContain('人工复核')
    expect(wrapper.findAll('.stat-card')).toHaveLength(4)
    expect(wrapper.findAll('.review-item')).toHaveLength(6)
    expect(wrapper.findAll('.metric-row')).toHaveLength(18)
    expect(wrapper.get('.review-item').text()).toContain('C202406010001')
    expect(requests).toHaveLength(0)
  })
  it('filters review sessions and submits a local review opinion', async () => {
    location.hash = 'review'
    const app = mount(App, { attachTo: document.body })
    wrapper = app
    await flushPromises()
    await app.get('.review-search input').setValue('C202406010001')
    expect(app.findAll('.review-item')).toHaveLength(1)
    await app.get('.result-review-button').trigger('click')
    expect(document.body.querySelectorAll('.review-score-row')).toHaveLength(18)
    await setDialogValue('.review-dialog-note textarea', '证据不足，建议补充风险来源与随访安排。')
    await submitDialog()
    await flushPromises()
    expect(app.get('.toast').text()).toContain('复核结果已在本页保存')
    expect(app.get('.stat-card.total strong').text()).toBe('13')
    expect(requests).toHaveLength(0)
  })
  it('shows the bounded investigation trace returned by the backend', async () => {
    withInvestigation = true
    const app = await start()
    await evaluate()
    expect(app.get('.investigation-trace').text()).toContain('回复间隔是多少？')
    expect(app.get('.investigation-trace').text()).toContain('复诊强制历史检索：completed')
    expect(app.get('.investigation-trace').text()).toContain('模型请求：7/48')
  })
  it('opens the overview by default and keeps the evaluation workspace reachable', async () => {
    location.hash = ''
    const app = await start()
    expect(app.get('h1').text()).toBe('数据总览')
    await navigate('workspace')
    expect(app.findAll('.conversation-message')).toHaveLength(6)
    expect(app.get('.upload-actions .primary').attributes('disabled')).toBeUndefined()
  })
  it('loads six messages and enables evaluation', async () => {
    const app = await start()
    expect(app.findAll('.conversation-message')).toHaveLength(6)
    expect(app.get('.upload-actions .primary').attributes('disabled')).toBeUndefined()
    expect(app.get('.upload-actions .primary').text()).toContain('一键评估')
  })
  it('evaluates all connected sessions despite a list search filter', async () => {
    const app = await start()
    await app.get('.search-field input').setValue('preview-synthetic-001')
    await app.get('.consultation-list-tools').trigger('submit')
    await flushPromises()
    expect(app.findAll('.consultation-id')).toHaveLength(1)
    await evaluate()
    expect(requests.filter((r) => r === 'POST /api/v1/evaluations')).toHaveLength(3)
    expect(app.get('.run-note').text()).toContain('成功 3 条，失败 0 条')
  })
  it('uses the backend service-risk level for the batch summary', async () => {
    highRiskSessionId = 'preview-synthetic-002'
    const app = await start()
    await evaluate()
    await setTodayRange(app)
    await navigate('reports')
    expect(app.get('.latest-report-panel .risk-cards').text()).toContain('高风险1')
    expect(app.get('.latest-report-panel .risk-cards').text()).toContain('低风险2')
  })
  it('stops batch evaluation when the backend reports no model key', async () => {
    modelConfigured = false
    const app = await start()
    await evaluate()
    expect(requests.filter((r) => r === 'POST /api/v1/evaluations')).toHaveLength(0)
    expect(app.text()).toContain('后端尚未配置模型密钥')
  })
  it('counts a failed backend report as a failed session', async () => {
    failedReportSessionId = 'preview-synthetic-002'
    const app = await start()
    await evaluate()
    expect(app.get('.run-note').text()).toContain('成功 2 条，失败 1 条')
    expect(app.text()).toContain('model_not_configured')
  })
  it('shows the six-dimension result and translated validation details when evaluation fails', async () => {
    failedReportSessionId = 'preview-synthetic-001'
    const app = await start()
    await evaluate()
    expect(app.get('.results-panel .result-status.failed').text()).toContain('评估失败')
    expect(app.get('.workspace-result-failure').text()).toContain('未生成可信总分')
    expect(app.findAll('.workspace-result-groups .metric-group')).toHaveLength(6)
    expect(app.findAll('.workspace-result-groups .metric-row')).toHaveLength(18)
    expect(app.get('.report-limitations').text()).toContain('指标结果连续未通过后端校验')
    expect(app.get('.execution-issues').text()).toContain('评分缺少量表依据或原文证据')
    expect(app.text()).not.toContain('Leader 组织与协商')
  })
  it('continues the remaining sessions when one evaluation fails', async () => {
    failSessionId = 'preview-synthetic-002'
    const app = await start()
    await evaluate()
    expect(requests.filter((r) => r === 'POST /api/v1/evaluations')).toHaveLength(3)
    expect(app.get('.run-note').text()).toContain('成功 2 条，失败 1 条')
    expect(app.text()).toContain('preview-synthetic-002')
  })
  it('does not claim a single legacy demo record is the complete batch', async () => {
    const app = await start()
    catalogUnavailable = true
    await evaluate()
    expect(requests.filter((r) => r === 'POST /api/v1/evaluations')).toHaveLength(0)
    expect(app.text()).toContain('本次请求未完成')
  })
  it('renders a report and does not average initial scores', async () => {
    const app = await start()
    await evaluate()
    expect(app.findAll('.workspace-result-groups .metric-group')).toHaveLength(6)
    expect(app.findAll('.workspace-result-groups .metric-row')).toHaveLength(18)
    expect(app.get('.summary-counts').text()).toContain('—')
    expect(app.get('.summary-counts').text()).toContain('待核查')
  })
  it('filters unresolved findings instead of silently discarding them', async () => {
    const app = await start()
    await evaluate()
    await app.get('.filter-toolbar select').setValue('pending')
    expect(app.findAll('.workspace-result-groups .metric-row')).toHaveLength(5)
  })
  it('focuses referenced source messages', async () => {
    const app = await start()
    await evaluate()
    const evidencedMetric = app.findAll('.workspace-result-groups .metric-row').find((row) => row.text().includes('D5.4'))
    if (!evidencedMetric) throw new Error('Unable to find a scored metric row')
    await evidencedMetric.trigger('click')
    await app.get('.finding-detail .evidence-actions button').trigger('click')
    await flushPromises()
    expect(app.get('#message-preview-m4').classes()).toContain('highlighted')
    expect(document.activeElement?.id).toBe('message-preview-m4')
  })
  it('keeps both revisions and real discussion records', async () => {
    const app = await start()
    await evaluate()
    const row = app.findAll('.workspace-result-groups .metric-row').find((r) => r.text().includes('D4.1'))!
    await row.trigger('click')
    expect(app.findAll('.revision-compare article')).toHaveLength(2)
    expect(app.findAll('.discussion-list li')).toHaveLength(4)
    expect(app.get('.arbitration-record').text()).toContain('转人工复核')
  })
  it('keeps export disabled without explicit acknowledgment', async () => {
    const app = await start()
    await evaluate()
    await navigate('reports')
    expect(app.get('.reports-heading-actions .reports-action').attributes('disabled')).toBeDefined()
    await app.get('.report-export-consent input').setValue(true)
    expect(app.get('.reports-heading-actions .reports-action').attributes('disabled')).toBeUndefined()
  })
  it('switches to an unresolved item and submits a review decision', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    expect(app.get('.result-panel').text()).toContain('AI 评价结果')
    await app.get('.result-review-button').trigger('click')
    const adjust = document.body.querySelector<HTMLInputElement>('.review-decision-options input[value="adjust"]')
    if (!adjust) throw new Error('Unable to find the adjustment decision')
    adjust.checked = true
    adjust.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    await setDialogValue('.review-score-input input', '3.5')
    await setDialogValue('.review-total-score input', '82')
    await setDialogValue('.review-dialog-note textarea', '依据对话证据修正一项评分并核对总分。')
    await submitDialog()
    await flushPromises()
    expect(document.body.querySelector('.review-score-dialog')).toBeNull()
    expect(requests.filter((r) => r.startsWith('POST') && r.endsWith('/reviews'))).toHaveLength(1)
    expect(app.text()).toContain('已写入服务器')
  })
  it('rejects a draft without a substantive reason', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    await app.get('.result-review-button').trigger('click')
    await setDialogValue('.review-total-score input', '80')
    await setDialogValue('.review-dialog-note textarea', '好')
    await submitDialog()
    expect(document.body.querySelector('.review-dialog-error')?.textContent).toContain('至少需要 10 个字')
    expect(requests.filter((r) => r.startsWith('POST') && r.endsWith('/reviews'))).toHaveLength(0)
  })
  it('catalog shows eighteen metrics under the six published dimensions', async () => {
    const app = await start()
    await navigate('rubrics')
    expect(app.findAll('.rubric-item')).toHaveLength(18)
    expect(app.findAll('.rubric-section')).toHaveLength(6)
    expect(app.text()).toContain('D1 服务可靠性')
    expect(app.text()).toContain('D2 服务响应性')
    expect(app.text()).toContain('D3 专业信息沟通')
    expect(app.text()).toContain('D4 情感共情性')
    expect(app.text()).toContain('D5 咨询协作性')
    expect(app.text()).toContain('D6 心理风险应对')
  })
  it('does not claim the local database is connected', async () => {
    const app = await start()
    await navigate('service')
    expect(app.get('.connection-facts').text()).toContain('未配置或状态未知')
  })
  it('uploads a JSON session without an access token and evaluates only its row', async () => {
    setPrivateAccessToken('')
    const app = await start()
    const input = app.get('#workspace-session-import')
    const file = new File([JSON.stringify(previewSession())], 'sample.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: async () => JSON.stringify(previewSession()) })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(app.text()).toContain('已完成 1/1 份')
    expect(app.get('.upload-progress').text()).toBe('完成')
    expect(app.findAll('.consultation-row')).toHaveLength(1)
    await app.get('.consultation-evaluate').trigger('click')
    await flushPromises()
    expect(requests.filter((r) => r === 'POST /api/v1/guest/evaluations')).toHaveLength(1)
    expect(app.get('.session-identity').text()).toContain('preview-synthetic-001')
  })
  it('does not create a report when the POST fails', async () => {
    failEvaluation = true
    const app = await start()
    await evaluate()
    expect(app.text()).toContain('本次请求未完成')
    expect(app.findAll('.finding-row')).toHaveLength(0)
    expect(requests.filter((r) => r === 'POST /api/v1/evaluations')).toHaveLength(3)
  })
  it('guards double clicks while mutation is running', async () => {
    holdEvaluation = true
    const app = await start()
    await app.get('.upload-actions .primary').trigger('click')
    await flushPromises()
    await app.get('.upload-actions .primary').trigger('click')
    expect(app.get('.upload-actions .primary').attributes('disabled')).toBeDefined()
    expect(requests.filter((r) => r.startsWith('POST'))).toHaveLength(1)
    holdEvaluation = false
    resolveEvaluation!()
    await flushPromises()
  })
  it('explicit offline mode never makes a server evaluation request', async () => {
    const app = await start()
    await app.get('.mode-switch-button').trigger('click')
    await flushPromises()
    const count = requests.length
    await app.get('.workspace-actions .primary').trigger('click')
    expect(requests.length).toBe(count)
    expect(app.get('.workspace-data-note').text()).toContain('合成离线数据')
  })
  it('mobile navigation closes after choosing a page', async () => {
    const app = await start()
    await app.get('.mobile-menu').trigger('click')
    expect(app.get('.sidebar').classes()).toContain('open')
    await navigate('rubrics')
    expect(app.get('.sidebar').classes()).not.toContain('open')
  })
  it('switches offline consultation IDs and matches their source evidence without requests', async () => {
    const app = await start()
    await app.get('.mode-switch-button').trigger('click')
    await flushPromises()
    await setDateRange(app, '2024-05-30', '2024-06-01')
    await flushPromises()
    expect(app.findAll('.session-item')).toHaveLength(6)
    const before = requests.length
    await app.findAll('.session-item')[2]!.trigger('click')
    await flushPromises()
    expect(app.get('.conversation-heading').text()).toContain('C202405310089')
    expect(app.findAll('.conversation-message')[0]!.text()).toContain('情绪一直很低落')
    expect(app.get('.result-empty').text()).toContain('等待开始评价')
    expect(requests.length).toBe(before)
    await app.findAll('.session-item')[0]!.trigger('click')
    await app.findAll('.metric-item')[0]!.trigger('click')
    await app.get('.metric-detail button').trigger('click')
    await flushPromises()
    expect(app.get('.conversation-message.highlighted').text()).toContain('我理解这让你感到很困扰')
    expect(requests.length).toBe(before)
  })
  it('filters review priorities while keeping risk labels visible', async () => {
    const app = await start()
    await evaluate()
    await setTodayRange(app)
    await navigate('review')
    expect(app.findAll('.review-item')).toHaveLength(3)
    await app.get('.stat-card.high').trigger('click')
    expect(app.findAll('.review-item')).toHaveLength(0)
    await app.get('.stat-card.medium').trigger('click')
    expect(app.findAll('.review-item')).toHaveLength(0)
    await app.get('.stat-card.low').trigger('click')
    const lowRiskItems = app.findAll('.review-item')
    expect(lowRiskItems).toHaveLength(3)
    expect(lowRiskItems.every((item) => item.find('.risk-badge.low').exists())).toBe(true)
    expect(app.findAll('.metric-row').some((item) => item.text().includes('D6.1'))).toBe(true)
  })
})

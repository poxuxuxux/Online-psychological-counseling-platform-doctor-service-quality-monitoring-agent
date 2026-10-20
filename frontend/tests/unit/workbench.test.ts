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
beforeEach(() => {
  requests = []
  failEvaluation = false
  failSessionId = ''
  catalogUnavailable = false
  holdEvaluation = false
  withInvestigation = false
  modelConfigured = undefined
  failedReportSessionId = ''
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
      if (path === '/api/v1/evaluations') {
        const session = JSON.parse(String(options?.body))
        if (holdEvaluation)
          await new Promise<void>((resolve) => {
            resolveEvaluation = resolve
          })
        if (failEvaluation || session.session_id === failSessionId)
          return new Response('{}', { status: 500 })
        const generated = previewReport(session)
        if (session.session_id === failedReportSessionId) {
          generated.status = 'failed'
          generated.team = { model_call_count: 0, stop_reason: 'model_not_configured' }
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
  return wrapper
}
async function evaluate() {
  await wrapper!.get('.heading-actions .primary').trigger('click')
  await flushPromises()
}
async function navigate(page: string) {
  await wrapper!.get(`.nav-item[href="#${page}"]`).trigger('click')
  await flushPromises()
}
describe('workbench actual component interaction', () => {
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
    expect(app.get('.heading-actions .primary').attributes('disabled')).toBeUndefined()
  })
  it('loads six messages and enables evaluation', async () => {
    const app = await start()
    expect(app.findAll('.conversation-message')).toHaveLength(6)
    expect(app.get('.heading-actions .primary').attributes('disabled')).toBeUndefined()
    expect(app.get('.heading-actions .primary').text()).toContain('一键自动评估')
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
    expect(app.findAll('.finding-row')).toHaveLength(7)
    expect(app.get('.summary-counts').text()).toContain('—')
    expect(app.get('.summary-counts').text()).toContain('待核查')
  })
  it('filters unresolved findings instead of silently discarding them', async () => {
    const app = await start()
    await evaluate()
    await app.get('.filter-toolbar select').setValue('pending')
    expect(app.findAll('.finding-row')).toHaveLength(5)
  })
  it('focuses referenced source messages', async () => {
    const app = await start()
    await evaluate()
    await app.get('.finding-detail .evidence-actions button').trigger('click')
    await flushPromises()
    expect(app.get('#message-preview-m2').classes()).toContain('highlighted')
    expect(document.activeElement?.id).toBe('message-preview-m2')
  })
  it('keeps both revisions and real discussion records', async () => {
    const app = await start()
    await evaluate()
    const row = app.findAll('.finding-row').find((r) => r.text().includes('D4.1'))!
    await row.trigger('click')
    expect(app.findAll('.revision-compare article')).toHaveLength(2)
    expect(app.findAll('.discussion-list li')).toHaveLength(4)
    expect(app.get('.arbitration-record').text()).toContain('转人工复核')
  })
  it('keeps export disabled without explicit acknowledgment', async () => {
    const app = await start()
    await evaluate()
    await navigate('reports')
    expect(app.get('.export-area button').attributes('disabled')).toBeDefined()
    await app.get('.export-area input').setValue(true)
    expect(app.get('.export-area button').attributes('disabled')).toBeUndefined()
  })
  it('switches to an unresolved item and submits a review decision', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    expect(app.get('.finding-detail .status-badge').text()).not.toBe('核验通过')
    await app.get('#decision').setValue('无法判断')
    await app.get('#reason').setValue('缺少正式评分依据，请专业复核。')
    await app.get('.review-form').trigger('submit')
    await flushPromises()
    expect(app.findAll('.draft-record')).toHaveLength(1)
    expect(requests.filter((r) => r.startsWith('POST') && r.endsWith('/reviews'))).toHaveLength(1)
    expect(app.text()).toContain('已写入服务器')
  })
  it('rejects a draft without a substantive reason', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    await app.get('#decision').setValue('确认')
    await app.get('#reason').setValue('好')
    await app.get('.review-form').trigger('submit')
    expect(app.findAll('.draft-record')).toHaveLength(0)
  })
  it('catalog shows eighteen metrics under the three merged evaluator groups', async () => {
    const app = await start()
    await navigate('rubrics')
    expect(app.findAll('.rubric-item')).toHaveLength(18)
    expect(app.findAll('.rubric-section')).toHaveLength(3)
    expect(app.text()).toContain('D1+D3')
    expect(app.text()).toContain('D2+D5')
    expect(app.text()).toContain('D4+D6')
  })
  it('does not claim the local database is connected', async () => {
    const app = await start()
    await navigate('service')
    expect(app.get('.connection-facts').text()).toContain('未配置或状态未知')
  })
  it('uploads a selected normalized session only after private access is set', async () => {
    const app = await start()
    await navigate('service')
    await app.get('#private-access-token').setValue('test-private-access-token')
    await app.get('.capability-panel form').trigger('submit')
    await flushPromises()
    const input = app.get('#session-import')
    const file = new File([JSON.stringify(previewSession())], 'sample.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: async () => JSON.stringify(previewSession()) })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(requests.filter((r) => r === 'POST /api/v1/sessions')).toHaveLength(1)
    expect(app.text()).toContain('已导入 1/1 份')
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
    await app.get('.heading-actions .primary').trigger('click')
    await flushPromises()
    await app.get('.heading-actions .primary').trigger('click')
    expect(app.get('.heading-actions .primary').attributes('disabled')).toBeDefined()
    expect(requests.filter((r) => r.startsWith('POST'))).toHaveLength(1)
    holdEvaluation = false
    resolveEvaluation!()
    await flushPromises()
  })
  it('explicit offline mode never makes a server evaluation request', async () => {
    const app = await start()
    await app.get('.mode-button').trigger('click')
    await flushPromises()
    const count = requests.length
    await evaluate()
    expect(requests.length).toBe(count)
    expect(app.get('.mode-notice').text()).toContain('预设合成数据')
  })
  it('mobile navigation closes after choosing a page', async () => {
    const app = await start()
    await app.get('.mobile-menu').trigger('click')
    expect(app.get('.sidebar').classes()).toContain('open')
    await navigate('rubrics')
    expect(app.get('.sidebar').classes()).not.toContain('open')
  })
  it('switches among three offline consultation IDs and matches their source evidence', async () => {
    const app = await start()
    await app.get('.mode-button').trigger('click')
    await flushPromises()
    expect(app.findAll('.consultation-id')).toHaveLength(3)
    const before = requests.length
    await app.findAll('.consultation-id')[2]!.trigger('click')
    await flushPromises()
    expect(app.get('.session-identity').text()).toContain('preview-synthetic-003')
    expect(app.findAll('.conversation-message')[0]!.text()).toContain('最近加班')
    expect(app.findAll('.finding-row')).toHaveLength(7)
    expect(app.get('.finding-detail .evidence-quote').text()).toContain('本次原文可定位')
    expect(requests.length).toBe(before)
    await evaluate()
    expect(app.get('.session-identity').text()).toContain('preview-synthetic-003')
    expect(app.findAll('.finding-row')).toHaveLength(7)
  })
  it('sorts and filters review priorities without hiding the verification status', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    expect(app.findAll('.session-review-item')).toHaveLength(3)
    await app.get('.priority-count.priority-high').trigger('click')
    expect(app.findAll('.session-review-item')).toHaveLength(0)
    await app.get('.priority-count.priority-medium').trigger('click')
    expect(app.findAll('.session-review-item')).toHaveLength(3)
    expect(app.findAll('.session-finding-item').some((item) => item.text().includes('D6.1'))).toBe(true)
    expect(app.get('.priority-detail').text()).toContain('核查优先级：高')
    expect(app.get('.finding-detail .status-badge').text()).toBe('材料冲突')
    await app.get('.priority-count.priority-low').trigger('click')
    expect(app.findAll('.session-review-item')).toHaveLength(0)
    expect(app.get('.review-queue .empty-note').text()).toContain('当前筛选没有待复核会话')
  })
})

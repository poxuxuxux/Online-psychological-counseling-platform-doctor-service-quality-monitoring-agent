// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import App from '../../src/App.vue'
import { previewSession, previewReport } from '../../src/data/preview'

let wrapper: VueWrapper | undefined
let requests: string[] = []
let failEvaluation = false
let resolveEvaluation: (() => void) | undefined
let holdEvaluation = false
beforeEach(() => {
  requests = []
  failEvaluation = false
  holdEvaluation = false
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
          JSON.stringify({ status: 'ready', database: { configured: false, connected: false } }),
        )
      if (path.startsWith('/api/v1/evaluations/recent'))
        return new Response(JSON.stringify({ database_configured: false, items: [] }))
      if (path === '/api/v1/demo/session') return new Response(JSON.stringify(previewSession()))
      if (path === '/api/v1/evaluations') {
        if (holdEvaluation)
          await new Promise<void>((resolve) => {
            resolveEvaluation = resolve
          })
        if (failEvaluation) return new Response('{}', { status: 500 })
        return new Response(JSON.stringify(previewReport()))
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
  it('switches to an unresolved item in the review queue and saves only local drafts', async () => {
    const app = await start()
    await evaluate()
    await navigate('review')
    expect(app.get('.finding-detail .status-badge').text()).not.toBe('核验通过')
    await app.get('#decision').setValue('无法判断')
    await app.get('#reason').setValue('缺少正式评分依据，请专业复核。')
    await app.get('.review-form').trigger('submit')
    await flushPromises()
    expect(app.findAll('.draft-record')).toHaveLength(1)
    expect(requests.filter((r) => r.startsWith('POST'))).toHaveLength(1)
    expect(app.text()).toContain('未提交服务器')
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
  it('catalog has eighteen unique-owner rows', async () => {
    const app = await start()
    await navigate('rubrics')
    expect(app.findAll('.rubric-item')).toHaveLength(18)
  })
  it('does not claim the local database is connected', async () => {
    const app = await start()
    await navigate('service')
    expect(app.get('.connection-facts').text()).toContain('未配置或状态未知')
  })
  it('does not create a report when the POST fails', async () => {
    failEvaluation = true
    const app = await start()
    await evaluate()
    expect(app.text()).toContain('本次请求未完成')
    expect(app.findAll('.finding-row')).toHaveLength(0)
    expect(requests.filter((r) => r.startsWith('POST'))).toHaveLength(1)
  })
  it('guards double clicks while mutation is running', async () => {
    holdEvaluation = true
    const app = await start()
    await app.get('.heading-actions .primary').trigger('click')
    await app.get('.heading-actions .primary').trigger('click')
    expect(app.get('.heading-actions .primary').attributes('disabled')).toBeDefined()
    expect(requests.filter((r) => r.startsWith('POST'))).toHaveLength(1)
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
})

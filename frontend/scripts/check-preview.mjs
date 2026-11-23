// 环节：前端构建辅助层；用途：执行构建产物同步、预览启动或产物检查。
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { JSDOM } from 'jsdom'
import assert from 'node:assert/strict'

const frontend = fileURLToPath(new URL('..', import.meta.url))
const html = readFileSync(resolve(frontend, '../frontend-preview.html'), 'utf8')
const errors = []
const dom = new JSDOM(html, {
  url: 'file:///synthetic-preview/frontend-preview.html',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  beforeParse(window) {
    window.matchMedia = () => ({ matches: true })
    window.TextEncoder = TextEncoder
    window.TextDecoder = TextDecoder
    window.HTMLElement.prototype.scrollIntoView = () => {}
    window.addEventListener('error', (event) => errors.push(event.message))
  },
})
const wait = () => new Promise((resolve) => setTimeout(resolve, 25))
try {
  await wait()
  const doc = dom.window.document
  assert.equal(doc.querySelector('h1').textContent, '数据总览')
  assert.ok(doc.querySelector('.mode-notice').textContent.includes('预设合成数据'))
  doc.querySelector('.nav-item[href="#overview"]').click()
  await wait()
  assert.equal(doc.querySelectorAll('.overview-stat').length, 4)
  assert.equal(doc.querySelectorAll('.dimension-averages tbody tr').length, 6)
  assert.ok(doc.querySelector('.radar-chart'))
  assert.ok(doc.querySelector('.trend-chart'))
  assert.ok(doc.querySelector('.hero-photo').src.startsWith('data:image/png;base64,'))
  doc.querySelector('.nav-item[href="#rubrics"]').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '评价指标')
  doc.querySelector('.nav-item[href="#overview"]').click()
  await wait()
  doc.querySelector('.nav-item[href="#review"]').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '人工复核')
  doc.querySelector('.nav-item[href="#overview"]').click()
  await wait()
  doc.querySelector('.hero-cta').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '评估工作台')
  assert.equal(doc.querySelectorAll('.conversation-message').length, 6)
  assert.ok(doc.querySelectorAll('.session-item').length >= 3)
  const originalSession = doc.querySelector('.session-item.selected').textContent
  doc.querySelectorAll('.session-item')[2].click()
  await wait()
  assert.notEqual(doc.querySelector('.session-item.selected').textContent, originalSession)
  const evaluateButton = doc.querySelector('.workspace-heading .workspace-button.primary')
    || doc.querySelector('.workspace-button.primary')
  evaluateButton.click()
  await wait()
  assert.equal(evaluateButton.disabled, true)
  const deadline = Date.now() + 5000
  while (evaluateButton.disabled && Date.now() < deadline) await wait()
  assert.equal(evaluateButton.disabled, false)
  assert.equal(doc.querySelectorAll('.metric-item').length, 18)
  doc.querySelector('.evidence-tag').click()
  await wait()
  assert.ok(doc.querySelector('.conversation-message.highlighted'))
  doc.querySelector('.nav-item[href="#review"]').click()
  await wait()
  assert.equal(doc.querySelectorAll('.review-stats .stat-card').length, 4)
  doc.querySelectorAll('.risk-tabs button')[2].click()
  await wait()
  assert.ok(doc.querySelectorAll('.review-item').length > 0)
  assert.ok([...doc.querySelectorAll('.review-item')].every((item) => item.classList.contains('risk-medium')))
  doc.querySelectorAll('.risk-tabs button')[3].click()
  await wait()
  assert.ok(doc.querySelectorAll('.review-item').length > 0)
  assert.ok([...doc.querySelectorAll('.review-item')].every((item) => item.classList.contains('risk-low')))
  doc.querySelector('.nav-item[href="#profile"]').click()
  await wait()
  assert.equal(doc.querySelectorAll('.doctor-row').length, 3)
  assert.equal(doc.querySelectorAll('.trend-summary > div').length, 4)
  assert.ok(doc.querySelector('.rolling-line'))
  assert.equal(doc.querySelectorAll('.sample-bars rect').length, 30)
  doc.querySelectorAll('.doctor-row')[1].click()
  await wait()
  assert.ok(doc.querySelector('.profile-identity').textContent.includes('dr-2091'))
  assert.equal(errors.length, 0)
  console.log(
    'Compiled offline preview: all runtime assertions passed, including consultation switching and review priorities (DOM, not visual browser QA)',
  )
} finally {
  dom.window.close()
}

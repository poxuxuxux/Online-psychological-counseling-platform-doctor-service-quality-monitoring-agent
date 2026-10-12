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
  assert.ok(doc.querySelector('.consultation-photo').src.startsWith('data:image/png;base64,'))
  doc.querySelector('.hero-secondary').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '评价指标')
  doc.querySelector('.nav-item[href="#overview"]').click()
  await wait()
  doc.querySelector('.rail-links button:last-child').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '人工复核')
  doc.querySelector('.nav-item[href="#overview"]').click()
  await wait()
  doc.querySelector('.hero-start').click()
  await wait()
  assert.equal(doc.querySelector('h1').textContent, '评估工作台')
  assert.equal(doc.querySelectorAll('.conversation-message').length, 6)
  doc.querySelector('.heading-actions .primary').click()
  await wait()
  assert.equal(doc.querySelectorAll('.finding-row').length, 7)
  ;[...doc.querySelectorAll('.finding-row')].find((e) => e.textContent.includes('D4.1')).click()
  await wait()
  assert.equal(doc.querySelectorAll('.discussion-list li').length, 4)
  assert.equal(doc.querySelectorAll('.revision-compare article').length, 2)
  doc.querySelector('.finding-detail .evidence-actions button').click()
  await wait()
  assert.ok(doc.querySelector('#message-preview-m2').classList.contains('highlighted'))
  assert.equal(errors.length, 0)
  console.log('Compiled offline preview: 16 runtime checks passed (DOM, not visual browser QA)')
} finally {
  dom.window.close()
}

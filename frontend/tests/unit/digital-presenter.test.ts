// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DigitalReportPresenter from '../../src/components/feedback/DigitalReportPresenter.vue'
import { previewReport, previewSession } from '../../src/data/preview'
import { reportNarration, speechChunks, spokenReportText } from '../../src/utils/reportNarration'
import { ReportSchema } from '../../src/api/contracts/evaluation'
import fixture from '../fixtures/leader-report.json'

afterEach(() => vi.unstubAllGlobals())

function speechMock() {
  const spoken: SpeechSynthesisUtterance[] = []
  const voice = { lang: 'zh-CN', localService: true, name: 'Chinese' }
  const engine = {
    getVoices: vi.fn(() => [voice]), addEventListener: vi.fn(), removeEventListener: vi.fn(),
    speak: vi.fn((text: SpeechSynthesisUtterance) => spoken.push(text)),
    cancel: vi.fn(), pause: vi.fn(), resume: vi.fn(),
  }
  class Utterance { constructor(public text: string) {} }
  vi.stubGlobal('speechSynthesis', engine)
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance)
  return { engine, spoken }
}

describe('report narration', () => {
  it('reads scores, percentages and metric names as natural spoken Chinese', () => {
    expect(spokenReportText('D4.1：3.44/5，完成率85.7%。')).toBe('情绪识别与回应指标：三点四四分，满分五分，完成率百分之八十五点七。')
    expect(spokenReportText('**综合分** 68.8 / 100分')).toBe('综合分 六十八点八分，满分一百分')
    expect(spokenReportText('日期2026/5/1，地址1.2.3.4')).toBe('日期2026/5/1，地址1.2.3.4')
  })
  it('groups short sentences into one utterance instead of resetting the voice on every sentence', () => {
    expect(speechChunks('你好。我是小鉴。接下来一起看看报告。')).toEqual(['你好。我是小鉴。接下来一起看看报告。'])
  })
  it('converts an eligible five-point total to the same hundred-point score as the page', () => {
    expect(reportNarration(ReportSchema.parse(fixture))).toContain('综合评分为80分')
  })
  it('announces missing and failed scores without inventing a total', () => {
    const report = previewReport(previewSession())
    report.status = 'partial'
    report.quality_profile = null
    expect(reportNarration(report)).toContain('尚未形成可展示的综合分')
    expect(reportNarration(report)).toContain(spokenReportText(report.summary))
    report.status = 'failed'
    expect(reportNarration(report)).toContain('评价执行未完成')
    expect(reportNarration(report)).not.toContain('综合评分为')
    expect(reportNarration(null)).toBe('')
  })
  it('keeps long speech chunks within 120 characters without losing text', () => {
    const text = '很'.repeat(260) + '好。下一句！'
    const chunks = speechChunks(text)
    expect(chunks.every(chunk => Array.from(chunk).length <= 120)).toBe(true)
    expect(chunks.join('')).toBe(text)
  })
})

describe('digital presenter playback', () => {
  it('can speak explicitly labeled offline text without a backend report', async () => {
    const { spoken } = speechMock()
    const wrapper = mount(DigitalReportPresenter, { props: { demoText: '离线示例摘要。' } })
    await flushPromises()
    expect(wrapper.text()).toContain('离线演示')
    await wrapper.get('.presenter-play').trigger('click')
    expect(spoken[0]?.text).toContain('离线合成数据')
    wrapper.unmount()
  })
  it('starts only on click and supports pause, resume, stop and report replacement', async () => {
    const { engine, spoken } = speechMock()
    const wrapper = mount(DigitalReportPresenter, { props: { report: previewReport(previewSession()) } })
    await flushPromises()
    expect(engine.speak).not.toHaveBeenCalled()
    await wrapper.findAll('select')[0]!.setValue('Chinese')
    await wrapper.findAll('select')[1]!.setValue('1.1')
    await wrapper.get('.presenter-play').trigger('click')
    expect(engine.speak).toHaveBeenCalledTimes(1)
    expect(spoken[0]?.lang).toBe('zh-CN')
    expect(spoken[0]?.voice?.name).toBe('Chinese')
    expect(spoken[0]?.rate).toBe(1.1)
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(engine.pause).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('继续播报')
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(engine.resume).toHaveBeenCalledOnce()
    await wrapper.findAll('button')[2]!.trigger('click')
    expect(engine.cancel).toHaveBeenCalledOnce()
    await wrapper.get('.presenter-play').trigger('click')
    const oldEnd = spoken.at(-1)!.onend!
    await wrapper.setProps({ report: null })
    expect(engine.cancel).toHaveBeenCalledTimes(2)
    oldEnd.call(spoken.at(-1)!, {} as SpeechSynthesisEvent)
    expect(engine.speak).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.presenter-play').attributes('disabled')).toBeDefined()
    wrapper.unmount()
    expect(engine.removeEventListener).toHaveBeenCalledOnce()
  })
  it('stops on unmount and shows voice playback errors', async () => {
    const { engine, spoken } = speechMock()
    const wrapper = mount(DigitalReportPresenter, { props: { report: previewReport(previewSession()) } })
    await flushPromises()
    await wrapper.get('.presenter-play').trigger('click')
    spoken[0]!.onerror!.call(spoken[0]!, {} as SpeechSynthesisErrorEvent)
    await flushPromises()
    expect(wrapper.text()).toContain('语音播放未完成')
    await wrapper.get('.presenter-play').trigger('click')
    wrapper.unmount()
    expect(engine.cancel).toHaveBeenCalledOnce()
  })
  it('provides text and disables speech when the browser does not support it', () => {
    const wrapper = mount(DigitalReportPresenter, { props: { report: previewReport(previewSession()) } })
    expect(wrapper.text()).toContain('暂不支持语音播报')
    expect(wrapper.get('.presenter-play').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('plays all chunks in order and allows replay after completion', async () => {
    const { engine, spoken } = speechMock()
    const wrapper = mount(DigitalReportPresenter, { props: { report: previewReport(previewSession()) } })
    await flushPromises()
    await wrapper.get('.presenter-play').trigger('click')
    let index = 0
    while (index < spoken.length && index < 100) {
      const item = spoken[index++]!
      item.onend!.call(item, {} as SpeechSynthesisEvent)
    }
    await flushPromises()
    expect(wrapper.text()).toContain('本次播报已结束')
    expect(spoken.map(item => item.text).join('')).toBe(speechChunks(reportNarration(wrapper.props('report') ?? null)).join(''))
    const count = spoken.length
    await wrapper.get('.presenter-play').trigger('click')
    expect(engine.speak).toHaveBeenCalledTimes(count + 1)
    wrapper.unmount()
  })
})

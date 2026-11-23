// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MediaTranscriptImport from '../../src/components/workspace/MediaTranscriptImport.vue'

afterEach(() => vi.unstubAllGlobals())
it('requires transcript and speaker confirmation before emitting a text session', async () => {
  vi.stubGlobal('crypto', webcrypto)
  const fetch = vi.fn(async () => new Response(JSON.stringify({
    text: '医生您好。\n最近睡不好。', duration_seconds: 10,
    model: 'qwen3-asr-flash', source_modality: 'video', timestamps_available: false,
  })))
  vi.stubGlobal('fetch', fetch)
  const wrapper = mount(MediaTranscriptImport)
  const input = wrapper.get('input[type=file]')
  const file = new File(['mock-video'], 'session.mp4', { type: 'video/mp4' })
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
  const transcribe = wrapper.findAll('button').find(b => b.text() === '开始转写')!
  await transcribe.trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledOnce()
  expect(fetch.mock.calls[0]).toBeDefined()
  const confirm = wrapper.findAll('button').find(b => b.text() === '确认并导入会话')!
  expect(confirm.attributes('disabled')).toBeDefined()
  expect(wrapper.get('select').element.value).toBe('unknown')
  await wrapper.get('select').setValue('patient')
  await wrapper.get('input[type=checkbox]').setValue(true)
  await confirm.trigger('click')
  const session = wrapper.emitted('imported')![0]![0] as {
    observation_complete: boolean; messages: { role: string; timestamp: null; modality: string }[];
    service_context: { visual_analysis: boolean; transcript_source: string };
  }
  expect(session.observation_complete).toBe(false)
  expect(session.messages[0]).toMatchObject({ role: 'patient', timestamp: null, modality: 'text' })
  expect(session.service_context).toMatchObject({ visual_analysis: false, transcript_source: 'video' })
  expect(confirm.attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

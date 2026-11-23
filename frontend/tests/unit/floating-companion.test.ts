// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FloatingDigitalCompanion from '../../src/components/feedback/FloatingDigitalCompanion.vue'

beforeEach(() => localStorage.removeItem('xin-jian-companion-position-v1'))
afterEach(() => vi.unstubAllGlobals())

it('opens offline report narration, minimizes and closes with Escape', async () => {
  const wrapper = mount(FloatingDigitalCompanion, { props: { report: null, preview: true } })
  expect(wrapper.find('.companion-panel').exists()).toBe(false)
  await wrapper.get('.pet-avatar').trigger('click')
  expect(wrapper.find('.companion-panel').exists()).toBe(true)
  expect(wrapper.text()).toContain('离线演示')
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  await flushPromises()
  expect(wrapper.find('.companion-panel').exists()).toBe(false)
  await wrapper.get('.pet-size-toggle').trigger('click')
  await flushPromises()
  expect(wrapper.get('.companion-pet').classes()).toContain('minimized')
  expect(JSON.parse(localStorage.getItem('xin-jian-companion-position-v1')!).minimized).toBe(true)
  wrapper.unmount()
})

it('drags within the viewport, saves its position and does not open after dragging', async () => {
  const wrapper = mount(FloatingDigitalCompanion, { props: { report: null, preview: false } })
  const avatar = wrapper.get('.pet-avatar')
  Object.defineProperty(avatar.element, 'setPointerCapture', { value: vi.fn() })
  await avatar.trigger('pointerdown', { button: 0, pointerId: 1, clientX: 800, clientY: 500 })
  await avatar.trigger('pointermove', { pointerId: 1, clientX: -1000, clientY: -1000 })
  await avatar.trigger('pointerup', { pointerId: 1 })
  await avatar.trigger('click')
  expect(wrapper.get('.companion-pet').attributes('style')).toContain('left: 8px')
  expect(wrapper.find('.companion-panel').exists()).toBe(false)
  const saved = JSON.parse(localStorage.getItem('xin-jian-companion-position-v1')!)
  expect(saved.x).toBe(8)
  expect(saved.y).toBe(8)
  wrapper.unmount()
})

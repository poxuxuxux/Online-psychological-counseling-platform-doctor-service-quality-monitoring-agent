import { afterEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { request } from '../../src/api/client/http'
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
describe('API error handling', () => {
  it('validates responses before use', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }))),
    )
    expect(await request('/health', z.object({ status: z.string() }))).toEqual({ status: 'ok' })
  })
  it('rejects malformed responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ wrong: true }))))
    await expect(request('/health', z.object({ status: z.string() }))).rejects.toThrow(
      '数据格式不兼容',
    )
  })
  it('does not show submitted patient text from validation bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'private-content' }), { status: 422 }),
        ),
    )
    await expect(request('/api', z.object({}))).rejects.toThrow('数据格式与后端约定不一致')
  })
  it('does not retry mutation requests automatically', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('network'))
    vi.stubGlobal('fetch', fetch)
    await expect(request('/api', z.object({}), { method: 'POST' })).rejects.toThrow('无法连接服务')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('warns that timed-out mutations may still execute on the server', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, options) =>
          new Promise((_resolve, reject) =>
            options.signal.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            ),
          ),
      ),
    )
    const pending = request('/api', z.object({}), { method: 'POST' }, 20)
    const result = expect(pending).rejects.toThrow('评估可能仍在服务端执行')
    await vi.advanceTimersByTimeAsync(21)
    await result
  })
})

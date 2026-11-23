// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { evaluateUploaded, recoverUpload } from '../../src/api/guestJobs'
import { previewReport, previewSession } from '../../src/data/preview'

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('crypto', webcrypto)
})
afterEach(() => vi.unstubAllGlobals())

it('restores completed uploads from a capability without posting the dialogue again', async () => {
  const session = previewSession()
  const report = previewReport(session)
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/ready') return new Response(JSON.stringify({ capabilities: { guest_jobs: true } }))
    if (url === '/api/v1/guest/jobs')
      return new Response(JSON.stringify({ job_id: 'abc', token: 'capability' }))
    expect(options?.headers).toMatchObject({ 'X-Guest-Token': 'capability' })
    return new Response(JSON.stringify({ job_id: 'abc', status: 'completed', stage: 'done',
      model_calls: 10, elapsed_seconds: 1, report, error: null }))
  })
  vi.stubGlobal('fetch', fetch)
  await evaluateUploaded(session, vi.fn())
  await evaluateUploaded(session, vi.fn())
  await recoverUpload(vi.fn())
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/guest/jobs')).toHaveLength(1)
  const stored = localStorage.getItem('xin-heng-upload-jobs-v1')!
  expect(stored).toContain('capability')
  expect(stored).not.toContain(session.messages[0]!.content)
})

it('retains a recoverable job after polling fails, without silently resubmitting', async () => {
  const fetch = vi.fn(async (url: string) => {
    if (url === '/ready') return new Response(JSON.stringify({ capabilities: { guest_jobs: true } }))
    if (url === '/api/v1/guest/jobs')
      return new Response(JSON.stringify({ job_id: 'abc', token: 'capability' }))
    throw new Error('disconnected')
  })
  vi.stubGlobal('fetch', fetch)
  await expect(evaluateUploaded(previewSession(), vi.fn())).rejects.toThrow('找回上传评价')
  await expect(recoverUpload(vi.fn())).rejects.toThrow('找回上传评价')
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/guest/jobs')).toHaveLength(1)
})

it.each(['completed', 'running'] as const)('explicit new run handles existing %s job safely', async (status) => {
  const session = previewSession()
  const report = previewReport(session)
  report.status = 'failed'
  let creations = 0
  let priorRunning = false
  const fetch = vi.fn(async (url: string) => {
    if (url === '/ready') return new Response(JSON.stringify({ capabilities: { guest_jobs: true } }))
    if (url === '/api/v1/guest/jobs') {
      creations++
      return new Response(JSON.stringify({ job_id: 'job' + creations, token: 'token' + creations }))
    }
    const running = url.endsWith('job1') && priorRunning
    return new Response(JSON.stringify({ job_id: url.split('/').at(-1),
      status: running ? 'running' : 'completed', stage: running ? 'initial' : 'done',
      model_calls: 10, elapsed_seconds: 1, report: running ? null : report, error: null }))
  })
  vi.stubGlobal('fetch', fetch)
  await evaluateUploaded(session, vi.fn())
  priorRunning = status === 'running'
  if (priorRunning) {
    await expect(evaluateUploaded(session, vi.fn(), true)).rejects.toThrow('正在运行')
    expect(creations).toBe(1)
  } else {
    await evaluateUploaded(session, vi.fn(), true)
    expect(creations).toBe(2)
    const entries = JSON.parse(localStorage.getItem('xin-heng-upload-jobs-v1')!)
    expect(entries.map((e: { job_id: string }) => e.job_id)).toEqual(['job2', 'job1'])
  }
})

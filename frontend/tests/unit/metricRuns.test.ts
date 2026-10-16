// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import MetricRunsPage from '../../src/pages/MetricRunsPage.vue'
import { metricRunsApi } from '../../src/api/endpoints/metricRuns'
import { previewSession } from '../../src/data/preview'

vi.mock('../../src/api/endpoints/metricRuns', () => ({
  metricRunsApi: {
    capabilities: vi.fn(),
    seed: vi.fn(),
    round: vi.fn(),
    create: vi.fn(),
    status: vi.fn(),
    report: vi.fn(),
  },
}))

let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  vi.mocked(metricRunsApi.capabilities).mockResolvedValue({ enabled: true, source: 'server_synthetic_only' })
  vi.mocked(metricRunsApi.seed).mockResolvedValue({ round_id: 'synthetic-round', source_kind: 'server_synthetic' })
  vi.mocked(metricRunsApi.round).mockResolvedValue({
    id: 'synthetic-round',
    source_kind: 'server_synthetic',
    data: { ...previewSession(), session_id: 'synthetic-round' },
  })
  vi.mocked(metricRunsApi.create).mockResolvedValue({ run_id: 'run-1', status: 'queued' })
  vi.mocked(metricRunsApi.status).mockResolvedValue({
    id: 'run-1',
    round_id: 'synthetic-round',
    status: 'partial',
    error: null,
    events: [{ seq: 1, stage: 'partial', created_at: '2026-10-16T00:00:00Z' }],
  })
  vi.mocked(metricRunsApi.report).mockResolvedValue({
    evaluation_id: 'run-1',
    session_id: 'synthetic-round',
    status: 'partial',
    rubric: { version: 'draft-v1', metrics: [{ metric_id: 'D4.1', name: '情绪识别与回应', scoring_status: 'draft' }] },
    agent_results: [{ agent_id: 'empathy_relationship', status: 'completed', findings: [{ finding_id: 'f-1', metric_id: 'D4.1', score: null, rationale: '合成观察', evidence: [{ message_ids: ['demo-m02'], quote: '合成引文' }] }] }],
    checks: [{ metric_id: 'D4.1', finding_id: 'f-1', status: 'supported' }],
    adopted_findings: { 'D4.1': 'f-1' },
    summary: '合成摘要',
    limitations: ['scoring_rules_not_configured'],
    unresolved_metrics: [],
    overall_score: null,
  })
})
afterEach(() => {
  wrapper?.unmount()
  sessionStorage.clear()
})

it('submits a synthetic run and renders the returned draft report without inventing scores', async () => {
  wrapper = mount(MetricRunsPage, { props: { preview: false } })
  await flushPromises()
  await wrapper.get('input[type="password"]').setValue('operator-only-code')
  await wrapper.get('.metric-controls .primary').trigger('click')
  await flushPromises()

  expect(metricRunsApi.seed).toHaveBeenCalledWith('operator-only-code', false)
  expect(metricRunsApi.create).toHaveBeenCalledWith('operator-only-code', 'synthetic-round', expect.any(String))
  expect(sessionStorage.getItem('xin-heng-metric-run-id')).toBe('run-1')
  expect(wrapper.text()).toContain('合成摘要')
  expect(wrapper.text()).toContain('总分尚不可用')
  expect(wrapper.text()).toContain('合成引文')
})

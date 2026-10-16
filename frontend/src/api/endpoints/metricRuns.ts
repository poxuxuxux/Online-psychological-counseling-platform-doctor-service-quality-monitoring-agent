import { request } from '../client/http'
import {
  CreatedRunSchema,
  MetricCapabilitiesSchema,
  MetricReportSchema,
  MetricRoundSchema,
  MetricRunSchema,
  SeededRoundSchema,
} from '../contracts/metricRuns'

const headers = (code: string) => ({ 'X-Metric-Runs-Key': code })

export const metricRunsApi = {
  capabilities: () => request('/api/v1/metric-runs/capabilities', MetricCapabilitiesSchema),
  seed: (code: string, followUp: boolean) =>
    request(
      `/api/v1/rounds/${followUp ? 'demo-follow-up' : 'demo'}`,
      SeededRoundSchema,
      { method: 'POST', headers: headers(code) },
    ),
  round: (code: string, id: string) =>
    request(`/api/v1/rounds/${encodeURIComponent(id)}`, MetricRoundSchema, {
      headers: headers(code),
    }),
  create: (code: string, roundId: string, idempotencyKey: string) =>
    request(
      '/api/v1/evaluation-runs',
      CreatedRunSchema,
      {
        method: 'POST',
        headers: {
          ...headers(code),
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({ round_id: roundId }),
      },
    ),
  status: (code: string, id: string) =>
    request(`/api/v1/evaluation-runs/${encodeURIComponent(id)}`, MetricRunSchema, {
      headers: headers(code),
    }),
  report: (code: string, id: string) =>
    request(`/api/v1/evaluation-runs/${encodeURIComponent(id)}/report`, MetricReportSchema, {
      headers: headers(code),
    }),
}

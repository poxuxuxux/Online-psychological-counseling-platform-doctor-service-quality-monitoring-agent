import { z } from 'zod'
import { SessionSchema } from './evaluation'

export const MetricCapabilitiesSchema = z.object({
  enabled: z.boolean(),
  source: z.literal('server_synthetic_only'),
})
export const SeededRoundSchema = z.object({
  round_id: z.string(),
  source_kind: z.literal('server_synthetic'),
})
export const MetricRoundSchema = z.object({
  id: z.string(),
  source_kind: z.literal('server_synthetic'),
  data: SessionSchema,
})
export const CreatedRunSchema = z.object({ run_id: z.string(), status: z.string() })
export const MetricRunSchema = z.object({
  id: z.string(),
  round_id: z.string(),
  status: z.string(),
  error: z.string().nullable(),
  events: z.array(z.object({ seq: z.number(), stage: z.string(), created_at: z.string() })),
})
const MetricFindingSchema = z.object({
  finding_id: z.string(),
  metric_id: z.string(),
  score: z.number().nullable(),
  rationale: z.string(),
  evidence: z.array(z.object({ message_ids: z.array(z.string()), quote: z.string() })).default([]),
})
export const MetricReportSchema = z.object({
  evaluation_id: z.string(),
  session_id: z.string(),
  status: z.string(),
  rubric: z.object({
    version: z.string(),
    metrics: z.array(z.object({ metric_id: z.string(), name: z.string(), scoring_status: z.string() })),
  }),
  agent_results: z.array(
    z.object({ agent_id: z.string(), status: z.string(), findings: z.array(MetricFindingSchema) }),
  ),
  checks: z.array(
    z.object({ metric_id: z.string(), finding_id: z.string(), status: z.string(), reason: z.string().optional() }),
  ),
  adopted_findings: z.record(z.string(), z.string()).default({}),
  summary: z.string(),
  limitations: z.array(z.string()),
  unresolved_metrics: z.array(z.string()).default([]),
  overall_score: z.number().nullable(),
})

export type MetricRun = z.infer<typeof MetricRunSchema>
export type MetricReport = z.infer<typeof MetricReportSchema>
export type MetricRound = z.infer<typeof MetricRoundSchema>

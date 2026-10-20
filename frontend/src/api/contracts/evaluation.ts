// 环节：前端 API 契约层；用途：定义前后端共享的数据结构和 TypeScript 类型。
import { z } from 'zod'

const strings = z.array(z.string()).default([])
const score = z.number().min(0).max(5).nullable().default(null)
const coverage = z.number().min(0).max(1).default(0)
export const EvidenceSchema = z.object({
  message_ids: strings,
  quote: z.string(),
  explanation: z.string().default(''),
  media_time_ranges: z
    .array(
      z.object({ start_seconds: z.number().nonnegative(), end_seconds: z.number().nonnegative() }),
    )
    .default([]),
})
export const MessageSchema = z
  .object({
    message_id: z.string().min(1),
    role: z.enum(['doctor', 'patient', 'system', 'unknown']).default('unknown'),
    modality: z.enum(['text', 'audio', 'video']).default('text'),
    content: z.string(),
    sequence: z.number().int().nonnegative(),
    timestamp: z.string().nullable().optional(),
    redaction_applied: z.boolean().default(false),
  })
  .passthrough()
export const SessionSchema = z
  .object({
    session_id: z.string().min(1),
    source_id: z.string().nullable().optional(),
    anonymized_patient_ref: z.string().nullable().optional(),
    consultation_round: z.enum(['initial', 'follow_up', 'unknown']).default('unknown'),
    messages: z.array(MessageSchema),
    imported_at: z.string().nullable().optional(),
  })
  .passthrough()
  .superRefine((session, ctx) => {
    const ids = session.messages.map((m) => m.message_id)
    if (new Set(ids).size !== ids.length)
      ctx.addIssue({ code: 'custom', message: '消息编号必须唯一', path: ['messages'] })
  })
export const FindingSchema = z.object({
  finding_id: z.string().min(1),
  metric_id: z.string().min(1),
  metric_version: z.string().nullable().optional(),
  attempt: z.number().int().min(0).max(1).default(0),
  supersedes_finding_id: z.string().nullable().optional(),
  applicability: z
    .enum(['applicable', 'not_applicable', 'insufficient_context'])
    .default('applicable'),
  score,
  rationale: z.string(),
  evidence: z.array(EvidenceSchema).default([]),
  knowledge_refs: z
    .array(
      z.object({
        source_id: z.string(),
        title: z.string(),
        excerpt: z.string(),
        version: z.string().nullable().optional(),
      }),
    )
    .default([]),
  confidence_band: z.enum(['high', 'medium', 'low']).nullable().optional(),
  limitations: strings,
})
export const VerificationSchema = z.object({
  verification_id: z.string().optional(),
  finding_id: z.string(),
  verifier_version: z.string().nullable().optional(),
  reference_status: z.enum(['valid', 'missing', 'quote_mismatch', 'source_mismatch', 'uncertain']),
  claims: z
    .array(
      z.object({
        claim_id: z.string(),
        finding_id: z.string(),
        statement: z.string(),
        claim_type: z.string(),
        subject_role: z.enum(['doctor', 'patient', 'system', 'unknown']).nullable().optional(),
        behavior: z.string().nullable().optional(),
        object_text: z.string().nullable().optional(),
        time_scope: z.string().nullable().optional(),
        negated: z.boolean().default(false),
        qualifiers: strings,
      }),
    )
    .default([]),
  claim_results: z
    .array(
      z.object({
        claim_id: z.string(),
        status: z.enum(['supported', 'contradicted', 'insufficient_evidence']),
        supporting_evidence: z.array(EvidenceSchema).default([]),
        contradicting_evidence: z.array(EvidenceSchema).default([]),
        rationale: z.string().default(''),
      }),
    )
    .default([]),
  reference_conflict: z.boolean().default(false),
  applicability_status: z.enum(['matched', 'mismatched', 'uncertain']).default('uncertain'),
  rubric_status: z.enum(['matched', 'mismatched', 'uncertain']).default('uncertain'),
  support_status: z.enum(['supported', 'partial', 'unsupported', 'uncertain']),
  issues: strings,
  revision_request: z.string().nullable().optional(),
})
// Optional fields are forward-compatible presentation contracts, not new Agents or endpoints.
export const DiscussionSchema = z.object({
  finding_id: z.string(),
  role: z.enum(['evaluator', 'verifier', 'arbiter']),
  text: z.string(),
  message_ids: strings,
  timestamp: z.string().nullable().optional(),
})
export const ArbitrationSchema = z.object({
  conflict_id: z.string(),
  metric_ids: strings,
  status: z.enum(['resolved', 'unresolved', 'not_needed']),
  adopted: z
    .enum(['initial', 're_evaluated', 'verification', 'manual_review'])
    .nullable()
    .optional(),
  rationale: z.string().default(''),
  requires_manual_review: z.boolean().default(false),
})
export const ReportSchema = z
  .object({
    evaluation_id: z.string().min(1),
    session_id: z.string().min(1),
    status: z.enum(['completed', 'partial', 'failed']),
    agent_results: z
      .array(
        z.object({
          agent_id: z.string(),
          status: z.enum(['completed', 'partial', 'failed']),
          findings: z.array(FindingSchema).default([]),
          error: z.string().nullable().optional(),
        }),
      )
      .default([]),
    verification_results: z.array(VerificationSchema).default([]),
    summary: z.string().default(''),
    limitations: strings,
    quality_profile: z
      .object({
        dimensions: z
          .array(z.object({ dimension_id: z.string(), name: z.string(), score, coverage }))
          .default([]),
        overall_score: score,
        overall_coverage: coverage,
        coverage_gate_passed: z.boolean().default(false),
      })
      .nullable()
      .optional(),
    improvements: z
      .array(
        z.object({
          target_id: z.string(),
          level: z.string(),
          suggestion: z.string(),
          related_evidence: z.array(EvidenceSchema).default([]),
        }),
      )
      .default([]),
    review_required: z.boolean().default(false),
    review_reasons: strings,
    team: z.object({
      model_call_count: z.number(),
      stop_reason: z.string().nullable().optional(),
      usage: z.object({
        requests: z.number(),
        input_characters: z.number(),
        prompt_tokens: z.number(),
        completion_tokens: z.number(),
        usage_reported_requests: z.number(),
      }).optional(),
    }).optional(),
    investigation: z.object({
      stop_reason: z.string(),
      uncovered_metric_ids: strings,
      attempts: z.record(z.string(), z.number()),
      model_call_count: z.number().optional(),
      model_call_limit: z.number().optional(),
      metric_statuses: z.record(z.string(), z.enum([
        'evaluated', 'not_applicable', 'insufficient_evidence', 'manual_review',
      ])).optional(),
      preflight_history: z.object({
        required: z.boolean(), status: z.string(), issues: strings,
      }).optional(),
      observations: z.array(z.object({
        step: z.number(),
        action: z.string(),
        question: z.string(),
        status: z.string(),
        issues: strings.optional(),
        metric_ids: strings.optional(),
        tool_name: z.string().optional(),
        verification: z.array(z.object({
          metric_id: z.string(), status: z.string(), reason: z.string(),
        })).optional(),
      }).passthrough()),
    }).nullable().optional(),
    summary_status: z
      .enum(['completed', 'partial', 'failed', 'not_configured', 'skipped'])
      .nullable()
      .optional(),
    arbitration_status: z
      .enum(['not_needed', 'resolved', 'unresolved', 'not_configured'])
      .nullable()
      .optional(),
    discussions: z.array(DiscussionSchema).default([]),
    arbitration_decisions: z.array(ArbitrationSchema).default([]),
  })
  .superRefine((report, ctx) => {
    const ids = report.agent_results.flatMap((a) => a.findings.map((f) => f.finding_id))
    if (new Set(ids).size !== ids.length)
      ctx.addIssue({ code: 'custom', message: '评价结果编号重复', path: ['agent_results'] })
  })
export const RecentSchema = z.object({
  database_configured: z.boolean(),
  items: z.array(
    z.object({
      evaluation_id: z.string(),
      session_id: z.string(),
      status: z.enum(['completed', 'partial', 'failed']),
      created_at: z.string(),
    }),
  ),
})
export const ReadySchema = z
  .object({
    status: z.string(),
    database: z
      .object({
        configured: z.boolean(),
        connected: z.boolean(),
        backend: z.enum(['postgresql', 'sqlite']).optional(),
        checked_at: z.string().optional(),
      })
      .passthrough(),
    model: z.object({ configured: z.boolean() }).optional(),
  })
  .passthrough()
export type Session = z.infer<typeof SessionSchema>
export type Finding = z.infer<typeof FindingSchema>
export type Evidence = z.infer<typeof EvidenceSchema>
export type Verification = z.infer<typeof VerificationSchema>
export type Report = z.infer<typeof ReportSchema>
export type Recent = z.infer<typeof RecentSchema>
export type Ready = z.infer<typeof ReadySchema>

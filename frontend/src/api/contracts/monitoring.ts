// 环节：前端 API 契约层；用途：定义医生画像与监测预警的前后端共享结构。
import { z } from 'zod'
const count = z.number().int().nonnegative()
const score = z.number().min(0).max(100).nullable()
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const riskLevel = z.enum(['high', 'medium', 'low', 'unknown']).nullable()
const alertLevel = z.enum(['high', 'medium'])

const dimensions = z
  .array(
    z.object({
      dimension_id: z.string().min(1),
      name: z.string(),
      average: score,
      sample_count: count,
    }),
  )
  .min(1)

const trend = z.array(z.object({ date, average: score, sample_count: count }))

export const MonitoringListSchema = z
  .object({
    available: z.boolean(),
    source: z.enum(['postgresql', 'sqlite', 'offline-preview']),
    days: z.number().int().min(7).max(365),
    period_start: date,
    period_end: date,
    timezone: z.literal('Asia/Shanghai'),
    generated_at: z.string(),
    rubric_version: z.string().nullable(),
    policy_version: z.literal('monitoring-v1'),
    doctor_count: count,
    alert_counts: z.object({ high: count, medium: count }),
    excluded_missing_doctor_id: count,
    doctors: z.array(
      z.object({
        doctor_id: z.string().min(1),
        session_count: count,
        scored_count: count,
        average_total: score,
        latest_score: score,
        latest_date: date.nullable(),
        latest_risk: riskLevel,
        alerts: z.array(z.object({ rule_id: z.string(), level: alertLevel })),
      }),
    ),
  })
  .superRefine((data, ctx) => {
    if (data.doctor_count !== data.doctors.length)
      ctx.addIssue({ code: 'custom', message: '医生数量不一致' })
  })

export const DoctorProfileSchema = z
  .object({
    available: z.boolean(),
    source: z.enum(['postgresql', 'sqlite', 'offline-preview']),
    days: z.number().int().min(7).max(365),
    period_start: date,
    period_end: date,
    timezone: z.literal('Asia/Shanghai'),
    generated_at: z.string(),
    rubric_version: z.string().nullable(),
    policy_version: z.literal('monitoring-v1'),
    doctor_id: z.string().min(1),
    counts: z.object({
      in_window: count,
      comparable: count,
      scored: count,
      pending_review: count,
      other_version: count,
    }),
    average_total: score,
    latest_score: score,
    latest_date: date.nullable(),
    latest_risk: riskLevel,
    dimensions,
    trend,
    sessions: z.array(
      z.object({
        session_id: z.string().nullable(),
        date,
        overall_score: z.number().min(0).max(5).nullable(),
        risk_level: riskLevel,
        review_required: z.boolean(),
        status: z.string(),
      }),
    ),
    alerts: z.array(
      z.object({
        rule_id: z.string(),
        level: alertLevel,
        message: z.string(),
        related_sessions: z.array(z.string()),
        last_seen: date.nullable(),
      }),
    ),
  })
  .superRefine((data, ctx) => {
    if (data.trend.length !== data.days)
      ctx.addIssue({ code: 'custom', message: '日期范围与天数不一致' })
    for (const point of [...data.dimensions, ...data.trend])
      if ((point.average === null) !== (point.sample_count === 0))
        ctx.addIssue({ code: 'custom', message: '样本数与均值不一致' })
  })

export type MonitoringList = z.infer<typeof MonitoringListSchema>
export type DoctorProfile = z.infer<typeof DoctorProfileSchema>

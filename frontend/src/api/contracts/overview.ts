import { z } from 'zod'
const count = z.number().int().nonnegative()
const score = z.number().min(0).max(100).nullable()
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
export const OverviewSchema = z
  .object({
    available: z.boolean(),
    source: z.enum(['postgresql', 'offline-preview']),
    days: z.number().int().min(1).max(90),
    period_start: date,
    period_end: date,
    timezone: z.literal('Asia/Shanghai'),
    generated_at: z.string(),
    rubric_version: z.string().nullable(),
    score_scale: z.literal(100),
    rules: z.object({ high_quality_min: z.literal(85), risk_below: z.literal(60) }),
    counts: z.object({
      evaluated: count.nullable(),
      scored: count.nullable(),
      high_quality: count.nullable(),
      risk: count.nullable(),
      pending: count.nullable(),
      other_version: count.nullable(),
      synthetic: count.nullable(),
    }),
    average_total: score,
    dimensions: z
      .array(
        z.object({
          dimension_id: z.enum(['D1', 'D2', 'D3', 'D4', 'D5', 'D6']),
          name: z.string(),
          average: score,
          sample_count: count,
        }),
      )
      .length(6),
    trend: z.array(z.object({ date, average: score, sample_count: count })),
  })
  .superRefine((data, ctx) => {
    const c = data.counts
    if (new Set(data.dimensions.map((d) => d.dimension_id)).size !== 6)
      ctx.addIssue({ code: 'custom', message: '维度重复' })
    if (data.available && Object.values(c).some((v) => v === null))
      ctx.addIssue({ code: 'custom', message: '统计计数缺失' })
    if (
      c.evaluated !== null &&
      c.scored !== null &&
      c.pending !== null &&
      c.other_version !== null &&
      (c.scored + c.pending + c.other_version !== c.evaluated ||
        (c.high_quality ?? 0) + (c.risk ?? 0) > c.scored ||
        (c.synthetic ?? 0) > c.evaluated)
    )
      ctx.addIssue({ code: 'custom', message: '统计计数不一致' })
    if (
      data.trend.length !== data.days ||
      new Set(data.trend.map((d) => d.date)).size !== data.days
    )
      ctx.addIssue({ code: 'custom', message: '日期范围不一致' })
    for (const point of [...data.dimensions, ...data.trend])
      if ((point.average === null) !== (point.sample_count === 0))
        ctx.addIssue({ code: 'custom', message: '样本数与均值不一致' })
  })
export type Overview = z.infer<typeof OverviewSchema>

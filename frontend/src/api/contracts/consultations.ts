// 环节：前端 API 契约层；用途：定义前后端共享的数据结构和 TypeScript 类型。
import { z } from 'zod'
import { SessionSchema, ReportSchema } from './evaluation'

export const ConsultationItemSchema = z.object({
  session_id: z.string().min(1),
  consultation_round: z.enum(['initial', 'follow_up', 'unknown']),
  message_count: z.number().int().nonnegative(),
  updated_at: z.string(),
  evaluation_status: z.enum(['completed', 'partial', 'failed']).nullable(),
})
export const ConsultationListSchema = z.object({
  database_configured: z.boolean(),
  total: z.number().int().nonnegative(),
  items: z.array(ConsultationItemSchema),
})
export const ConsultationDetailSchema = z
  .object({
    session: SessionSchema,
    report: ReportSchema.nullable(),
  })
  .superRefine((detail, ctx) => {
    if (detail.report && detail.report.session_id !== detail.session.session_id)
      ctx.addIssue({ code: 'custom', message: '咨询记录与报告不匹配', path: ['report'] })
  })
export type ConsultationItem = z.infer<typeof ConsultationItemSchema>
export type ConsultationDetail = z.infer<typeof ConsultationDetailSchema>

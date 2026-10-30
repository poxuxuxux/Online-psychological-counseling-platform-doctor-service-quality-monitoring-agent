// 环节：前端 API 接入层；用途：封装 HTTP 通信及后端业务接口调用。
import { z } from 'zod'
import { request } from '../client/http'
import { ConsultationListSchema, ConsultationDetailSchema } from '../contracts/consultations'
import {
  SessionSchema,
  ReportSchema,
  RecentSchema,
  ReadySchema,
  type Session,
} from '../contracts/evaluation'

export const api = {
  demoSessions: () => request('/api/v1/demo/sessions', z.array(SessionSchema)),
  demoDetail: (id: string) =>
    request(`/api/v1/demo/sessions/${encodeURIComponent(id)}`, ConsultationDetailSchema),
  reviews: (evaluationId: string) =>
    request(`/api/v1/evaluations/${encodeURIComponent(evaluationId)}/reviews`, z.object({
      items: z.array(z.object({
        review_id: z.string(), evaluation_id: z.string(), finding_id: z.string(),
        decision: z.string(), reason: z.string(), created_at: z.string(),
      })),
    })),
  addReview: (input: { evaluation_id: string; finding_id: string; decision: string; reason: string }) =>
    request(`/api/v1/evaluations/${encodeURIComponent(input.evaluation_id)}/reviews`,
      z.object({ review_id: z.string(), evaluation_id: z.string(), finding_id: z.string(),
        decision: z.string(), reason: z.string(), created_at: z.string() }),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) }),
  consultations: (offset = 0, query = '', limit = 5, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams({
      scope: 'private',
      limit: String(limit),
      offset: String(offset),
      query,
    })
    if (startDate && endDate) {
      params.set('start_date', startDate)
      params.set('end_date', endDate)
    }
    return request(`/api/v1/consultations?${params.toString()}`, ConsultationListSchema)
  },
  consultation: (id: string) =>
    request(`/api/v1/consultations/${encodeURIComponent(id)}`, ConsultationDetailSchema),
  importSession: (session: Session) =>
    request('/api/v1/sessions', z.object({ session_id: z.string() }), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(session),
    }),
  demo: () => request('/api/v1/demo/session', SessionSchema),
  evaluate: (session: Session) =>
    request(
      '/api/v1/evaluations',
      ReportSchema,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(session),
      },
      600000,
    ),
  evaluateGuest: (session: Session) =>
    request('/api/v1/guest/evaluations', ReportSchema, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(session),
    }, 600000),
  recent: () => request('/api/v1/evaluations/recent?limit=20', RecentSchema),
  health: () => request('/health', z.object({ status: z.string() })),
  ready: () => request('/ready', ReadySchema),
}

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
  consultations: (offset = 0, query = '') =>
    request(
      `/api/v1/consultations?limit=5&offset=${offset}&query=${encodeURIComponent(query)}`,
      ConsultationListSchema,
    ),
  consultation: (id: string) =>
    request(`/api/v1/consultations/${encodeURIComponent(id)}`, ConsultationDetailSchema),
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
      90000,
    ),
  recent: () => request('/api/v1/evaluations/recent?limit=20', RecentSchema),
  health: () => request('/health', z.object({ status: z.string() })),
  ready: () => request('/ready', ReadySchema),
}

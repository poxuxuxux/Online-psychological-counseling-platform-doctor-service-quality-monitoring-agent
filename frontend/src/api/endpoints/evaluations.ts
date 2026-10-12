import { z } from 'zod'
import { request } from '../client/http'
import {
  SessionSchema,
  ReportSchema,
  RecentSchema,
  ReadySchema,
  type Session,
} from '../contracts/evaluation'

export const api = {
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

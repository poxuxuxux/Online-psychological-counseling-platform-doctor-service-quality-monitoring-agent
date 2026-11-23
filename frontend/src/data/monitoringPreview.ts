// 环节：前端演示数据层；用途：提供医生画像离线合成样例，覆盖趋势、画像与预警路径。
import type { MonitoringList, DoctorProfile } from '../api/contracts/monitoring'

const DAYS = 180
const iso = (offset: number) =>
  new Date(Date.parse('2024-06-30T00:00:00Z') - offset * 86400000).toISOString().slice(0, 10)
const scale = (value: number) => Math.round(value * 20 * 100) / 100
const DIMENSIONS = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6']

type Risk = 'high' | 'medium' | 'low' | 'unknown'
type SessionSeed = { id: string; offset: number; score: number | null; risk: Risk; review: boolean }

function trendFrom(sessions: SessionSeed[]) {
  const map = new Map<number, number>()
  for (const session of sessions)
    if (session.score !== null) map.set(session.offset, session.score)
  return Array.from({ length: DAYS }, (_, i) => {
    const offset = DAYS - 1 - i
    const value = map.get(offset)
    return {
      date: iso(offset),
      average: value === undefined ? null : scale(value),
      sample_count: value === undefined ? 0 : 1,
    }
  })
}

function buildProfile(
  doctorId: string,
  sessions: SessionSeed[],
  dimensionScores: number[],
  alerts: DoctorProfile['alerts'],
): DoctorProfile {
  const scored = sessions.filter((s) => s.score !== null)
  const byOffset = [...sessions].sort((a, b) => a.offset - b.offset)
  const latestScored = [...scored].sort((a, b) => a.offset - b.offset).pop()
  const scores = scored.map((s) => s.score as number)
  const average = scores.length
    ? scale(scores.reduce((sum, value) => sum + value, 0) / scores.length)
    : null
  return {
    available: true,
    source: 'offline-preview',
    days: DAYS,
    period_start: iso(DAYS - 1),
    period_end: iso(0),
    timezone: 'Asia/Shanghai',
    generated_at: new Date().toISOString(),
    rubric_version: 'offline-preview',
    policy_version: 'monitoring-v1',
    doctor_id: doctorId,
    counts: {
      in_window: sessions.length,
      comparable: sessions.length,
      scored: scored.length,
      pending_review: sessions.length - scored.length,
      other_version: 0,
    },
    average_total: average,
    latest_score: latestScored && latestScored.score !== null ? scale(latestScored.score) : null,
    latest_date: latestScored ? iso(latestScored.offset) : null,
    latest_risk: byOffset[byOffset.length - 1]?.risk ?? null,
    dimensions: DIMENSIONS.map((dimension_id, i) => ({
      dimension_id,
      name: dimension_id,
      average: scored.length ? scale(dimensionScores[i]!) : null,
      sample_count: scored.length,
    })),
    trend: trendFrom(sessions),
    sessions: byOffset
      .slice()
      .reverse()
      .map(({ id, offset, score, risk, review }) => ({
        session_id: id,
        date: iso(offset),
        overall_score: score,
        risk_level: risk,
        review_required: review,
        status: review ? 'partial' : 'completed',
      })),
    alerts,
  }
}

const DECLINING_ALERTS: DoctorProfile['alerts'] = [
  {
    rule_id: 'latest_high_risk',
    level: 'high',
    message: '最近一次评价风险等级为高，需优先人工复核。',
    related_sessions: ['demo-session-1087-d'],
    last_seen: iso(20),
  },
  {
    rule_id: 'persistent_dimension_gap',
    level: 'high',
    message: '以下维度持续低于 3/5：D4（均值 2.4/5）。',
    related_sessions: ['demo-session-1087-c', 'demo-session-1087-d'],
    last_seen: iso(20),
  },
  {
    rule_id: 'score_decline',
    level: 'medium',
    message: '可信总分连续下滑（3.10 → 2.50，5 分制），需关注近期服务状态。',
    related_sessions: ['demo-session-1087-c', 'demo-session-1087-d'],
    last_seen: iso(20),
  },
  {
    rule_id: 'consecutive_risk_streak',
    level: 'medium',
    message: '最近 2 次评价风险均为中等及以上，建议持续观察。',
    related_sessions: ['demo-session-1087-c', 'demo-session-1087-d'],
    last_seen: iso(20),
  },
]

const PROFILES: Record<string, DoctorProfile> = {
  'dr-1087': buildProfile(
    'dr-1087',
    [
      { id: 'demo-session-1087-a', offset: 160, score: 4.2, risk: 'medium', review: false },
      { id: 'demo-session-1087-b', offset: 120, score: 3.7, risk: 'medium', review: false },
      { id: 'demo-session-1087-c', offset: 70, score: 3.1, risk: 'high', review: false },
      { id: 'demo-session-1087-d', offset: 20, score: 2.5, risk: 'high', review: false },
    ],
    [3.4, 3.8, 3.3, 2.4, 3.5, 3.2],
    DECLINING_ALERTS,
  ),
  'dr-2091': buildProfile(
    'dr-2091',
    [
      { id: 'demo-session-2091-a', offset: 150, score: 4.5, risk: 'low', review: false },
      { id: 'demo-session-2091-b', offset: 110, score: 4.6, risk: 'low', review: false },
      { id: 'demo-session-2091-c', offset: 65, score: 4.4, risk: 'low', review: false },
      { id: 'demo-session-2091-d', offset: 12, score: 4.7, risk: 'low', review: false },
    ],
    [4.6, 4.7, 4.5, 4.8, 4.6, 4.7],
    [],
  ),
  'dr-3050': buildProfile(
    'dr-3050',
    [
      { id: 'demo-session-3050-a', offset: 140, score: 4.3, risk: 'low', review: false },
      { id: 'demo-session-3050-b', offset: 95, score: null, risk: 'unknown', review: true },
      { id: 'demo-session-3050-c', offset: 55, score: null, risk: 'unknown', review: true },
      { id: 'demo-session-3050-d', offset: 30, score: null, risk: 'unknown', review: true },
      { id: 'demo-session-3050-e', offset: 5, score: 4.1, risk: 'low', review: false },
    ],
    [4.2, 4.0, 4.3, 4.1, 4.2, 4.0],
    [
      {
        rule_id: 'review_backlog',
        level: 'medium',
        message: '评价期内已有 3 份报告待人工复核，请关注积压。',
        related_sessions: ['demo-session-3050-b', 'demo-session-3050-c', 'demo-session-3050-d'],
        last_seen: iso(30),
      },
    ],
  ),
}

function summary(profile: DoctorProfile): MonitoringList['doctors'][number] {
  return {
    doctor_id: profile.doctor_id,
    session_count: profile.counts.in_window,
    scored_count: profile.counts.scored,
    average_total: profile.average_total,
    latest_score: profile.latest_score,
    latest_date: profile.latest_date,
    latest_risk: profile.latest_risk,
    alerts: profile.alerts.map(({ rule_id, level }) => ({ rule_id, level })),
  }
}

function profileForRange(profile: DoctorProfile, start: string, end: string): DoctorProfile | null {
  const sessions = profile.sessions.filter((session) => session.date >= start && session.date <= end)
  if (!sessions.length) return null
  const scored = sessions.filter((session) => session.overall_score !== null)
  const average = scored.length
    ? scale(scored.reduce((sum, session) => sum + session.overall_score!, 0) / scored.length)
    : null
  const latestScored = scored[0]
  const latest = sessions[0]
  const sessionIds = new Set(sessions.map((session) => session.session_id).filter((id): id is string => !!id))
  const alerts = profile.alerts
    .map((alert) => ({
      ...alert,
      related_sessions: alert.related_sessions.filter((id) => sessionIds.has(id)),
    }))
    .filter((alert) => alert.related_sessions.length > 0 || (!!alert.last_seen && alert.last_seen >= start && alert.last_seen <= end))
  const days = Math.floor((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000) + 1
  const byDate = new Map(scored.map((session) => [session.date, session.overall_score! * 20]))
  const trend = Array.from({ length: days }, (_, offset) => {
    const date = new Date(Date.parse(`${start}T00:00:00Z`) + offset * 86400000).toISOString().slice(0, 10)
    const value = byDate.get(date)
    return { date, average: value ?? null, sample_count: value === undefined ? 0 : 1 }
  })
  return {
    ...profile,
    days,
    period_start: start,
    period_end: end,
    counts: {
      in_window: sessions.length,
      comparable: sessions.length,
      scored: scored.length,
      pending_review: sessions.length - scored.length,
      other_version: 0,
    },
    average_total: average,
    latest_score: latestScored ? scale(latestScored.overall_score!) : null,
    latest_date: latestScored?.date ?? null,
    latest_risk: latest?.risk_level ?? null,
    dimensions: profile.dimensions.map((dimension) => ({
      ...dimension,
      average: scored.length ? dimension.average : null,
      sample_count: scored.length,
    })),
    trend,
    sessions,
    alerts,
  }
}

export function monitoringPreviewList(start = iso(DAYS - 1), end = iso(0)): MonitoringList {
  const profiles = [PROFILES['dr-1087']!, PROFILES['dr-2091']!, PROFILES['dr-3050']!]
    .map((profile) => profileForRange(profile, start, end))
    .filter((profile): profile is DoctorProfile => profile !== null)
  const doctors = profiles.map(summary)
  const days = Math.floor((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000) + 1
  return {
    available: true,
    source: 'offline-preview',
    days,
    period_start: start,
    period_end: end,
    timezone: 'Asia/Shanghai',
    generated_at: new Date().toISOString(),
    rubric_version: 'offline-preview',
    policy_version: 'monitoring-v1',
    doctor_count: doctors.length,
    alert_counts: {
      high: doctors.reduce(
        (sum, d) => sum + d.alerts.filter((a) => a.level === 'high').length,
        0,
      ),
      medium: doctors.reduce(
        (sum, d) => sum + d.alerts.filter((a) => a.level === 'medium').length,
        0,
      ),
    },
    excluded_missing_doctor_id: 0,
    doctors,
  }
}

export function monitoringPreviewProfile(doctorId: string, start = iso(DAYS - 1), end = iso(0)): DoctorProfile | null {
  const profile = PROFILES[doctorId]
  return profile ? profileForRange(profile, start, end) : null
}

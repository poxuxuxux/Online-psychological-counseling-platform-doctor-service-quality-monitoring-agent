import { describe, expect, it } from 'vitest'
import { monitoringPreviewProfile } from '../../src/data/monitoringPreview'

describe('offline doctor trend data', () => {
  it('keeps daily sample counts and weighted scores consistent with the records', () => {
    const profile = monitoringPreviewProfile('dr-1087', '2024-06-01', '2024-06-30')!
    expect(profile.trend).toHaveLength(30)
    expect(profile.trend.filter((p) => p.average !== null)).toHaveLength(30)
    expect(profile.trend.reduce((sum, p) => sum + p.sample_count, 0)).toBe(profile.counts.scored)
    for (const point of profile.trend) {
      const records = profile.sessions.filter((s) => s.date === point.date && s.overall_score !== null)
      expect(point.average).toBeCloseTo(records.reduce((sum, s) => sum + s.overall_score! * 20, 0) / records.length)
    }
    expect(profile.latest_date).toBe('2024-06-30')
    expect(profile.sessions[0]!.date).toBe(profile.latest_date)
    expect(profile.latest_score).toBeCloseTo(profile.sessions[0]!.overall_score! * 20)
  })

  it('leaves an unscored review day empty instead of inventing a score', () => {
    const profile = monitoringPreviewProfile('dr-3050', '2024-03-01', '2024-06-30')!
    const pending = profile.sessions.filter((s) => s.overall_score === null)
    expect(pending).toHaveLength(3)
    for (const record of pending) {
      expect(profile.trend.find((p) => p.date === record.date)).toMatchObject({ average: null, sample_count: 0 })
    }
  })
})

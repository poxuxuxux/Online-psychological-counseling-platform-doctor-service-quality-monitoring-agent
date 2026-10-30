// 环节：前端预览数据层；用途：提供界面预览使用的合成数据，不代表生产评价结果。
import { OverviewSchema, type Overview } from '../api/contracts/overview'
import { dimensions } from '../utils/catalog'

// Separate synthetic aggregate fixture: never derived from or presented as real Agent reports.
export function overviewPreview(days = 30): Overview {
  if (days === 30) {
    const scores = [42, 47, 70, 57, 71, 86, 68, 73, 78, 82, 84]
    const scoreIndexes = new Set([0, 2, 5, 8, 11, 14, 17, 20, 23, 26, 29])
    let scoreIndex = 0
    const names = dimensions.map((dimension) => dimension.name)
    return OverviewSchema.parse({
      available: true,
      source: 'offline-preview',
      days,
      period_start: '2024-06-01',
      period_end: '2024-06-30',
      timezone: 'Asia/Shanghai',
      generated_at: new Date().toISOString(),
      rubric_version: 'preview-only',
      score_scale: 100,
      rules: { high_quality_min: 85, risk_below: 60 },
      counts: {
        evaluated: 1852,
        scored: 1852,
        high_quality: 1423,
        risk: 128,
        pending: 0,
        other_version: 0,
        synthetic: 1852,
      },
      average_total: 84,
      dimensions: dimensions.map((d, i) => ({
        dimension_id: d.id,
        name: names[i],
        average: [84, 90, 78, 76, 82, 86][i],
        sample_count: 1852,
      })),
      trend: Array.from({ length: 30 }, (_, i) => {
        const scored = scoreIndexes.has(i)
        const average = scored ? scores[scoreIndex++]! : null
        return {
          date: `2024-06-${String(i + 1).padStart(2, '0')}`,
          average,
          sample_count: scored ? 168 : 0,
        }
      }),
    })
  }
  const localDate = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
  const end = new Date(localDate + 'T00:00:00+08:00')
  const dates = Array.from({ length: days }, (_, i) => {
    const d = new Date(end.getTime() - (days - 1 - i) * 86400000)
    return new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(d)
  })
  const values = [78, 86, 58, 92, 82, 88, 72, 55, 85, 90, 79, 94]
  const trend = dates.map((date, i) => {
    const index = i - (days - Math.min(days, values.length))
    return { date, average: index < 0 ? null : values[index]!, sample_count: index < 0 ? 0 : 1 }
  })
  const totals = trend.flatMap((p) => (p.average === null ? [] : [p.average]))
  const n = totals.length
  return OverviewSchema.parse({
    available: true,
    source: 'offline-preview',
    days,
    period_start: dates[0],
    period_end: dates[dates.length - 1],
    timezone: 'Asia/Shanghai',
    generated_at: new Date().toISOString(),
    rubric_version: 'preview-only',
    score_scale: 100,
    rules: { high_quality_min: 85, risk_below: 60 },
    counts: {
      evaluated: n + 3,
      scored: n,
      high_quality: totals.filter((s) => s >= 85).length,
      risk: totals.filter((s) => s < 60).length,
      pending: 3,
      other_version: 0,
      synthetic: n + 3,
    },
    average_total: totals.reduce((a, b) => a + b, 0) / n,
    dimensions: dimensions.map((d, i) => ({
      dimension_id: d.id,
      name: d.name,
      average: [87.2, 76.8, 83.4, 89.1, 78.5, 72.6][i],
      sample_count: i === 5 ? Math.max(1, n - 2) : n,
    })),
    trend,
  })
}

export function overviewPreviewRange(start: string, end: string): Overview {
  const startDate = new Date(`${start}T00:00:00Z`)
  const endDate = new Date(`${end}T00:00:00Z`)
  const days = Math.floor((endDate.getTime() - startDate.getTime()) / 86400000) + 1
  if (!Number.isFinite(days) || days < 1 || days > 365) return overviewPreview(30)

  const fixture = overviewPreview(30)
  const fixtureTrend = new Map(fixture.trend.map((point) => [point.date, point]))
  const trend = Array.from({ length: days }, (_, offset) => {
    const date = new Date(startDate.getTime() + offset * 86400000).toISOString().slice(0, 10)
    return fixtureTrend.get(date) ?? { date, average: null, sample_count: 0 }
  })
  const coveredDays = trend.filter((point) => fixtureTrend.has(point.date)).length
  const coverage = coveredDays / fixture.trend.length
  const scoredPoints = trend.filter((point) => point.average !== null)
  const selectedSamples = scoredPoints.reduce((sum, point) => sum + point.sample_count, 0)
  const fixtureSamples = fixture.trend.reduce((sum, point) => sum + point.sample_count, 0)
  const scoreCoverage = fixtureSamples ? selectedSamples / fixtureSamples : 0
  const counts = {
    evaluated: Math.max(selectedSamples, Math.round(fixture.counts.evaluated! * coverage)),
    scored: coveredDays === fixture.trend.length ? fixture.counts.scored! : selectedSamples,
    high_quality: Math.round(fixture.counts.high_quality! * scoreCoverage),
    risk: Math.round(fixture.counts.risk! * scoreCoverage),
    pending: 0,
    other_version: 0,
    synthetic: Math.round(fixture.counts.synthetic! * coverage),
  }
  counts.pending = Math.max(0, counts.evaluated - counts.scored)
  counts.high_quality = Math.min(counts.scored, counts.high_quality)
  counts.risk = Math.min(counts.scored - counts.high_quality, counts.risk)
  const sampleTotal = scoredPoints.reduce((sum, point) => sum + point.sample_count, 0)
  const averageTotal = coveredDays === fixture.trend.length
    ? fixture.average_total
    : sampleTotal
      ? scoredPoints.reduce((sum, point) => sum + point.average! * point.sample_count, 0) / sampleTotal
      : null

  return OverviewSchema.parse({
    ...fixture,
    days,
    period_start: start,
    period_end: end,
    counts,
    average_total: averageTotal,
    dimensions: fixture.dimensions.map((dimension) => ({
      ...dimension,
      average: counts.scored ? dimension.average : null,
      sample_count: counts.scored,
    })),
    trend,
  })
}

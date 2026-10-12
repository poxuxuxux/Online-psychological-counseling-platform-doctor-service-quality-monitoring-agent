import { OverviewSchema, type Overview } from '../api/contracts/overview'
import { dimensions } from '../utils/catalog'

// Separate synthetic aggregate fixture: never derived from or presented as real Agent reports.
export function overviewPreview(days = 30): Overview {
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

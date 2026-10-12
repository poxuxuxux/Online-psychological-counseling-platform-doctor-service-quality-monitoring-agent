import type { CaseState, MetricState, RunState } from '../types/domain'

export function runTone(status: RunState): 'green' | 'amber' | 'red' | 'blue' {
  if (status === '已完成') return 'green'
  if (status === '失败') return 'red'
  if (status === '部分完成') return 'amber'
  return 'blue'
}

export function caseTone(status: CaseState): 'green' | 'amber' | 'blue' {
  if (status === '已处理') return 'green'
  if (status === '处理中') return 'blue'
  return 'amber'
}

export function metricTone(status: MetricState): 'green' | 'amber' | 'purple' | 'slate' {
  if (status === '达标') return 'green'
  if (status === '需复核') return 'amber'
  if (status === '证据不足') return 'purple'
  return 'slate'
}

export function shortDate(value: string): string {
  const match = value.match(/\d{4}-(\d{2})-(\d{2})\s*(\d{2}:\d{2})?/)
  return match ? `${match[1]}/${match[2]} ${match[3] ?? ''}`.trim() : value
}

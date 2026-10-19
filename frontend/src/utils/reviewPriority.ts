// 环节：前端展示工具层；用途：提供目录映射、显示计算、导出或复核排序逻辑。
import type { Row } from './trust'

export type PriorityLevel = 'high' | 'medium' | 'low'
export const priorityLevels: PriorityLevel[] = ['high', 'medium', 'low']
export const priorityNames = { high: '高', medium: '中', low: '低' } as const
// Workflow priority v1; never infer a patient's clinical urgency from a score.
export function reviewPriority(row: Row): { level: PriorityLevel; reason: string } {
  if (/^D6(?:\.|$)/.test(row.finding.metric_id))
    return { level: 'high', reason: '涉及风险响应或转介指标，优先由专业人员核查。' }
  if (row.verdict.code === 'conflict')
    return { level: 'high', reason: '存在材料冲突或明确核验异议，需要优先厘清依据。' }
  if (
    row.verdict.code === 'insufficient' ||
    row.agentStatus !== 'completed' ||
    row.verification?.applicability_status === 'mismatched' ||
    row.verification?.rubric_status === 'mismatched'
  )
    return { level: 'medium', reason: '证据、执行结果或评分依据尚不充分，需要补查。' }
  return { level: 'low', reason: '当前为常规核验或评分规则确认，按序复核。' }
}
export function comparePriority(a: Row, b: Row): number {
  return (
    priorityLevels.indexOf(reviewPriority(a).level) -
    priorityLevels.indexOf(reviewPriority(b).level)
  )
}

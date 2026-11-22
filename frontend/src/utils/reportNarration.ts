import type { Report } from '../api/contracts/evaluation'
import { overallScore, reportRows } from './trust'
import { dimensions, metrics } from './catalog'

function spokenNumber(value: string): string {
  const digits = '零一二三四五六七八九'
  const [whole = '0', fraction] = value.split('.')
  const number = Number(whole)
  let integer = whole
  if (number < 10) integer = digits[number]!
  else if (number < 100)
    integer = (number < 20 ? '' : digits[Math.floor(number / 10)]) + '十' + (number % 10 ? digits[number % 10] : '')
  else if (number === 100) integer = '一百'
  return integer + (fraction ? '点' + Array.from(fraction, digit => digits[Number(digit)]).join('') : '')
}

export function spokenReportText(source: string): string {
  return source
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
    .replace(/^\s*[-*•]\s+/gm, '')
    .replace(/[*_`]/g, '')
    .replace(/(?<![\d.])(\d+(?:\.\d+)?)\s*\/\s*(100|5)(?![\d/])\s*分?/g,
      (original, numerator: string, denominator: string) => Number(numerator) <= Number(denominator)
        ? spokenNumber(numerator) + '分，满分' + spokenNumber(denominator) + '分' : original)
    .replace(/(\d+(?:\.\d+)?)\s*[%％]/g, (_, number: string) => '百分之' + spokenNumber(number))
    .replace(/D[1-6]\.\d+/gi, id => {
      const metric = metrics.find(item => item.id === id.toUpperCase())
      return metric ? metric.name + '指标' : id
    })
    .replace(/D[1-6](?![\d.])/gi, id => dimensions.find(item => item.id === id.toUpperCase())?.name || id)
    .replace(/(?<![\d.])(\d+\.\d+)(?![\d.])/g, (_, number: string) => spokenNumber(number))
    .replace(/\s*[|｜]\s*/g, '，')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function reportNarration(report: Report | null): string {
  if (!report) return ''
  if (report.status === 'failed')
    return '你好，我是小鉴。本次评价执行未完成，尚未形成最终评分报告。请先查看运行详情，处理后再评价。'
  const lines = ['你好，我是小鉴。我来为你介绍这次评价的主要结果。']
  if (report.status === 'partial') lines.push('本次报告为部分完成，请结合未评分项目和待复核事项阅读。')
  const score = overallScore(report)
  lines.push(score === null
    ? '当前尚未形成可展示的综合分。'
    : `本次综合评分为${Number((score * 20).toFixed(1))}分，满分一百分。`)
  if (report.summary.trim()) lines.push('先来看整体情况。' + report.summary.trim())
  const pending = reportRows(report).filter(row =>
    !['verified', 'agent_scored', 'not_applicable'].includes(row.verdict.code))
  if (pending.length) lines.push(`当前有${pending.length}项指标需要进一步核对，请查看报告明细。`)
  else if (report.review_required) lines.push('本报告仍有需要人工复核的事项，请查看报告明细。')
  const suggestions = report.improvements.map(item => item.suggestion.trim()).filter(Boolean).slice(0, 3)
  if (suggestions.length) lines.push('接下来，有几条改进建议供你参考。',
    ...suggestions.map((text, index) => `${['首先', '其次', '最后'][index]}，${text}`))
  lines.push('以上为本次报告摘要，具体评分理由与证据请查看报告原文。')
  return spokenReportText(lines.join('\n\n'))
}

export function speechChunks(text: string): string[] {
  // Short utterances keep long reports playable in browsers with speech time limits.
  const sentences = text.match(/[^。！？；\n]+[。！？；]?/gu) || []
  const chunks: string[] = []
  let pending = ''
  for (const sentence of sentences) {
    const chars = Array.from(sentence.trim())
    if (Array.from(pending).length + chars.length <= 120) {
      pending += chars.join('')
      continue
    }
    if (pending) chunks.push(pending)
    pending = ''
    while (chars.length > 120) chunks.push(chars.splice(0, 120).join(''))
    pending = chars.join('')
  }
  if (pending) chunks.push(pending)
  return chunks
}

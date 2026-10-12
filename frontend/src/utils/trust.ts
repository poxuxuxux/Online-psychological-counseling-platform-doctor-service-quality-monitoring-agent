import type { Evidence, Finding, Report, Session, Verification } from '../api/contracts/evaluation'

export type Verdict = {
  code: 'verified' | 'pending' | 'insufficient' | 'conflict' | 'not_applicable'
  text: string
  tone: 'success' | 'warning' | 'danger' | 'neutral'
}
export type Row = {
  finding: Finding
  agentId: string
  agentStatus: string
  verification?: Verification
  verdict: Verdict
}
export function verdict(f: Finding, v?: Verification, agentStatus = 'completed'): Verdict {
  if (f.applicability === 'not_applicable')
    return { code: 'not_applicable', text: '不适用', tone: 'neutral' }
  if (f.applicability === 'insufficient_context')
    return { code: 'insufficient', text: '证据不足', tone: 'warning' }
  if (v?.reference_conflict) return { code: 'conflict', text: '材料冲突', tone: 'danger' }
  if (
    v &&
    (v.reference_status === 'quote_mismatch' ||
      v.reference_status === 'source_mismatch' ||
      v.support_status === 'unsupported' ||
      v.claim_results.some((c) => c.status === 'contradicted'))
  ) {
    return { code: 'conflict', text: '核验有异议', tone: 'danger' }
  }
  if (
    !f.evidence.length ||
    !f.evidence.some((e) => e.message_ids.length && e.quote.trim()) ||
    v?.reference_status === 'missing'
  )
    return { code: 'insufficient', text: '证据不足', tone: 'warning' }
  const completeClaims =
    v &&
    v.claims.length > 0 &&
    v.claims.every(
      (claim) =>
        claim.finding_id === f.finding_id &&
        v.claim_results.some((c) => c.claim_id === claim.claim_id && c.status === 'supported'),
    )
  if (
    agentStatus === 'completed' &&
    f.score !== null &&
    v?.reference_status === 'valid' &&
    v.support_status === 'supported' &&
    v.applicability_status === 'matched' &&
    v.rubric_status === 'matched' &&
    completeClaims &&
    !v.issues.length
  ) {
    return { code: 'verified', text: '核验通过', tone: 'success' }
  }
  return { code: 'pending', text: '待核验 / 复核', tone: 'warning' }
}
export function reportRows(report: Report | null): Row[] {
  if (!report) return []
  const all = report.agent_results.flatMap((a) =>
    a.findings.map((f) => ({ finding: f, agentId: a.agent_id, agentStatus: a.status })),
  )
  // Only an explicit same-agent, same-metric link supersedes the original finding.
  const superseded = new Set(
    all.flatMap((row) => {
      const prior = all.find((p) => p.finding.finding_id === row.finding.supersedes_finding_id)
      return row.finding.attempt === 1 &&
        prior &&
        prior.agentId === row.agentId &&
        prior.finding.metric_id === row.finding.metric_id &&
        prior.finding.attempt === 0
        ? [prior.finding.finding_id]
        : []
    }),
  )
  return all
    .filter((row) => !superseded.has(row.finding.finding_id))
    .map((row) => {
      const checks = report.verification_results.filter(
        (v) => v.finding_id === row.finding.finding_id,
      )
      const verification = checks.length === 1 ? checks[0] : undefined
      return { ...row, verification, verdict: verdict(row.finding, verification, row.agentStatus) }
    })
}
export function overallScore(report: Report | null): number | null {
  if (
    !report ||
    report.status !== 'completed' ||
    report.review_required ||
    report.arbitration_status === 'unresolved'
  )
    return null
  const active = reportRows(report).filter((r) => r.verdict.code !== 'not_applicable')
  if (new Set(active.map((r) => r.finding.metric_id)).size !== active.length) return null
  if (!active.length || active.some((r) => r.verdict.code !== 'verified')) return null
  const profile = report.quality_profile
  return profile?.coverage_gate_passed ? profile.overall_score : null
}
const normalize = (s: string) => s.normalize('NFKC').replace(/\s+/g, '')
export function localReference(
  e: Evidence,
  session: Session | null,
): { valid: boolean; reason: string } {
  if (!session || !e.message_ids.length || !e.quote.trim())
    return { valid: false, reason: '缺少消息或引文，无法定位' }
  const messages = e.message_ids.map((id) => session.messages.find((m) => m.message_id === id))
  if (messages.some((m) => !m)) return { valid: false, reason: '本次会话中找不到引用消息' }
  const found = messages.some((m) => m && normalize(m.content).includes(normalize(e.quote)))
  return found
    ? { valid: true, reason: '本次原文可定位；不代表语义或评分核验通过' }
    : { valid: false, reason: '引文与本次原文不匹配' }
}
export function relatedFindings(report: Report, f: Finding): Finding[] {
  const all = report.agent_results.flatMap((a) => a.findings)
  const predecessor = f.supersedes_finding_id
    ? all.find((p) => p.finding_id === f.supersedes_finding_id)
    : undefined
  return predecessor ? [predecessor, f] : [f]
}

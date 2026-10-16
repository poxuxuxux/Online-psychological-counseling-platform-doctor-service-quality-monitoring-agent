import { describe, expect, it } from 'vitest'
import {
  FindingSchema,
  ReportSchema,
  VerificationSchema,
  SessionSchema,
  type Report,
} from '../../src/api/contracts/evaluation'
import { localReference, overallScore, reportRows, verdict } from '../../src/utils/trust'
import { previewReport, previewSession } from '../../src/data/preview'

const finding = () =>
  FindingSchema.parse({
    finding_id: 'f1',
    metric_id: 'D4.1',
    score: 4,
    rationale: '回应情绪',
    evidence: [{ message_ids: ['m1'], quote: '很辛苦' }],
  })
const verification = () =>
  VerificationSchema.parse({
    finding_id: 'f1',
    reference_status: 'valid',
    support_status: 'supported',
    applicability_status: 'matched',
    rubric_status: 'matched',
    claims: [
      {
        claim_id: 'c1',
        finding_id: 'f1',
        claim_type: 'observed_behavior',
        statement: '回应了辛苦',
      },
    ],
    claim_results: [{ claim_id: 'c1', status: 'supported' }],
  })
const report = (): Report =>
  ReportSchema.parse({
    evaluation_id: 'r1',
    session_id: 's1',
    status: 'completed',
    agent_results: [
      { agent_id: 'empathy_relationship', status: 'completed', findings: [finding()] },
    ],
    verification_results: [verification()],
    quality_profile: { overall_score: 4, overall_coverage: 1, coverage_gate_passed: true },
  })
describe('trust display policy', () => {
  it('does not turn candidate scores into verified results without verification', () =>
    expect(verdict(finding()).code).toBe('pending'))
  it('requires all four checks and per-claim support', () =>
    expect(verdict(finding(), verification()).code).toBe('verified'))
  it('keeps absent claims pending even with a supported summary', () => {
    const v = verification()
    v.claims = []
    expect(verdict(finding(), v).code).toBe('pending')
  })
  it('requires every claim to be checked', () => {
    const v = verification()
    v.claims.push({ ...v.claims[0]!, claim_id: 'c2' })
    expect(verdict(finding(), v).code).toBe('pending')
  })
  it('keeps unknown score anchors pending', () => {
    const v = verification()
    v.rubric_status = 'uncertain'
    expect(verdict(finding(), v).code).toBe('pending')
  })
  it('retains material conflicts separately', () => {
    const v = verification()
    v.reference_conflict = true
    expect(verdict(finding(), v).code).toBe('conflict')
  })
  it('retains explicit contradiction', () => {
    const v = verification()
    v.claim_results[0]!.status = 'contradicted'
    expect(verdict(finding(), v).code).toBe('conflict')
  })
  it('does not equate missing evidence with low quality', () => {
    const f = finding()
    f.evidence = []
    expect(verdict(f).code).toBe('insufficient')
    expect(f.score).toBe(4)
  })
  it('distinguishes objectively not applicable', () => {
    const f = finding()
    f.applicability = 'not_applicable'
    f.score = null
    expect(verdict(f).code).toBe('not_applicable')
  })
  it('distinguishes insufficient context', () => {
    const f = finding()
    f.applicability = 'insufficient_context'
    f.score = null
    expect(verdict(f).code).toBe('insufficient')
  })
  it('does not approve a partial Agent result', () =>
    expect(verdict(finding(), verification(), 'partial').code).toBe('pending'))
  it('does not calculate an average in the browser', () => {
    const r = report()
    r.quality_profile = null
    expect(overallScore(r)).toBeNull()
  })
  it('uses backend total only with gates satisfied', () => expect(overallScore(report())).toBe(4))
  it('hides total when any finding is pending', () => {
    const r = report()
    r.verification_results = []
    expect(overallScore(r)).toBeNull()
  })
  it('hides total under manual review gate', () => {
    const r = report()
    r.review_required = true
    expect(overallScore(r)).toBeNull()
  })
  it('hides total under unresolved arbitration', () => {
    const r = report()
    r.arbitration_status = 'unresolved'
    expect(overallScore(r)).toBeNull()
  })
  it('does not interpret missing coverage gate as passed', () => {
    const r = report()
    r.quality_profile!.coverage_gate_passed = false
    expect(overallScore(r)).toBeNull()
  })
  it('replaces initial finding only through an explicit same-owner revision link', () => {
    const r = report()
    r.agent_results[0]!.findings.push({
      ...finding(),
      finding_id: 'f2',
      attempt: 1,
      supersedes_finding_id: 'f1',
    })
    expect(reportRows(r).map((r) => r.finding.finding_id)).toEqual(['f2'])
  })
  it('never supersedes a different metric', () => {
    const r = report()
    r.agent_results[0]!.findings.push({
      ...finding(),
      finding_id: 'f2',
      metric_id: 'D4.2',
      attempt: 1,
      supersedes_finding_id: 'f1',
    })
    expect(reportRows(r)).toHaveLength(2)
  })
  it('never supersedes another owner', () => {
    const r = report()
    r.agent_results.push({
      agent_id: 'other',
      status: 'completed',
      findings: [{ ...finding(), finding_id: 'f2', attempt: 1, supersedes_finding_id: 'f1' }],
    })
    expect(reportRows(r)).toHaveLength(2)
  })
})
describe('incomplete or conflicting backend records', () => {
  it('does not adopt contradictory duplicate verification records', () => {
    const r = report()
    r.verification_results.push({ ...verification(), support_status: 'unsupported' })
    expect(reportRows(r)[0]!.verdict.code).toBe('pending')
  })
  it('does not approve claims associated with another finding', () => {
    const v = verification()
    v.claims[0]!.finding_id = 'different'
    expect(verdict(finding(), v).code).toBe('pending')
  })
  it('does not display a total for repeated active metric owners', () => {
    const r = report()
    r.agent_results[0]!.findings.push({ ...finding(), finding_id: 'f2' })
    r.verification_results.push({
      ...verification(),
      finding_id: 'f2',
      claims: [{ ...verification().claims[0]!, finding_id: 'f2' }],
    })
    expect(overallScore(r)).toBeNull()
  })
})
describe('evidence navigation and schema boundary', () => {
  const session = SessionSchema.parse({
    session_id: 's1',
    messages: [{ message_id: 'm1', role: 'doctor', content: '这段时间让你很辛苦。', sequence: 0 }],
  })
  it('finds actual quoted text', () =>
    expect(localReference(finding().evidence[0]!, session).valid).toBe(true))
  it('does not turn a missing message into a successful reference', () => {
    const e = { ...finding().evidence[0]!, message_ids: ['history-m1'] }
    expect(localReference(e, session).valid).toBe(false)
  })
  it('rejects a changed quote', () => {
    const e = { ...finding().evidence[0]!, quote: '医生安排了复诊' }
    expect(localReference(e, session).valid).toBe(false)
  })
  it('rejects empty quotes', () => {
    const e = { ...finding().evidence[0]!, quote: '' }
    expect(localReference(e, session).valid).toBe(false)
  })
  it('rejects duplicate message IDs', () =>
    expect(
      SessionSchema.safeParse({ ...session, messages: [session.messages[0], session.messages[0]] })
        .success,
    ).toBe(false))
  it('rejects invalid scores', () =>
    expect(FindingSchema.safeParse({ ...finding(), score: 6 }).success).toBe(false))
  it('rejects duplicate finding IDs', () => {
    const r = report()
    r.agent_results[0]!.findings.push(finding())
    expect(ReportSchema.safeParse(r).success).toBe(false)
  })
  it('supports explicitly marked synthetic revision fixtures', () => {
    const r = previewReport()
    expect(reportRows(r)).toHaveLength(7)
    expect(r.discussions).toHaveLength(4)
    expect(overallScore(r)).toBeNull()
    expect(previewSession().source_id).toBe('offline-preview')
  })
})

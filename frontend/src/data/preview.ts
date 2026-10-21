// 环节：前端预览数据层；用途：提供界面预览使用的合成数据，不代表生产评价结果。
import { SessionSchema, ReportSchema, type Report } from '../api/contracts/evaluation'

// Entirely synthetic UX fixtures. These values are not model results or validated clinical anchors.
export function previewSession(index = 0) {
  const rows = [
    ['patient', '医生您好，我最近两周晚上很难入睡，白天上班也很疲惫。'],
    ['doctor', '听起来这段时间的失眠让你很辛苦。我想先了解一下，通常几点入睡，夜里会醒几次？'],
    ['patient', '大约凌晨一点才能睡，夜里会醒两三次，第二天很难集中注意力。'],
    ['doctor', '谢谢你说得这么具体。我们可以先记录一周的睡眠情况，下次根据记录一起讨论调整方案。'],
    ['patient', '好的，我愿意试试。'],
    ['doctor', '如果这几天症状明显加重，或已经影响到基本生活，请及时联系专业医疗机构。'],
  ]
  return SessionSchema.parse({
    session_id: `preview-synthetic-${String(index + 1).padStart(3, '0')}`,
    source_id: 'offline-preview',
    consultation_round: 'initial',
    messages: rows.map(([role, content], i) => ({
      message_id: index ? `preview-${index + 1}-m${i + 1}` : `preview-m${i + 1}`,
      role,
      content:
        index && i === 0
          ? [
              '医生您好，我这三周入睡比较困难，白天总感觉疲惫。',
              '医生您好，最近加班后晚上很难入睡，白天工作也很疲惫。',
            ][index - 1] || content
          : content,
      sequence: i,
      timestamp: `2026-10-${String(11 + index).padStart(2, '0')}T14:${String(i * 2).padStart(2, '0')}:00`,
    })),
  })
}
export function previewReport(session = previewSession()): Report {
  const evidence = (i: number) => [
    {
      message_ids: [session.messages[i]!.message_id],
      quote: session.messages[i]!.content,
      explanation: '合成交互样例中的医生原话。',
    },
  ]
  return ReportSchema.parse({
    evaluation_id: `preview-${crypto.randomUUID()}`,
    session_id: session.session_id,
    status: 'completed',
    risk: {
      level: 'medium',
      scope: 'doctor_service_quality',
      reasons: ['synthetic_preview_requires_review'],
    },
    summary:
      '这是本地合成交互样例，用于检查证据定位、初评修正、讨论与待复核状态。所有分数和核验意见均为预设示例，不能用于评价真实医生。',
    review_required: true,
    review_reasons: ['D4.1 的事实解释和评分依据仍有分歧；离线样例保留人工复核。'],
    arbitration_status: 'unresolved',
    limitations: [
      '离线样例没有运行模型，没有写入服务器数据库。',
      '演示分数用于交互验收，不代表经专业审定的评分规则。',
    ],
    agent_results: [
      {
        agent_id: 'professional_service',
        status: 'completed',
        findings: [
          {
            finding_id: 'preview-f1',
            metric_id: 'D3.1',
            metric_version: 'preview-draft',
            score: 4,
            rationale: '医生询问入睡时间及夜间醒来次数。',
            evidence: evidence(1),
          },
          {
            finding_id: 'preview-f2',
            metric_id: 'D3.2',
            metric_version: 'preview-draft',
            applicability: 'insufficient_context',
            score: null,
            rationale: '本轮材料不能可靠判断病史与既往治疗核对情况。',
            evidence: [],
          },
          {
            finding_id: 'preview-f3',
            metric_id: 'D6.2',
            metric_version: 'preview-draft',
            applicability: 'not_applicable',
            score: null,
            rationale: '该合成交互样例将本项标记为不适用，以验证空分数展示。',
            evidence: [],
          },
        ],
      },
      {
        agent_id: 'process_response',
        status: 'completed',
        findings: [
          {
            finding_id: 'preview-f4',
            metric_id: 'D2.1',
            metric_version: 'preview-draft',
            score: 4,
            rationale: '消息时间显示首次回复间隔为 2 分钟；适用时限需以正式指标规则为准。',
            evidence: evidence(1),
          },
          {
            finding_id: 'preview-f5',
            metric_id: 'D5.4',
            metric_version: 'preview-draft',
            score: 4,
            rationale: '医生提出记录一周睡眠情况的具体行动。',
            evidence: evidence(3),
          },
        ],
      },
      {
        agent_id: 'empathy_relationship',
        status: 'completed',
        findings: [
          {
            finding_id: 'preview-f6-original',
            metric_id: 'D4.1',
            metric_version: 'preview-draft',
            score: 4,
            rationale: '医生识别了患者的焦虑并回应失眠带来的辛苦。',
            evidence: evidence(1),
          },
          {
            finding_id: 'preview-f6',
            metric_id: 'D4.1',
            metric_version: 'preview-draft',
            attempt: 1,
            supersedes_finding_id: 'preview-f6-original',
            score: 3,
            rationale:
              '删除“识别焦虑”的无充分证据主张。原文可支持医生回应患者的辛苦感受，分数为交互预设示例。',
            evidence: evidence(1),
          },
          {
            finding_id: 'preview-f7',
            metric_id: 'D6.1',
            metric_version: 'preview-draft',
            applicability: 'insufficient_context',
            score: null,
            rationale: '风险回应指标尚待专业审定；本条仅展示证据定位与人工复核。',
            evidence: evidence(5),
          },
        ],
      },
    ],
    verification_results: [
      {
        finding_id: 'preview-f1',
        reference_status: 'valid',
        support_status: 'supported',
        applicability_status: 'matched',
        rubric_status: 'matched',
        verifier_version: 'preview-only',
        claims: [
          {
            claim_id: 'preview-c1',
            finding_id: 'preview-f1',
            claim_type: 'observed_behavior',
            statement: '医生询问了入睡时间和醒来次数。',
          },
        ],
        claim_results: [
          {
            claim_id: 'preview-c1',
            status: 'supported',
            rationale: '两个问题均存在于本次医生发言中。',
            supporting_evidence: evidence(1),
          },
        ],
      },
      {
        finding_id: 'preview-f6',
        reference_status: 'valid',
        support_status: 'supported',
        applicability_status: 'matched',
        rubric_status: 'uncertain',
        verifier_version: 'preview-only',
        claims: [
          {
            claim_id: 'preview-c6',
            finding_id: 'preview-f6',
            claim_type: 'observed_behavior',
            statement: '医生回应了失眠带来的辛苦感受。',
          },
        ],
        claim_results: [
          {
            claim_id: 'preview-c6',
            status: 'supported',
            rationale: '原文提到“这段时间的失眠让你很辛苦”。',
            supporting_evidence: evidence(1),
          },
        ],
        issues: ['示例中的事实解释仍有争议，不能仅凭行为存在确认分数。'],
      },
      {
        finding_id: 'preview-f7',
        reference_status: 'valid',
        support_status: 'partial',
        applicability_status: 'uncertain',
        rubric_status: 'uncertain',
        verifier_version: 'preview-only',
        reference_conflict: true,
        issues: ['对本项适用情境的解释仍有冲突。保留原文并转人工核查。'],
      },
    ],
    discussions: [
      {
        finding_id: 'preview-f6-original',
        role: 'evaluator',
        text: '我认为医生回应了焦虑与失眠带来的辛苦，初评为 4 分。',
        message_ids: [session.messages[1]!.message_id],
      },
      {
        finding_id: 'preview-f6-original',
        role: 'verifier',
        text: '原文没有明确表达“焦虑”。请删除该主张，保留能回溯到原话的辛苦感受回应，并重新核对评分依据。',
        message_ids: [session.messages[0]!.message_id, session.messages[1]!.message_id],
      },
      {
        finding_id: 'preview-f6',
        role: 'evaluator',
        text: '接受定向质疑，删除焦虑主张，保留已发生的回应。修订分数只用于交互样例。',
        message_ids: [session.messages[1]!.message_id],
      },
      {
        finding_id: 'preview-f6',
        role: 'verifier',
        text: '修订后的事实主张可获支持；示例评分依据仍需人工判断。',
        message_ids: [session.messages[1]!.message_id],
      },
    ],
    arbitration_decisions: [
      {
        conflict_id: 'preview-conflict-6',
        metric_ids: ['D4.1'],
        status: 'unresolved',
        adopted: 'manual_review',
        rationale:
          '采纳对事实主张的修正。评分依据尚存分歧，转人工复核。',
        requires_manual_review: true,
      },
    ],
  })
}

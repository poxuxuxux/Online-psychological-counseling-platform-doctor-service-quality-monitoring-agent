import { dimensions, metrics } from '../utils/catalog'

export type ReviewRisk = 'high' | 'medium' | 'low'
export type ReviewStatus = 'pending' | 'submitted'
export type ReviewSpeaker = 'patient' | 'doctor'

export type ReviewMessage = {
  id: string
  role: ReviewSpeaker
  time: string
  content: string
  evidence?: number
}

export type ReviewMetric = {
  code: string
  name: string
  score: number
  rationale: string
  evidenceId: string
}

export type ReviewGroup = {
  id: string
  name: string
  icon: string
  metrics: ReviewMetric[]
}

export type ReviewSession = {
  id: string
  doctor: string
  patient: string
  updatedAt: string
  messageCount: number
  risk: ReviewRisk
  status: ReviewStatus
  score: number
  conclusion: string
  messages: ReviewMessage[]
  groups: ReviewGroup[]
}

export const riskText: Record<ReviewRisk, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}
export const statusText: Record<ReviewStatus, string> = {
  pending: '待复核',
  submitted: '已复核',
}

const groupIcons = ['shield', 'clock', 'message', 'heart', 'sparkle', 'alert']
const rationales = [
  '部分服务内容与咨询约定的目标仍需核对，建议结合原文确认履行情况。',
  '响应总体及时，个别交互节点仍可更明确地回应来访者的问题。',
  '信息探询和解释仍有补充空间，建议结合来访者的主要诉求逐项核对。',
  '情绪回应较为积极，可进一步确认来访者是否感到被理解和尊重。',
  '建议继续与来访者协商目标，并确认建议符合其现实条件且可执行。',
  '出现风险线索时应明确回应，并在需要时给出求助或转介提示。',
]

function makeGroups(messages: ReviewMessage[], scores: number[]): ReviewGroup[] {
  let scoreIndex = 0
  return dimensions.map((dimension, groupIndex) => ({
    id: dimension.id,
    name: `${dimension.id} ${dimension.name}`,
    icon: groupIcons[groupIndex]!,
    metrics: metrics.filter((metric) => metric.id.startsWith(`${dimension.id}.`)).map((metric) => ({
      code: metric.id,
      name: metric.name,
      score: scores[scoreIndex++] ?? 3,
      rationale: rationales[groupIndex]!,
      evidenceId: messages[Math.min(groupIndex, messages.length - 1)]!.id,
    })),
  }))
}

type Scenario = { patient: string[]; doctor: string[] }

const scenarios: Scenario[] = [
  {
    patient: [
      '最近一段时间我总是睡不着，脑子里会反复想很多事情。一到晚上就很焦虑，怎么办？',
      '大概有两个三个月了。白天还好，一到晚上就会紧张，心跳加快，脑子停不下来，有时候会想一些不好的事情。',
      '工作有点乱，最近工作压力比较大，经常加班，感觉自己一直处于紧绷的状态。',
    ],
    doctor: [
      '我理解这让你感到很困扰。能告诉我，这种情况大概持续了多久？平时还有其他不适的感觉吗？',
      '听起来你可能正经历一定程度的焦虑反应。为了更好地了解你的情况，我想再问几个问题：你平时的作息规律吗？最近有没有遇到特别的压力事件？',
      '我们可以先一起梳理压力来源，并记录一周的睡眠和情绪变化。如果不适持续加重，建议尽快到专业医疗机构进行进一步评估。',
    ],
  },
  {
    patient: [
      '我最近经常担心项目做不好，开会前会紧张，甚至想请假回避。',
      '我怕出错以后被否定，几乎每天上班前都会想这些，越靠近汇报越严重。',
      '这样分开看好像轻松一点，我其实已经准备得很充分了。',
    ],
    doctor: [
      '我理解这让你感到很困扰。能告诉我，这种情况大概持续了多久？平时还有其他不适的感觉吗？',
      '听起来你可能正经历一定程度的焦虑反应。为了更好地了解你的情况，我想再问几个问题：你平时的作息规律吗？最近有没有遇到特别的压力事件？',
      '我们可以先一起梳理压力来源，并记录一周的睡眠和情绪变化。如果不适持续加重，建议尽快到专业医疗机构进行进一步评估。',
    ],
  },
  {
    patient: [
      '这段时间情绪一直很低落，以前喜欢的事情现在也提不起兴趣。',
      '吃得比较少，周末也不出门，朋友约我我都拒绝了。',
      '我姐姐很关心我，但我不太想让她担心。',
    ],
    doctor: [
      '这种持续低落的感觉一定很不好受。它对你的睡眠、饮食和日常工作有什么影响？',
      '谢谢你愿意告诉我这些。我们可以先从一件负担很小的事情开始，同时了解你身边是否有可以支持你的人。',
      '我们可以讨论怎样用你舒服的方式让她了解你的近况，也会一起关注这些变化是否持续加重。',
    ],
  },
  {
    patient: [
      '按照上次说的做了睡眠记录，这周有三天能比较快入睡了。',
      '上午注意力好多了，但加班到很晚时还是容易反复醒来。',
      '好，我也想把午休控制在半小时以内。',
    ],
    doctor: [
      '你坚持记录做得很好。我看入睡时间提前了，白天精神状态有什么变化？',
      '这说明规律作息对你有帮助。我们可以针对加班日再设计一个更简短的睡前放松流程。',
      '可以，接下来继续记录一周。若白天功能再次明显下降，我们再及时评估并调整计划。',
    ],
  },
  {
    patient: [
      '昨天突然心跳很快、呼吸急促，持续了十几分钟，我很害怕。',
      '没有晕过去，休息后慢慢缓解了，最近体检也没有发现异常。',
      '好的，那我需要马上再去医院检查吗？',
    ],
    doctor: [
      '突然经历这些确实会让人害怕。当时是否伴随胸痛、晕厥？以前做过身体检查吗？',
      '建议先按医嘱排除身体原因。如果再次发作，可以记录诱因和持续时间，暂时到安全安静的地方休息。',
      '如果再次出现持续胸痛、意识不清或症状明显加重，请立即就医。目前也建议尽快预约门诊做进一步评估。',
    ],
  },
  {
    patient: [
      '我和家人沟通时总是吵架，事后又觉得很内疚。',
      '他们替我做了决定，我觉得自己没有选择权，但又不忍心让他们难过。',
      '我想先试着说出自己的安排，而不是马上反驳他们。',
    ],
    doctor: [
      '争吵后的内疚让你很矛盾。最近一次争吵是怎么开始的，当时你最希望被理解的是什么？',
      '你既希望维护关系，也希望自己的意愿被尊重。我们可以练习怎样把这两部分同时表达清楚。',
      '这是一个具体的开始。你可以先写下希望表达的三句话，我们下次一起看看沟通时的感受。',
    ],
  },
]

function makeMessages(index: number): ReviewMessage[] {
  const scenario = scenarios[index % scenarios.length]!
  const hour = 10 + (index % 8)
  const minute = String((index * 7) % 60).padStart(2, '0')
  return [
    { id: 'm1', role: 'patient', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.patient[0]! },
    { id: 'm2', role: 'doctor', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.doctor[0]! },
    { id: 'm3', role: 'patient', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.patient[1]!, evidence: 1 },
    { id: 'm4', role: 'doctor', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.doctor[1]! },
    { id: 'm5', role: 'patient', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.patient[2]!, evidence: 2 },
    { id: 'm6', role: 'doctor', time: `2024-06-0${1 + (index % 8)} ${hour}:${minute}`, content: scenario.doctor[2]! },
  ]
}

export function createReviewSessions(): ReviewSession[] {
  const risks: ReviewRisk[] = ['high', 'medium', 'low', 'high', 'medium', 'low', 'high', 'medium', 'low', 'medium', 'high', 'low', 'medium', 'medium']
  const doctors = ['张医生', '李医生', '王医生', '陈医生', '赵医生', '刘医生', '周医生', '吴医生', '郑医生', '孙医生', '钱医生', '许医生', '沈医生', '韩医生']
  const conclusions = [
    '存在明显情绪风险线索，医生在风险评估和转介条件上仍不充分。',
    '服务质量尚可，但部分回应与风险确认需要人工补充判断。',
    '整体较为平稳，建议保留抽查并完善随访记录。',
  ]
  return risks.map((risk, index) => {
    const day = String(1 + (index % 8)).padStart(2, '0')
    const messages = makeMessages(index)
    const riskOffset = risk === 'high' ? -0.6 : risk === 'medium' ? -0.2 : 0.4
    const scores = dimensions.flatMap((dimension, groupIndex) =>
      metrics
        .filter((metric) => metric.id.startsWith(`${dimension.id}.`))
        .map((_, metricIndex) => {
          const base = [3.3, 3.5, 3.0, 3.5, 3.3, 2.7][groupIndex]!
          return Math.max(2.2, Math.min(4.6, base + riskOffset + (metricIndex % 3) * 0.15))
        }),
    )
    return {
      id: `C202406${day}${String(index + 1).padStart(4, '0')}`,
      doctor: doctors[index]!,
      patient: `来访者 ${String(index + 1).padStart(2, '0')}`,
      updatedAt: `2024-06-${day} ${10 + (index % 8)}:${String((index * 7) % 60).padStart(2, '0')}`,
      messageCount: [32, 18, 25, 12, 28, 16, 22, 20, 17, 24, 31, 15, 19, 21][index]!,
      risk,
      status: 'pending',
      score: risk === 'high' ? 2.8 : risk === 'medium' ? 3.4 : 4.1,
      conclusion: conclusions[index % conclusions.length]!,
      messages,
      groups: makeGroups(messages, scores),
    }
  })
}
